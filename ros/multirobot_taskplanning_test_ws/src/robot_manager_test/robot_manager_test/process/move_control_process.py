# ros 기본 모듈
import rclpy
import rclpy.node
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ros 인터페이스 모듈
from robot_control_interface.action import ControlCommand

# 기본 파이썬 모듈
import enum
import time

# 사용자 정의 파이썬 모듈
from robot_manager_state_transition.process.process import Process
from robot_manager_state_transition.robot_entity.robot import Robot

class MoveControl(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        # <ros2 기능 요소 정의>
        self._action_client_move_control = ActionClient(self.node, ControlCommand, 'move_straight_control_action', callback_group=MutuallyExclusiveCallbackGroup())

        # <ros2 콜백 관리용 요소 정의>
        # 콜백 퓨쳐
        self._send_goal_future_move_control = None
        self._get_result_future_move_control = None

        # 콜백 핸들
        self.goal_handle_move_control = None

        # 콜백 결과
        self.action_result_move_control = None

        # 기타 상수 정의
        self.length_move_straghit = 0.5
        
        # 프로세스 상태 정의
        class Process_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            wait_action_transition = enum.auto()
            send_goal = enum.auto()
            wait_ack = enum.auto()#wait_acknowledgments
            working = enum.auto()
            complete = enum.auto()
            reset = enum.auto()
            error = enum.auto() # 오류를 처리중인 상태
            halt = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태
        
        self.process_state_enum:Process_state_enum = Process_state_enum
        self.process_state = self.process_state_enum.error.value

        class Request_type_enum(enum.Enum):
            move_out = enum.auto()
            move_in = enum.auto()

        self.request_type_enum:Request_type_enum = Request_type_enum
        self.request_type = None# 아직 요청이 전달되지 않은 대기 상태에서는 None 값으로 하여 비워둠

    # process 객체 정의
    def do_assign_request(self, request_arg:int) -> None:
        mobile_properties = self.robot.get_mobilebase_property_instance()
        self.request_type = request_arg

        self.flag_job_set = False
        self.flag_job_completed = False
        self.result = None

        if self.request_type == self.request_type_enum.move_out.value:
            if mobile_properties.get_state == mobile_properties.mobilebase_state_enum.danger_zone.value:
                self.process_state = self.process_state_enum.send_goal.value
            else:
                assert 0, "현재 주어진 명령을 수행할 수 없는 상태 입니다."
        elif self.request_type == self.request_type_enum.move_in.value:
            if mobile_properties.get_state == mobile_properties.mobilebase_state_enum.safe_zone.value:
                self.process_state = self.process_state_enum.send_goal.value
            else:
                assert 0, "현재 주어진 명령을 수행할 수 없는 상태 입니다."
        else:
            assert 0, "잘못된 타입의 명령 전달되었음"

    def do_execute(self) -> None:
                # if self.process_state_move_control == self.process_state_enum.init.value:
        #     ...
        #     # 오류 상태로 전이
        #     self.process_state_move_control = self.process_state_enum.error.value
        #     self.process_state_move_control = self.process_state_enum.error.value
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.wait_action_transition.value:
            ...# 완료 시간으로 부터 지정한 시간이 지날때 까지 대기
        elif self.process_state == self.process_state_enum.send_goal.value:
            # 명령 전달 전에 결과를 담을 변수 초기화
            self.action_result_move_control = None
            if self.request_type == self.request_type_enum.move_out.value:
                self.send_goal_move_control(-self.length_move_straghit) # 후진으로 빠져나오는 동작이므로 거리를 음수로 지정.
            if self.request_type == self.request_type_enum.move_in.value:
                self.send_goal_move_control(self.length_move_straghit) # 후진으로 빠져나오는 동작이므로 거리를 음수로 지정.
        elif self.process_state == self.process_state_enum.wait_ack.value:
            ...# 완료 될때까지 대기
        elif self.process_state == self.process_state_enum.working.value:
            ...# 완료 될때까지 대기
        elif self.process_state == self.process_state_enum.complete.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            # 완료 후에 값 초기화
            self._send_goal_future_move_control = None
            self._get_result_future_move_control = None
            self.goal_handle_move_control = None
            self.action_result_move_control = None

            self.request_type = None# 아직 요청이 전달되지 않은 대기 상태에서는 None 값으로 하여 비워둠

    def do_update(self) -> None:
        mobile_properties = self.robot.get_mobilebase_property_instance()
        # ready
        if self.process_state == self.process_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
            self.process_state = self.process_state_enum.send_goal.value# action_transition을 건너뛰고 바로 send_goal 상태로 전이
            ... # ready 상태인 경우는 명령이 등록되지 않은 상태이므로 건너 뜀
        # action_transition
            # move_out은 첫 시작 액션으로 액션과 액션 사이에 기다리는 시간이 불필요
        # send_goal
        elif self.process_state == self.process_state_enum.send_goal.value:
            self.process_state = self.process_state_enum.wait_ack.value# send_goal을 수행했다면 acknowlegements 를 대기 
            # 변수들을 확인하여 send_goal 이 수행 완료되었다면 다음 상태로 넘어감
            # 변수들의 상태를 update에서 감시해주는 이유는 
            # callback에서 변수의 상태변화를 일으키는 경우가 매 실행마다 반영되도록 하기 위함이다.

            # 해당 분기에서는 goal handle을 통해 전달된 goal이 accept 되었는지 확인해야 한다.
            # goal이 accept 되었다면 상태를 working으로 전이하고
            # 만약 accept 되지 못했다면 상태를 error로 전이시켜야 한다.
        # wait_ack
        elif self.process_state == self.process_state_enum.wait_ack.value:
            # 변수 확인
            if self.goal_handle_move_control is not None:
                if self.goal_handle_move_control.accepted == True: 
                    self.process_state = self.process_state_enum.working.value
                    mobile_properties.set_state(mobile_properties.mobilebase_state_enum.moving.value)# 로봇의 상태를 moving으로 변경
                else:
                    self.process_state = self.process_state_enum.error.value
        # working
        elif self.process_state == self.process_state_enum.working.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self._get_result_future_move_control is not None:
                if self._get_result_future_move_control.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    if self.action_result_move_control is not None:
                        if self.action_result_move_control == True:
                            self.process_state = self.process_state_enum.complete.value
                            mobile_properties.set_state(mobile_properties.mobilebase_state_enum.safe_zone.value)# 로봇의 상태를 moving으로 변경
                        else:
                            self.process_state = self.process_state_enum.error.value
        # complete
        elif self.process_state == self.process_state_enum.complete.value:
            # move_out의 경우 navigation 명령이 어지기 전에 대기시간이 필요하므로 action_transition 상태로 전이
            self.process_state = self.process_state_enum.reset.value
            # 다음에 수행되어야 할 액션으로 상태를 전이
            # self.process_state_move_control = self.process_state_enum.navigate_to_pose.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.result = True
        elif self.process_state == self.process_state_enum.reset.value:
            self.process_state = self.process_state_enum.ready.value
        # error
        elif self.process_state == self.process_state_enum.error.value:
            # self.process_state_move_control = self.process_state_enum.error.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.result = False

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
            self.result = False
        return complete_bool_rtn

    def get_result(self):
        ...
        raise NotImplementedError

    # ros 콜백 정의
    def send_goal_move_control(self, distance_target_arg:float):
        goal_request = ControlCommand.Goal()
        goal_request.control_target = distance_target_arg
        self._send_goal_future_move_control = self._action_client_move_control.send_goal_async(goal_request)
        self._send_goal_future_move_control.add_done_callback(self.goal_response_callback_move_control)

    def goal_response_callback_move_control(self, future):
        self.goal_handle_move_control = future.result()
        if self.goal_handle_move_control.accepted:
            self.node.get_logger().info('Goal accepted :)')
            self._get_result_future_move_control = self.goal_handle_move_control.get_result_async()
            self._get_result_future_move_control.add_done_callback(self.get_result_callback_move_control)
        else:
            self.node.get_logger().info('Control Goal rejected :(')

    def get_result_callback_move_control(self, future):
        result = future.result().result.result
        if result:
            self.node.get_logger().info('Goal succeeded!')
        else:
            self.node.get_logger().info('Goal failed!') #move error
        self.action_result_move_control = result
