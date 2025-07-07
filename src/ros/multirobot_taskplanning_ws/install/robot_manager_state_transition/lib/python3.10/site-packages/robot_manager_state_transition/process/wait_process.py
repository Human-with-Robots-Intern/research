# ros 기본 모듈
import rclpy
import rclpy.node
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ros 인터페이스 모듈
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Pose2D
from geometry_msgs.msg import Pose
from action_msgs.msg import GoalStatus

# 기본 파이썬 모듈
import enum
import time
import transforms3d
import json

# 사용자 정의 파이썬 모듈
from robot_manager_state_transition.process.process import Process
from robot_manager_state_transition.robot_entity.robot import Robot


class Wait(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        waitting_time = 0

        # 프로세스 상태 정의 (각 개별 프로세스마다 다르게 정의됨)
        class Process_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            request = enum.auto()# 굳이 필요한가?
            working = enum.auto()
            complete = enum.auto()
            reset = enum.auto()
            error = enum.auto() # 오류를 처리중인 상태
            halt = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태
        
        # 프로세스 상태값 초기화
        self.process_state_enum = Process_state_enum
        self.process_state = self.process_state_enum.ready.value


    def do_assign_request(self, request_arg:float) -> bool:# 작업 설정의 성공 여부를 반환
        self.flag_job_set = True
        self.flag_job_completed = False

        waitting_time = request_arg
        self.process_state = self.process_state_enum.working.value
        return self.flag_job_set
        
    def do_execute(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request.value:
            ...
        elif self.process_state == self.process_state_enum.working.value:
            ...
        elif self.process_state == self.process_state_enum.complete.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            ...
        elif self.process_state == self.process_state_enum.error.value:
            ...
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_update(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request.value:
            ...
        elif self.process_state == self.process_state_enum.working.value:
            ...
        elif self.process_state == self.process_state_enum.complete.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            ...
        elif self.process_state == self.process_state_enum.error.value:
            ...
        elif self.process_state == self.process_state_enum.halt.value:
            ...


    def do_check_completion(self) -> bool:
        ...
        raise NotImplementedError