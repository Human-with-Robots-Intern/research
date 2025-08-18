# ros 기본 모듈
import rclpy
import rclpy.node

# 파이썬 기본 모듈
import enum

# 사용자 정의 모듈
from robot_manager_state_transition.robot_entity.robot import Robot

class Process:
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        self.node = node_arg
        self.robot = robot_arg

        # 상태 관리 변수
        self.process_state:int = None
        self.process_state_enum:enum.Enum = None
        
        # 상태 로깅 변수
        self.process_state_old:int = None
        self.state_log:list = []

        # 흐름 관리를 위한 기타 변수
        self.flag_job_set:bool = False
        self.flag_job_completed:bool = False
        
        self.request = None
        
        self.success:bool = False
        self.result = None

    def do_assign_request(self, request_arg) -> bool:# 작업 설정의 성공 여부를 반환
        ...
        raise NotImplementedError
        
    def do_execute(self) -> None:
        ...
        raise NotImplementedError

    def do_update(self) -> None:
        ...
        raise NotImplementedError

    def do_check_completion(self) -> bool:
        ...
        raise NotImplementedError

    def get_success(self):
        return self.success

    def get_result(self):
        return self.result

    def do_log_state_trasition(self):
        # 상태 전이 로깅
        if self.process_state != self.process_state_old:# 상태가 변화할 때 마다 값을 저장
            self.state_log.append(self.process_state)
            self.process_state_old = self.process_state

    def do_print_log(self):
        print("state_log : {}".format(self.state_log))

    def do_reset_log(self):
        self.state_log = []