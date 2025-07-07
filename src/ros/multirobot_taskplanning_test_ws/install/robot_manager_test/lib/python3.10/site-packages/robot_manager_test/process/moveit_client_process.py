# ros 기본 모듈
import rclpy
import rclpy.node

# ros 메시지 타입
from geometry_msgs.msg import Pose
from moveit_proxy_interface.srv import SendPlan, ExecPlan, GetPose

# 파이썬 기본 모듈
import math
import enum

# 파이썬 사용자 정의 모듈
from robot_manager_state_transition.process.process import Process # 서브 프로세스 추상 클래스
from robot_manager_state_transition.robot_entity.robot import Robot

class MoveitClient(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        self.node = node_arg
        self.robot = robot_arg

        # <ros 기능 요소 선언>
        # do_plan service 선언
        self.cli_send_plan = self.node.create_client(SendPlan, 'moveit_proxy_send_plan')

        # do_exec service 선언
        self.cli_exec_plan = self.node.create_client(ExecPlan, 'moveit_proxy_exec_plan')

        # get_pose service 선언
        self.cli_get_pose = self.node.create_client(GetPose, 'moveit_proxy_get_pose')

        # <ros2 콜백 관리용 요소 정의>

        # 서비스 request 퓨쳐
        self.future_send_plan_request = None
        self.future_exec_plan_request = None
        self.future_get_pose_request = None

        # 서비스 result 퓨쳐
        self.future_send_plan_response = None
        self.future_exec_plan_response = None
        self.future_get_pose_response = None

        # 서비스 결과 변수
        self.result_send_plan = None
        self.result_exec_plan = None
        self.result_get_pose = None

        # 프로세스 상태 정의 (각 개별 프로세스마다 다르게 정의됨)
        class Process_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            # send plan
            request_send_plan = enum.auto()
            wait_ack_send_plan = enum.auto()#wait_acknowledgments
            working_send_plan = enum.auto()
            complete_send_plan = enum.auto()
            # exec plan
            request_exec_plan = enum.auto()
            wait_ack_exec_plan = enum.auto()#wait_acknowledgments
            working_exec_plan = enum.auto()
            complete_exec_plan = enum.auto()

            reset = enum.auto()
            error = enum.auto() # 오류를 처리중인 상태
            halt = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태
        
        # 프로세스 상태값 초기화
        self.process_state_enum = Process_state_enum
        self.process_state = self.process_state_enum.error.value

        self.request = Pose()

        # ros2 서비스 초기화
        while not self.cli_send_plan.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('moveit proxy service not available, waiting again...')

        while not self.cli_exec_plan.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('moveit proxy service not available, waiting again...')

        while not self.cli_get_pose.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('moveit proxy service not available, waiting again...')

        #서비스 초기화가 완료되면 ready 상태로 전이
        self.process_state = self.process_state_enum.ready.value

    # sub process 구성요소 정의
    # 추상 클래스 메서드 오버라이딩
    def do_assign_request(self, request_arg:Pose):
        # 기존 작업에 관련된 값을 초기화
        self.flag_job_completed = False
        self.flag_job_set = False
        self.success = False
        self.result = None

        self.do_reset_log()

        # 새로운 작업을 적용할 수 있는 상태인지 확인
        manipulator_properties = self.robot.get_manipulator_property_instance()
        if self.process_state == self.process_state_enum.ready.value:
            if manipulator_properties.get_state() == manipulator_properties.manipulator_state_enum.ready.value: 
                self.request = request_arg
                self.process_state = self.process_state_enum.request_send_plan.value
                self.flag_job_set = True
        
        return self.flag_job_set
            

    def do_execute(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request_send_plan.value:
            # print("request_send_plan")
            self.do_send_plan_rosmsg(self.request)# plan 요청
        elif self.process_state == self.process_state_enum.wait_ack_send_plan.value:
            ...
        elif self.process_state == self.process_state_enum.working_send_plan.value:
            ...
        elif self.process_state == self.process_state_enum.complete_send_plan.value:
            ...
        elif self.process_state == self.process_state_enum.request_exec_plan.value:
            # print("request_exec_plan")
            self.do_request_exec_plan()# 동작 요청
        elif self.process_state == self.process_state_enum.wait_ack_exec_plan.value:
            ...
        elif self.process_state == self.process_state_enum.working_exec_plan.value:
            ...
        elif self.process_state == self.process_state_enum.complete_exec_plan.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            # 서비스 request 퓨쳐
            self.future_send_plan_request = None
            self.future_exec_plan_request = None
            self.future_get_pose_request = None

            # 서비스 result 퓨쳐
            self.future_send_plan_response = None
            self.future_exec_plan_response = None
            self.future_get_pose_response = None

            # 서비스 결과 변수
            self.result_send_plan = None
            self.result_exec_plan = None
            self.result_get_pose = None

            # request 변수
            self.request = Pose()

        elif self.process_state == self.process_state_enum.error.value:
            ...
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_update(self) -> None:
        self.do_log_state_trasition()
        # print("self.process_state      : {}".format(self.process_state))
        # print("self.flag_job_completed : {}".format(self.flag_job_completed))
        # print("self.flag_job_set       : {}".format(self.flag_job_set))
        # print("self.result             : {}".format(self.result))
        
        manipulator_properties = self.robot.get_manipulator_property_instance()
        # ready
        if self.process_state == self.process_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
            if self.flag_job_set == True:# 요청이 확인된 경우 다음 단계로 넘어감
                self.process_state = self.process_state_enum.request_send_plan.value
            ... # 명령이 등록되지 않은 경우는 단순 대기함 뜀
        # request_send_plan
        elif self.process_state == self.process_state_enum.request_send_plan.value:
            self.process_state = self.process_state_enum.wait_ack_send_plan.value# send_goal을 수행했다면 acknowlegements 를 대기 
            # 변수들을 확인하여 send_goal 이 수행 완료되었다면 다음 상태로 넘어감
            # 변수들의 상태를 update에서 감시해주는 이유는 
            # callback에서 변수의 상태변화를 일으키는 경우가 매 실행마다 반영되도록 하기 위함이다.

            # 해당 분기에서는 goal handle을 통해 전달된 goal이 accept 되었는지 확인해야 한다.
            # goal이 accept 되었다면 상태를 working으로 전이하고
            # 만약 accept 되지 못했다면 상태를 error로 전이시켜야 한다.
        # wait_ack_send_plan
        elif self.process_state == self.process_state_enum.wait_ack_send_plan.value:
            # 변수 확인
            if self.future_send_plan_request is not None:
                self.process_state = self.process_state_enum.working_send_plan.value
                manipulator_properties.set_state(manipulator_properties.manipulator_state_enum.request.value)# 로봇의 상태를 request으로 변경
            else:
                self.process_state = self.process_state_enum.error.value
                # 서비스의 경우 퓨쳐가 어떠한 방식으로 예외처리를 하는지 확인되지 않음...
                # 현재 상황으로는 future 자체의 python 예외를 통하여 예외처리가 되는 것으로 생각됨.
                # ... 어차피 발생한 예외를 처리하지 못하면 시스템이 종료되니, 잘못된 수행을 걱정할 필요는 없을 지도... 
                # futue 객체 예외 목록 링크 참고자료
                # https://docs.python.org/ko/3/library/concurrent.futures.html#exception-classes

        # working_send_plan
        elif self.process_state == self.process_state_enum.working_send_plan.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self.future_send_plan_request is not None:
                if self.future_send_plan_request.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    if self.result_send_plan is not None:
                        if self.result_send_plan == True:
                            self.process_state = self.process_state_enum.complete_send_plan.value
                        else:
                            self.process_state = self.process_state_enum.error.value
        # complete_send_plan
        elif self.process_state == self.process_state_enum.complete_send_plan.value:
            # send plan 이 완료되면 exec plan 단계로 전이
            self.process_state = self.process_state_enum.request_exec_plan.value

        # request_exec_plan
        elif self.process_state == self.process_state_enum.request_exec_plan.value:
            self.process_state = self.process_state_enum.wait_ack_exec_plan.value# send_goal을 수행했다면 acknowlegements 를 대기 
            # 변수들을 확인하여 send_goal 이 수행 완료되었다면 다음 상태로 넘어감
            # 변수들의 상태를 update에서 감시해주는 이유는 
            # callback에서 변수의 상태변화를 일으키는 경우가 매 실행마다 반영되도록 하기 위함이다.

            # 해당 분기에서는 goal handle을 통해 전달된 goal이 accept 되었는지 확인해야 한다.
            # goal이 accept 되었다면 상태를 working으로 전이하고
            # 만약 accept 되지 못했다면 상태를 error로 전이시켜야 한다.
        # wait_ack_send_plan
        elif self.process_state == self.process_state_enum.wait_ack_exec_plan.value:
            # 변수 확인
            if self.future_exec_plan_request is not None:
                self.process_state = self.process_state_enum.working_exec_plan.value
                manipulator_properties.set_state(manipulator_properties.manipulator_state_enum.working.value)# 로봇의 상태를 request으로 변경
            else:
                self.process_state = self.process_state_enum.error.value
                # 서비스의 경우 퓨쳐가 어떠한 방식으로 예외처리를 하는지 확인되지 않음...
                # 현재 상황으로는 future 자체의 python 예외를 통하여 예외처리가 되는 것으로 생각됨.
                # ... 어차피 발생한 예외를 처리하지 못하면 시스템이 종료되니, 잘못된 수행을 걱정할 필요는 없을 지도... 
                # futue 객체 예외 목록 링크 참고자료
                # https://docs.python.org/ko/3/library/concurrent.futures.html#exception-classes

        # working_send_plan
        elif self.process_state == self.process_state_enum.working_exec_plan.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self.future_exec_plan_request is not None:
                if self.future_exec_plan_request.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    if self.result_exec_plan is not None:
                        if self.result_exec_plan == True:
                            self.process_state = self.process_state_enum.complete_exec_plan.value
                            manipulator_properties.set_state(manipulator_properties.manipulator_state_enum.complete.value)# 로봇의 상태를 working으로 변경
                            self.result = True
                        else:
                            self.process_state = self.process_state_enum.error.value
                            manipulator_properties.set_state(manipulator_properties.manipulator_state_enum.error.value)# 로봇의 상태를 working으로 변경
        # complete_send_plan
        elif self.process_state == self.process_state_enum.complete_exec_plan.value:
            # move_out의 경우 navigation 명령이 어지기 전에 대기시간이 필요하므로 action_transition 상태로 전이
            self.process_state = self.process_state_enum.reset.value
            # 다음에 수행되어야 할 액션으로 상태를 전이
            # self.process_state_move_control = self.process_state_enum.navigate_to_pose.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = True
        # reset
        elif self.process_state == self.process_state_enum.reset.value:
            # 각종 변수 및 상태를 초기화 한 후 ready 상태로 전이
            self.process_state = self.process_state_enum.ready.value
            manipulator_properties.set_state(manipulator_properties.manipulator_state_enum.ready.value)# 로봇의 상태를 ready으로 변경

        # error
        elif self.process_state == self.process_state_enum.error.value:
            # self.process_state_move_control = self.process_state_enum.error.value
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
        return complete_bool_rtn

    # ros 콜백 정의
    def do_request_send_plan(self, arg_goal_pose):
        # print("moveit_proxy_client_test")
        req_send_plan = SendPlan.Request()
        req_send_plan.goal_pose = arg_goal_pose
        self.future_send_plan_request = self.cli_send_plan.call_async(req_send_plan)
        # add done callback
        self.future_send_plan_request.add_done_callback(self.callback_send_plan_result)

    def callback_send_plan_result(self, future):
        self.future_send_plan_response = future # 메모리 상에서는 self.future_send_plan_request 와 같은 객체를 가리킬 것임.
        self.result_send_plan = self.future_send_plan_response.result().result

    def do_request_exec_plan(self):
        # print("moveit_proxy_client_test")
        req_exec_plan = ExecPlan.Request() # == Empty
        self.future_exec_plan_request = self.cli_exec_plan.call_async(req_exec_plan)
        # add done callback
        self.future_send_plan_request.add_done_callback(self.callback_exec_plan_result)

    def callback_exec_plan_result(self, future):
        self.future_exec_plan_response = future
        self.result_exec_plan = self.future_exec_plan_response.result().result
        ...

    def do_request_get_pose(self):
        # print("moveit_proxy_client_test")
        req_get_pose = GetPose.Request() # == Empty
        self.future_get_pose_request = self.cli_get_pose.call_async(req_get_pose)
        # add done callback
        self.future_send_plan_request.add_done_callback(self.callback_get_pose_result)

    def callback_get_pose_result(self, future):
        self.future_get_pose_response = future
        self.result_get_pose = GetPose.Response()
        result = self.future_get_pose_response.result()
        self.result_get_pose.pose.position.x = result.pose.position.x
        ...


    def do_send_plan_args(self, x, y, z, ox=0, oy=0, oz=0, ow=1):
        input_pose = Pose()
        input_pose.position.x = float(x)
        input_pose.position.y = float(y)
        input_pose.position.z = float(z)
        input_pose.orientation.x = float(ox)
        input_pose.orientation.y = float(oy)
        input_pose.orientation.z = float(oz)
        input_pose.orientation.w = float(ow)
        self.do_send_plan_rosmsg(input_pose)

    def do_send_plan_relative_args(self, x=0, y=0, z=0, ox=0, oy=0, oz=0, ow=0):
        input_displacement_pose = Pose()
        input_displacement_pose.position.x = float(x)
        input_displacement_pose.position.y = float(y)
        input_displacement_pose.position.z = float(z)
        input_displacement_pose.orientation.x = float(ox)
        input_displacement_pose.orientation.y = float(oy)
        input_displacement_pose.orientation.z = float(oz)
        input_displacement_pose.orientation.w = float(ow)

        self.do_send_plan_relative_rosmsg(input_displacement_pose)

    def do_send_plan_rosmsg(self, input_goal_pose: Pose):
        self.do_request_send_plan(input_goal_pose)

    def do_send_plan_relative_rosmsg(self, input_displacement_pose: Pose):
        goal_pose = Pose()
        current_pose = self.get_current_pose()

        goal_pose.position.x = current_pose.position.x + input_displacement_pose.position.x
        goal_pose.position.y = current_pose.position.y + input_displacement_pose.position.y
        goal_pose.position.z = current_pose.position.z + input_displacement_pose.position.z
        # goal_pose.orientation.x = current_pose.orientation.x + input_displacement_pose.orientation.x
        # goal_pose.orientation.y = current_pose.orientation.y + input_displacement_pose.orientation.y
        # goal_pose.orientation.z = current_pose.orientation.z + input_displacement_pose.orientation.z
        # goal_pose.orientation.w = current_pose.orientation.w + input_displacement_pose.orientation.w
        self.do_request_send_plan(goal_pose)

