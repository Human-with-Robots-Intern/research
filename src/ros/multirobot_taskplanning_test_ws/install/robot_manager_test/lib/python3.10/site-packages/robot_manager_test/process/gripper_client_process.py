"""
주의 사항 gripper properties는 task 단위에서 주도적으로 결정
    gripper process 단에 전해지는 정보 만으로는 gripper properties를 결정하기 어렵다.
    따라서 더 풍부한 정보를 가진 task 단계에서 gripper properties를 결정하는 것이 더 합리적이라고 판단하였다.

"""

# ros 기본 모듈
import rclpy
import rclpy.node
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ros 메시지 타입
from std_msgs.msg import Empty
from robot_manager_interface.srv import RobotManager
from control_msgs.action import GripperCommand
from action_msgs.msg import GoalStatus

# 파이썬 기본 모듈
import math
import enum

# 파이썬 사용자 정의 모듈
from robot_manager_state_transition.process.process import Process # 서브 프로세스 추상 클래스
from robot_manager_state_transition.robot_entity.robot import Robot
from robotiq_gripper_interface.srv import SetGripperStateCommand

class GripperClient(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        self.node = node_arg
        self.robot = robot_arg

        # <ros 기능 요소 선언>
        # set_gripper_state service 선언
        self.cli_set_gripper = self.node.create_client(SetGripperStateCommand, 'set_gripper_state')

        # gripper_action action 선언
        self.action_client_gripper_action = ActionClient(self.node, GripperCommand, 'panda_gripper/gripper_action', callback_group=MutuallyExclusiveCallbackGroup())

        # <ros2 콜백 관리용 요소 정의>
        # <set gripper service>
        # 서비스 request, result 퓨쳐
        self.future_set_gripper_request = None
        self.future_set_gripper_response = None
        # 서비스 결과 변수
        self.result_set_gripper = None

        # <gripper_action action> 
        # action 퓨쳐 변수
        self.send_goal_future_gripper_action = None
        self.get_result_future_gripper_action = None
        # goal handle
        self.goal_handle_gripper_action = None
        # 액션 결과 변수
        self.action_result_gripper_action = None
        self.action_status_gripper_action = None

        # 프로세스 상태 정의 (각 개별 프로세스마다 다르게 정의됨)
        class Process_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            request = enum.auto()
            wait_ack = enum.auto()#wait_acknowledgments
            working = enum.auto()
            complete = enum.auto()
            reset = enum.auto()
            error = enum.auto() # 오류를 처리중인 상태
            halt = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태
        
        # 프로세스 상태값 초기화
        self.process_state_enum:Process_state_enum = Process_state_enum
        self.process_state:int = self.process_state_enum.error.value

        self.request = None

        # ros2 서비스 초기화
        gripper_property_instance = self.robot.get_gripper_property_instance()
        if gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.panda.value:
            while not self.action_client_gripper_action.wait_for_server(timeout_sec=1.0):
                self.node.get_logger().info('gripper action not available, waiting again...')
        elif gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.robotiq.value:
            while not self.cli_set_gripper.wait_for_service(timeout_sec=1.0):
                self.node.get_logger().info('gripper service not available, waiting again...')

        #서비스 초기화가 완료되면 ready 상태로 전이
        self.process_state = self.process_state_enum.ready.value

        # 기타 상수 정의
        self.gripper_speed = 1.0

    # sub process 구성요소 정의
    # 추상 클래스 메서드 오버라이딩
    def do_assign_request(self, request_arg:GripperCommand.Goal):
        gripper_property_instance = self.robot.get_gripper_property_instance()
        if gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.panda.value:
            self.do_assign_request_franka(request_arg)
        elif gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.robotiq.value:
            self.do_assign_request_robotiq(request_arg)

        # self.flag_job_set의 경우 do_assign_request_franka 혹은 do_assign_request_robotiq 업데이트 된 값을 반환
        return self.flag_job_set

    def do_execute(self) -> None:
        gripper_property_instance = self.robot.get_gripper_property_instance()
        if gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.panda.value:
            self.do_execute_franka()
        elif gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.robotiq.value:
            self.do_execute_robotiq()
    
    def do_update(self) -> None:
        gripper_property_instance = self.robot.get_gripper_property_instance()
        if gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.panda.value:
            self.do_update_franka()
        elif gripper_property_instance.get_gripper_type() == gripper_property_instance.gripper_type_enum.robotiq.value:
            self.do_update_robotiq()
    
    def do_assign_request_robotiq(self, request_arg:GripperCommand.Goal):
        # 기존 작업에 관련된 값을 초기화
        self.flag_job_completed = False
        self.flag_job_set = False
        self.success = False
        self.result = None
        
        self.do_reset_log()

        # 새로운 작업을 적용할 수 있는 상태인지 확인
        gripper_properties = self.robot.get_gripper_property_instance()
        if self.process_state == self.process_state_enum.ready.value:
            is_working = gripper_properties.get_state() == gripper_properties.gripper_state_enum.working.value
            is_error = gripper_properties.get_state() == gripper_properties.gripper_state_enum.error.value
            is_halt = gripper_properties.get_state() == gripper_properties.gripper_state_enum.halt.value
            if not (is_working or is_error or is_halt):
                self.request = SetGripperStateCommand.Request()
                self.request.position = request_arg.command.position
                self.request.force = request_arg.command.max_effort
                self.request.speed = self.gripper_speed
                self.process_state = self.process_state_enum.request.value
                self.flag_job_set = True
        
        return self.flag_job_set
    
    def do_execute_robotiq(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request.value:
            print("request_send_plan_robotiq")
            self.do_request_robotiq_set_gripper()# detect objects 요청
        elif self.process_state == self.process_state_enum.wait_ack.value:
            ...
        elif self.process_state == self.process_state_enum.working.value:
            ...
        elif self.process_state == self.process_state_enum.complete.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            # 서비스 request 퓨쳐
            self.future_set_gripper_request = None

            # 서비스 result 퓨쳐
            self.future_set_gripper_response = None

            # 서비스 결과 변수
            self.result_set_gripper = None

        elif self.process_state == self.process_state_enum.error.value:
            ...
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_update_robotiq(self) -> None:
        self.do_log_state_trasition()
        # print("self.process_state      : {}".format(self.process_state))
        # print("self.flag_job_completed : {}".format(self.flag_job_completed))
        # print("self.flag_job_set       : {}".format(self.flag_job_set))
        # print("self.result             : {}".format(self.result))
        
        gripper_properties = self.robot.get_gripper_property_instance()
        # ready
        if self.process_state == self.process_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
            if self.flag_job_set == True:# 요청이 확인된 경우 다음 단계로 넘어감
                self.process_state = self.process_state_enum.request.value
            ... # 명령이 등록되지 않은 경우는 단순 대기함 뜀
        # request_send_plan
        elif self.process_state == self.process_state_enum.request.value:
            self.process_state = self.process_state_enum.wait_ack.value# send_goal을 수행했다면 acknowlegements 를 대기 
            # 변수들을 확인하여 send_goal 이 수행 완료되었다면 다음 상태로 넘어감
            # 변수들의 상태를 update에서 감시해주는 이유는 
            # callback에서 변수의 상태변화를 일으키는 경우가 매 실행마다 반영되도록 하기 위함이다.

            # 해당 분기에서는 goal handle을 통해 전달된 goal이 accept 되었는지 확인해야 한다.
            # goal이 accept 되었다면 상태를 working으로 전이하고
            # 만약 accept 되지 못했다면 상태를 error로 전이시켜야 한다.
        # wait_ack_send_plan
        elif self.process_state == self.process_state_enum.wait_ack.value:
            # 변수 확인
            if self.future_set_gripper_request is not None:
                self.process_state = self.process_state_enum.working.value
                # gripper_properties.set_state(gripper_properties.gripper_state_enum.working.value)# 로봇의 상태를 working으로 변경 그리퍼가 움직이는 상태임을 표시
            else:
                self.process_state = self.process_state_enum.error.value
                gripper_properties.set_state(gripper_properties.gripper_state_enum.error.value)# 로봇의 상태를 error으로 변경
                # 서비스의 경우 퓨쳐가 어떠한 방식으로 예외처리를 하는지 확인되지 않음...
                # 현재 상황으로는 future 자체의 python 예외를 통하여 예외처리가 되는 것으로 생각됨.
                # ... 어차피 발생한 예외를 처리하지 못하면 시스템이 종료되니, 잘못된 수행을 걱정할 필요는 없을 지도... 
                # futue 객체 예외 목록 링크 참고자료
                # https://docs.python.org/ko/3/library/concurrent.futures.html#exception-classes

        # working_send_plan
        elif self.process_state == self.process_state_enum.working.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self.future_set_gripper_response is not None:
                if self.future_set_gripper_response.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    if self.result_set_gripper is not None:
                        self.process_state = self.process_state_enum.complete.value
                    else:
                        self.process_state = self.process_state_enum.error.value
                        gripper_properties.set_state(gripper_properties.gripper_state_enum.error.value)# 로봇의 상태를 error으로 변경
        # complete_send_plan
        elif self.process_state == self.process_state_enum.complete.value:
            # 작업이 완료되면 reset 상태로 전이하여 각종 변수를 리셋
            self.process_state = self.process_state_enum.reset.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = True
        # reset
        elif self.process_state == self.process_state_enum.reset.value:
            # 각종 변수 및 상태를 초기화 한 후 ready 상태로 전이
            self.process_state = self.process_state_enum.ready.value
            # gripper_properties.set_state(gripper_properties.gripper_state_enum.ready.value)# 로봇의 상태를 ready으로 변경

        # error
        elif self.process_state == self.process_state_enum.error.value:
            self.process_state = self.process_state_enum.halt.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = False
                self.result = None
        # halt
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_assign_request_franka(self, request_arg:GripperCommand.Goal):
        # 기존 작업에 관련된 값을 초기화
        self.flag_job_completed = False
        self.flag_job_set = False
        self.success = False
        self.result = None
        
        # 새로운 작업을 적용할 수 있는 상태인지 확인
        gripper_properties = self.robot.get_gripper_property_instance()
        if self.process_state == self.process_state_enum.ready.value:
            if gripper_properties.get_state() == gripper_properties.gripper_state_enum.ready.value: 
                self.request = request_arg # 전달된 GripperCommand.Goal 타입의 정보를 그대로 request로 전달함. 
                self.process_state = self.process_state_enum.request.value
                self.flag_job_set = True
        
        return self.flag_job_set

    def do_execute_franka(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request.value:
            print("request_send_plan_franka")
            self.do_send_goal_gripper_action()# detect objects 요청
        elif self.process_state == self.process_state_enum.wait_ack.value:
            ...
        elif self.process_state == self.process_state_enum.working.value:
            ...
        elif self.process_state == self.process_state_enum.complete.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            # action 퓨쳐 변수
            self.send_goal_future_gripper_action = None
            self.get_result_future_gripper_action = None
            # goal handle
            self.goal_handle_gripper_action = None
            # 액션 결과 변수
            self.action_result_gripper_action = None
            self.action_status_gripper_action = None

        elif self.process_state == self.process_state_enum.error.value:
            ...
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_update_franka(self) -> None:
        self.do_log_state_trasition()
        # print("self.process_state      : {}".format(self.process_state))
        # print("self.flag_job_completed : {}".format(self.flag_job_completed))
        # print("self.flag_job_set       : {}".format(self.flag_job_set))
        # print("self.result             : {}".format(self.result))
        
        gripper_properties = self.robot.get_gripper_property_instance()
        # ready
        if self.process_state == self.process_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
            if self.flag_job_set == True:# 요청이 확인된 경우 다음 단계로 넘어감
                self.process_state = self.process_state_enum.request.value
            ... # 명령이 등록되지 않은 경우는 단순 대기함 뜀
        # request_send_plan
        elif self.process_state == self.process_state_enum.request.value:
            self.process_state = self.process_state_enum.wait_ack.value# send_goal을 수행했다면 acknowlegements 를 대기 

        # wait_ack_send_plan
        elif self.process_state == self.process_state_enum.wait_ack.value:
            # 변수 확인
            if self.goal_handle_gripper_action is not None:
                if self.goal_handle_gripper_action.accepted == True: 
                    self.process_state = self.process_state_enum.working.value
                else:
                    self.process_state = self.process_state_enum.error.value

        # working_send_plan
        elif self.process_state == self.process_state_enum.working.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self.get_result_future_gripper_action is not None:
                if self.get_result_future_gripper_action.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    if self.action_status_gripper_action is not None:
                        print("===self.action_status_gripper_action=== {}".format(self.action_status_gripper_action))
                        print(self.action_status_gripper_action == GoalStatus.STATUS_SUCCEEDED)
                        if self.action_status_gripper_action == GoalStatus.STATUS_SUCCEEDED:
                            self.process_state = self.process_state_enum.complete.value
                        else:
                            self.process_state = self.process_state_enum.error.value
                            gripper_properties.set_state(gripper_properties.gripper_state_enum.error.value)# 로봇의 상태를 error으로 변경
        # complete_send_plan
        elif self.process_state == self.process_state_enum.complete.value:
            # 작업이 완료되면 reset 상태로 전이하여 각종 변수를 리셋
            self.process_state = self.process_state_enum.reset.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = True
        # reset
        elif self.process_state == self.process_state_enum.reset.value:
            # 각종 변수 및 상태를 초기화 한 후 ready 상태로 전이
            self.process_state = self.process_state_enum.ready.value
            # gripper_properties.set_state(gripper_properties.gripper_state_enum.ready.value)# 로봇의 상태를 ready으로 변경

        # error
        elif self.process_state == self.process_state_enum.error.value:
            self.process_state = self.process_state_enum.halt.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = False
                self.result = None
        # halt
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_check_completion(self) -> bool:
        complete_bool_rtn = False
        if self.process_state == self.process_state_enum.ready.value or self.process_state == self.process_state_enum.error.value:
            # 모든 동작이 종료 및 정리되어서 ready 상태로 돌아 왔는지 확인
            # 혹은 error로 인하여 작업이 중단 되었는지 여부를 확인
            if self.flag_job_set == True:# 같은 ready 상태더라도 작업이 걸려있는 상태인지 확인
                if self.flag_job_completed == True:# 작업이 완료되었는지 여부 확인
                    complete_bool_rtn = True
                    self.flag_job_set = False
                    self.flag_job_completed = False
                    if self.process_state == self.process_state_enum.error.value:
                        self.process_state = self.process_state_enum.halt.value
        if self.process_state == self.process_state_enum.halt.value:
            complete_bool_rtn = True
            self.success = False
            self.result = None
        return complete_bool_rtn

    # <ros 콜백 함수 및 관리 함수 정의>
    # robotiq 그리퍼 콜백 정리
    def do_request_robotiq_set_gripper(self):
        print("object_detector_process_test")
        # reqest = SetGripperStateCommand.Request()
        self.future_set_gripper_request = self.cli_set_gripper.call_async(self.request)
        # add done callback
        self.future_set_gripper_request.add_done_callback(self.callback_robotiq_set_gripper_result)

    def callback_robotiq_set_gripper_result(self, future):
        self.future_set_gripper_response = future # 메모리 상에서는 self.future_send_plan_request 와 같은 객체를 가리킬 것임.
        self.result_set_gripper = self.future_set_gripper_response.result()
        if self.result_set_gripper != None:
            print("self.success True")
            self.success = True
            self.result = self.result_set_gripper

    # Franka 그리퍼 콜백 정리
    def do_send_goal_gripper_action(self):
        self.send_goal_future_gripper_action = self.action_client_gripper_action.send_goal_async(self.request)
        self.send_goal_future_gripper_action.add_done_callback(self.callback_goal_response_gripper_action)

    def callback_goal_response_gripper_action(self, future):
        self.goal_handle_gripper_action = future.result()
        if self.goal_handle_gripper_action.accepted:
            self.node.get_logger().info('Goal accepted :)')
            self.get_result_future_gripper_action = self.goal_handle_gripper_action.get_result_async()
            self.get_result_future_gripper_action.add_done_callback(self.callback_get_result_gripper_action)
        else:
            self.node.get_logger().info('Control Goal rejected :(')

    def callback_get_result_gripper_action(self, future):
        # print(type(future.result()))
        # print(dir(future.result()))
        # print(future.result().status)
        result = future.result().result # 메시지의 result 부분 
        status = future.result().status # goal 의 status 부분 enum의 결과인 int 값을 가질 것을 추정하고 설계함.
        self.action_result_gripper_action = result
        self.action_status_gripper_action = status
        print("status == GoalStatus.STATUS_SUCCEEDED {}".format(status == GoalStatus.STATUS_SUCCEEDED))
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.success = True
            self.node.get_logger().info('Goal succeeded!')
        else:
            self.success = False
            self.node.get_logger().info('Goal failed!') #move error
        print("callback_get_result_gripper_action")