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
import asyncio

# 사용자 정의 파이썬 모듈
from robot_manager_state_transition.process.process import Process
from robot_manager_state_transition.robot_entity.robot import Robot

class Nav2Client(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        self.node = node_arg
        self.robot = robot_arg

        # <ros2 기능 요소 정의>
        self._action_client_navigation = ActionClient(self.node, NavigateToPose, 'navigate_to_pose', callback_group=MutuallyExclusiveCallbackGroup())

        # <nav2_client action> 
        # action 퓨쳐 변수
        self.send_goal_future_navigation:asyncio.Future = None
        self.get_result_future_navigation:asyncio.Future = None
        # goal handle
        self.goal_handle_navigation = None
        # 액션 결과 변수
        self.action_result_navigation = None
        self.action_status_navigation = None

        # 기타 상수 정의
        self.length_move_straghit = 0.5

        # 프로세스 상태 정의
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
                # 프로세스 상태 정의 (각 개별 프로세스마다 다르게 정의됨)

        self.process_state_enum:Process_state_enum = Process_state_enum
        self.process_state:int = self.process_state_enum.error.value

        # 세부 request 변수 정의
        self.location_request:str = None
        self.coordinates_request:list = None

        # ros2 서비스 초기화
        while not self._action_client_navigation.wait_for_server(timeout_sec=1.0):
            self.node.get_logger().info('service not available, waiting again...')

        #서비스 초기화가 완료되면 ready 상태로 전이
        self.process_state = self.process_state_enum.ready.value

    # utility 함수 정의
    def get_coordinates_by_id(self, id_number:int, data_path:str):
        with open(data_path, 'r') as f:
            data = json.load(f)
        found = False
        coordinates = None
        for node in data['nodes']:
            if node['id'] == id_number:
                found = True
                location = node['location']
                coordinates = data['positions'][0][location]
                break
        if not found:
            print(f"ID '{id_number}' not found in the data.")
        return location, coordinates
    
    # process 객체 정의
    def do_assign_request(self, request_arg:Pose2D) -> None:
        mobile_properties = self.robot.get_mobilebase_property_instance()
        
        # job_accepted 
        self.flag_job_set = False
        self.flag_job_completed = False
        self.result = None

        self.do_reset_log()

        mobile_properties = self.robot.get_mobilebase_property_instance()
        robot_location = mobile_properties.get_location()
        mobilebase_state_enum = mobile_properties.get_state_enum_instance()

        data_path_dir = mobile_properties.get_data_dir_path()
        data_path = data_path_dir + "/instruction_position.json"
        
        self.location_request, self.coordinates_request = self.get_coordinates_by_id(self.request_arg.a, data_path)# find 명령의 경우 첫번 째 인자가 이동할 목표
        if self.task_sequence_state == self.process_state_enum.ready.value:# task 가 활성화 되어있는지 여부를 확인
            if mobile_properties.get_state() == mobilebase_state_enum.ready.value:
                # 이미 현재위치와 목적지가 같은 상태
                if robot_location == self.location_request:
                    self.request = request_arg
                    self.task_sequence_state = self.process_state_enum.complete.value
                    self.flag_job_set = True
                else:
                    self.request = request_arg
                    self.task_sequence_state = self.process_state_enum.request.value
                    self.flag_job_set = True
            else:
                self.task_sequence_state = self.process_state_enum.error.value
                self.flag_job_set = False
                # 차후 에러상태를 회복할 방법이 있는지도 생가해보고 가능하다면 구현해보기
                print("error")

        return self.flag_job_set

    def do_execute(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request.value:
            self.send_goal_navigation(self.request)
        elif self.process_state == self.process_state_enum.wait_ack.value:
            ...# 완료 될때까지 대기
        elif self.process_state == self.process_state_enum.working.value:
            ...# 완료 될때까지 대기
        elif self.process_state == self.process_state_enum.complete.value:
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = True
                self.robot.get_mobilebase_property_instance().set_location(self.location_request)

        elif self.process_state == self.process_state_enum.reset.value:
            # 완료 후에 값 초기화  
            # ros2 기능 요소 초기화          
            # action 퓨쳐 변수
            self.send_goal_future_navigation = None
            self.get_result_future_navigation = None
            # goal handle
            self.goal_handle_navigation = None
            # 액션 결과 변수
            self.action_result_navigation = None
            self.action_status_navigation = None

            # 객체 상태변수 초기화
            self.request = None
            self.location_request = None
            self.coordinates_request = None

    def do_update(self) -> None:
        # ready
        if self.process_state == self.process_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
            self.process_state = self.process_state_enum.request.value# action_transition을 건너뛰고 바로 send_goal 상태로 전이
            ... # ready 상태인 경우는 명령이 등록되지 않은 상태이므로 건너 뜀
        # action_transition
            # move_out은 첫 시작 액션으로 액션과 액션 사이에 기다리는 시간이 불필요
        # send_goal
        elif self.process_state == self.process_state_enum.request.value:
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
            if self.goal_handle_navigation is not None:
                if self.goal_handle_navigation.accepted == True: 
                    self.process_state = self.process_state_enum.working.value
                else:
                    self.process_state = self.process_state_enum.error.value
        # working
        elif self.process_state == self.process_state_enum.working.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self.get_result_future_navigation is not None:
                if self.get_result_future_navigation.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    if self.action_result_navigation is not None:
                        if self.action_result_navigation == True:
                            self.process_state = self.process_state_enum.complete.value
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
    def send_goal_navigation(self, pose_arg:Pose2D):
        goal_msg = NavigateToPose.Goal()
        PoseStamped_msg = PoseStamped()
        PoseStamped_msg.pose.position.x = pose_arg.x
        PoseStamped_msg.pose.position.y = pose_arg.y
        PoseStamped_msg.pose.position.z = 0.0
        roll = 0.0
        pitch = 0.0
        yaw = pose_arg.theta
        quaternion = transforms3d.euler.euler2quat(roll, pitch, yaw)
        orientation_x = quaternion[0]
        orientation_y = quaternion[1]
        orientation_z = quaternion[2]
        orientation_w = quaternion[3]
        PoseStamped_msg.pose.orientation.w = orientation_w
        PoseStamped_msg.pose.orientation.x = orientation_x
        PoseStamped_msg.pose.orientation.y = orientation_y
        PoseStamped_msg.pose.orientation.z = orientation_z
        PoseStamped_msg.header.frame_id = 'map'
        goal_msg._pose = PoseStamped_msg
        self._send_goal_future_navigation = self._action_client_navigation.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback)
        self._send_goal_future_navigation.add_done_callback(self.goal_response_navigation)
    
    def goal_response_navigation(self, future:asyncio.Future):
        self.goal_handle_navigation = future.result()
        if self.goal_handle_navigation.accepted:
            self.node.get_logger().info('Goal accepted :)')
            self._get_result_future_navigation = self.goal_handle_navigation.get_result_async()
            self._get_result_future_navigation.add_done_callback(self.get_result_callback_navigation)
        else:
            self.node.get_logger().info('Nav Goal rejected :(')


    def get_result_callback_navigation(self, future):
        result = future.result().result
        status = future.result().status
        
        self.node.get_logger().info('Result: {0}'.format(status))
        self.action_status_navigation = status
        self.action_result_navigation = result

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback.distance_remaining
        self.node.get_logger().info('Received distance remaining: {0}'.format(feedback))
