# ros2 기본 모듈
import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

# ros2 기본 인터페이스
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped

# 사용자 정의 인터페이스
from robot_control_interface.action import MoveStraight
from robot_manager_interface.srv import RobotManager

# 파이썬 기본 모듈
import math
import json
import time
import enum

# 파이썬 외부 모듈
from tf_transformations import quaternion_from_euler
# 해당 모듈 오류가 있는 좌표 변환 모듈이었던 것으로 확인됨 차후 다른 모듈로 교체하기 - 2024-0910-1122

# 파이썬 사용자 정의 모듈
from robot_manager.robot_manager_kimz1121.robot_entity.robot import Robot

class FindTask:
    def __init__(self, node_arg:rclpy.Node, robot_arg:Robot):
        self.robot = robot_arg
        self.node = node_arg

        # <ros2 기능 요소 정의>
        self._action_client_navigation = ActionClient(self.node, NavigateToPose, 'navigate_to_pose', callback_group=MutuallyExclusiveCallbackGroup())
        self._action_client_move_control = ActionClient(self.node, MoveStraight, 'move_straight_control_action', callback_group=MutuallyExclusiveCallbackGroup())

        # <ros2 콜백 관리용 요소 정의>
        # 콜백 퓨쳐
        self._send_goal_future_navigation = None
        self._send_goal_future_move_control = None

        self._get_result_future_navigation = None
        self._get_result_future_move_control = None
        # 콜백 핸들
        self.goal_handle_navigation = None
        self.goal_handle_move_control = None

        # 콜백 결과
        self.action_result_move_control = None
        self.action_result_navigation = None
        
        # <사용자 정의 객체 선언>
        class Find_task_sequence_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            move_straight_out = enum.auto()
            move_straight_in = enum.auto()
            navigate_to_pose = enum.auto()
            complete = enum.auto()
            error = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태

        class Action_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            wait_action_transition = enum.auto()
            send_goal = enum.auto()
            wait_ack = enum()#wait_acknowledgments
            working = enum.auto()
            complete = enum.auto()
            erorr = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태

        self.task_sequence_state_enum = Find_task_sequence_state_enum
        self.task_sequence_state = self.task_sequence_state_enum.init.value

        self.action_state_enum = Action_state_enum
        self.action_state_navigation = self.action_state_enum.init.value
        self.action_state_move_control = self.action_state_enum.init.value

        self.task_sequence_state_old = None
        self.state_log_task_sequence = []# 빈 배열을 선언

        self.request = None # 전달된 요청 사항은 비워둔 상태로 초기화
        self.location_request = None
        self.coordinates_request = None

        self.length_move_straghit = 0.25

        self.duration_action_transition = 2 * 1000000# 2초를 nano sec 단위로 표현
        self.time_action_completed = None


        # 초기화 실행 문
        if self.robot.get_mobilebase_property_instance().get_is_enabled() == False:
            assert 0, "로봇에 이동 속성이 없거나 활성화 되지 않았습니다."

        # 액션 서버가 준비 되어있는지 확인
        wait_nav_action = self._action_client_navigation.wait_for_server(10)
        wait_move_action = self._action_client_move_control.wait_for_server(10)

        if wait_nav_action and wait_move_action == True:
            self.action_state_navigation = self.action_state_enum.ready.value
            self.action_state_move_control = self.action_state_enum.ready.value
            self.task_sequence_state = self.task_sequence_state_enum.ready.value
            # 액션 서버가 준비되어 있다면 task 또한 준비 상태로 변경

    def get_coordinates_by_id(self, id_number:int):
        with open('planner_instruction/instruction_position.json', 'r') as f:
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

    def set_request(self, request_arg:RobotManager.Request):
        # 첫 명령을 전달 받을 때 상태를 지정해 주는 역할
        self.request = request_arg
        # job_accepted 
        flag_job_set = False

        mobile_properties = self.robot.get_mobilebase_property_instance()
        mobile_state = mobile_properties.get_state()
        robot_location = mobile_properties.get_location()
        # job_properties = self.robot.get_worker_property_instance()
        # job_state = job_properties.get_state()

        self.location_request, self.coordinates_request = self.get_coordinates_by_id(self.request.a)# find 명령의 경우 첫번 째 인자가 이동할 목표
        

        if self.task_sequence_state == self.task_sequence_state_enum.ready.value:# task 가 활성화 되어있는지 여부를 확인
            if robot_location == self.location_request:
                self.task_sequence_state = self.task_sequence_state_enum.complete.value
                flag_job_set = True
            else:
                if mobile_state == mobile_properties.mobilebase_state_enum.safe_zone.value:# 로봇의 상태를 확인하여 수행하야할 작업을 결정
                    # 안전지대에서 출발할 경우 naviagtion 을 바로 수행
                    self.task_sequence_state = self.task_sequence_state_enum.navigate_to_pose.value
                    # 명령이 지정되었음을 표시
                    flag_job_set = True

                if mobile_state == mobile_properties.mobilebase_state_enum.danger_zone.value:# 로봇의 상태를 확인하여 수행하야할 작업을 결정
                    # 안전지대에서 출발할 경우 naviagtion 을 바로 수행
                    self.task_sequence_state = self.task_sequence_state_enum.move_straight_out.value
                    # 명령이 지정되었음을 표시
                    flag_job_set = True
                else:# 로봇이 정지해 있는 2가지 상태 이외의 상태에서 명령이 전달되면 에러 상태로 전이
                    self.task_sequence_state = self.task_sequence_state_enum.error.value
                    flag_job_set = False
                    # 차후 에러상태를 회복할 방법이 있는지도 생가해보고 가능하다면 구현해보기

        # 성공적으로 명령이 등록되었다면 로봇의 상태를 작업중으로 표현하고 이는 변수로써 리턴한다.
        # self.robot.get_worker_property_instance().set_state(job_properties.job_state_enum.request.value)
        # job state의 관리는 task의 영역이 아니라 robot_manager의 역할

        return flag_job_set

    def do(self):

        if self.task_sequence_state == self.task_sequence_state_enum.init.value:# task 가 활성화 되어있는지 여부를 확인
            # assert 0, "task가 정상적으로 초기화되지 못 했습니다."
            self.task_sequence_state = self.task_sequence_state_enum.error.value
        elif self.task_sequence_state == self.task_sequence_state_enum.ready.value:
            ...# 실행 무시
        elif self.task_sequence_state == self.task_sequence_state_enum.move_straight_out.value:
            # if self.action_state_move_control == self.action_state_enum.init.value:
            #     ...
            #     # 오류 상태로 전이
            #     self.task_sequence_state = self.task_sequence_state_enum.error.value
            #     self.action_state_move_control = self.action_state_enum.erorr.value
            if self.action_state_move_control == self.action_state_enum.ready.value:
                ...
            elif self.action_state_move_control == self.action_state_enum.wait_action_transition.value:
                ...# 완료 시간으로 부터 지정한 시간이 지날때 까지 대기
            elif self.action_state_move_control == self.action_state_enum.send_goal.value:
                self.send_goal_move_control(-self.length_move_straghit) # 후진으로 빠져나오는 동작이므로 거리를 음수로 지정.
            elif self.action_state_move_control == self.action_state_enum.wait_ack.value:
                ...# 완료 될때까지 대기
            elif self.action_state_move_control == self.action_state_enum.working.value:
                ...# 완료 될때까지 대기
            elif self.action_state_move_control == self.action_state_enum.complete.value:
                # 완료 후에 완료 시간 기록
                self.time_action_completed = time.time_ns()
        elif self.task_sequence_state == self.task_sequence_state_enum.move_straight_in.value:
            if self.action_state_move_control == self.action_state_enum.ready.value:
                ...
            elif self.action_state_move_control == self.action_state_enum.wait_action_transition.value:
                ...# 완료 시간으로 부터 지정한 시간이 지날때 까지 대기
            elif self.action_state_move_control == self.action_state_enum.send_goal.value:
                self.send_goal_move_control(self.length_move_straghit) # 후진으로 빠져나오는 동작이므로 거리를 음수로 지정.
            elif self.action_state_move_control == self.action_state_enum.wait_ack.value:
                ...# 완료 될때까지 대기
            elif self.action_state_move_control == self.action_state_enum.working.value:
                ...# 완료 될때까지 대기
            elif self.action_state_move_control == self.action_state_enum.complete.value:
                ...# move in 의경우 action_transition 상태를 활용하지 않으므로 시간을 별도로 저장할 필요가 없다.
                # 완료 후에 완료 시간 기록
                # self.time_action_completed = time.time_ns()
        elif self.task_sequence_state == self.task_sequence_state_enum.navigate_to_pose.value:
            if self.action_state_navigation == self.action_state_enum.ready.value:
                ...
            elif self.action_state_navigation == self.action_state_enum.wait_action_transition.value:
                ...# 완료 시간으로 부터 지정한 시간이 지날때 까지 대기
            elif self.action_state_navigation == self.action_state_enum.send_goal.value:
                yaw = self.coordinates_request[2]
                x = self.coordinates_request[0] - (self.length_move_straghit)*(math.cos(yaw))
                y = self.coordinates_request[1] - (self.length_move_straghit)*(math.sin(yaw))
                self.send_goal_navigation(x, y, yaw) # 후진으로 빠져나오는 동작이므로 거리를 음수로 지정.
            elif self.action_state_navigation == self.action_state_enum.wait_ack.value:
                ...# 완료 될때까지 대기
            elif self.action_state_navigation == self.action_state_enum.working.value:
                ...# 완료 될때까지 대기
            elif self.action_state_navigation == self.action_state_enum.complete.value:
                # 완료 후에 완료 시간 기록
                self.time_action_completed = time.time_ns()
        elif self.task_sequence_state == self.task_sequence_state_enum.complete.value:
            ...# 액션이 완전히 완료된 경우 상태관리를 제외한 각종 변수를 초기화
            self.state_log_task_sequence = []# 빈 배열을 선언
            self.request = None # 전달된 요청 사항은 비워둔 상태로 초기화
            self.location_request = None
            self.coordinates_request = None
            self.time_action_completed = None

            self._send_goal_future_navigation = None
            self._send_goal_future_move_control = None
            self._get_result_future_navigation = None
            self._get_result_future_move_control = None
            self.goal_handle_navigation = None
            self.goal_handle_move_control = None
            self.action_result_move_control = None
            self.action_result_navigation = None


    def do_update_state(self):
        # 주기적으로 변수들의 상태를 확인하여 
        # 흐름제어를 결정하는 역할
        mobile_properties = self.robot.get_mobilebase_property_instance()
        job_properties = self.robot.get_worker_property_instance()

        mobile_state = mobile_properties.get_state()
        job_state = job_properties.get_state()

        flag_task_complete = False

        # 상태 전이 로깅
        if self.task_sequence_state != self.task_sequence_state_old:# 상태가 변화할 때 마다 값을 저장
            self.state_log_task_sequence.append(self.task_sequence_state)
            task_sequence_state_old = self.task_sequence_state

        if self.task_sequence_state == self.task_sequence_state_enum.init.value:
            ... # 초기화가 끝나지 않은 상태라면 실행 무시
        elif self.task_sequence_state != self.task_sequence_state_enum.ready.value:
            ... # ready 상태인 경우는 명령이 등록되지 않은 상태이므로 건너 뜀
        # move_straight_out
        elif self.task_sequence_state == self.task_sequence_state_enum.move_straight_out.value:
            ... # task_sequence_state 확인 이후에는 action state 를 확인 및 상태 전이 제어
            # ready
            if self.action_state_move_control == self.action_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
                self.action_state_move_control = self.action_state_enum.send_goal.value# action_transition을 건너뛰고 바로 send_goal 상태로 전이
                ... # ready 상태인 경우는 명령이 등록되지 않은 상태이므로 건너 뜀
            # action_transition
                # move_out은 첫 시작 액션으로 액션과 액션 사이에 기다리는 시간이 불필요
            # send_goal
            elif self.action_state_move_control == self.action_state_enum.send_goal.value:
                self.action_result_move_control = self.action_state_enum.wait_ack.value# send_goal을 수행했다면 acknowlegements 를 대기 
                # 변수들을 확인하여 send_goal 이 수행 완료되었다면 다음 상태로 넘어감
                # 변수들의 상태를 update에서 감시해주는 이유는 
                # callback에서 변수의 상태변화를 일으키는 경우가 매 실행마다 반영되도록 하기 위함이다.

                # 해당 분기에서는 goal handle을 통해 전달된 goal이 accept 되었는지 확인해야 한다.
                # goal이 accept 되었다면 상태를 working으로 전이하고
                # 만약 accept 되지 못했다면 상태를 error로 전이시켜야 한다.
            # wait_ack
            elif self.action_state_move_control == self.action_state_enum.wait_ack.value:
                # 변수 확인
                if self.goal_handle_move_control.accepted == True and self._get_result_future_move_control is not None:
                    self.action_state_move_control = self.action_state_enum.working.value
            # working
            elif self.action_state_move_control == self.action_state_enum.working.value:
                # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
                if self._get_result_future_move_control.done() == True and self.action_result_move_control is not None:
                    self.action_state_move_control = self.action_state_enum.complete.value
            # complete
            elif self.action_state_move_control == self.action_state_enum.complete.value:
                # move_out의 경우 navigation 명령이 어지기 전에 대기시간이 필요하므로 action_transition 상태로 전이
                self.action_state_move_control = self.action_state_enum.ready.value
                # 다음에 수행되어야 할 액션으로 상태를 전이
                self.task_sequence_state = self.task_sequence_state_enum.navigate_to_pose.value
        # navigate_to_pose
        elif self.task_sequence_state == self.task_sequence_state_enum.navigate_to_pose.value:
                        # ready
            if self.action_state_navigation == self.action_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
                self.action_state_navigation = self.action_state_enum.wait_action_transition.value
            # action_transition
            elif self.action_state_navigation == self.action_state_enum.wait_action_transition.value:
                if self.time_action_completed - time.time_ns() > self.duration_action_transition:
                    self.action_state_navigation = self.action_state_enum.send_goal.value
            # send_goal
            elif self.action_state_navigation == self.action_state_enum.send_goal.value:
                self.action_result_move_control = self.action_state_enum.wait_ack.value
            # wait_ack
            elif self.action_state_navigation == self.action_state_enum.wait_ack.value:
                # 변수 확인
                if self.goal_handle_move_control.accepted == True and self._get_result_future_move_control is not None:
                    self.action_state_navigation = self.action_state_enum.working.value
            # working
            elif self.action_state_navigation == self.action_state_enum.working.value:
                # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
                if self._get_result_future_move_control.done() == True and self.action_result_move_control is not None:
                    self.action_state_navigation = self.action_state_enum.complete.value
            # complete
            elif self.action_state_navigation == self.action_state_enum.complete.value:
                # move_out의 경우 navigation 명령이 어지기 전에 대기시간이 필요하므로 action_transition 상태로 전이
                self.action_state_navigation = self.action_state_enum.ready.value
                # 다음에 수행되어야 할 액션으로 상태를 전이
                self.task_sequence_state = self.task_sequence_state_enum.move_straight_in.value
        # move_straight_in
        elif self.task_sequence_state == self.task_sequence_state_enum.move_straight_in.value:
            # ready
            if self.action_state_move_control == self.action_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
                self.action_state_move_control = self.action_state_enum.wait_action_transition.value
            # action_transition
            elif self.action_state_move_control == self.action_state_enum.wait_action_transition.value:
                if self.time_action_completed - time.time_ns() > self.duration_action_transition:
                    self.action_state_move_control = self.action_state_enum.send_goal.value
            # send_goal
            elif self.action_state_move_control == self.action_state_enum.send_goal.value:
                self.action_result_move_control = self.action_state_enum.wait_ack.value
            # wait_ack
            elif self.action_state_move_control == self.action_state_enum.wait_ack.value:
                # 변수 확인
                if self.goal_handle_move_control.accepted == True and self._get_result_future_move_control is not None:
                    self.action_state_move_control = self.action_state_enum.working.value
            # working
            elif self.action_state_move_control == self.action_state_enum.working.value:
                # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
                if self._get_result_future_move_control.done() == True and self.action_result_move_control is not None:
                    self.action_state_move_control = self.action_state_enum.complete.value
            # complete
            elif self.action_state_move_control == self.action_state_enum.complete.value:
                # move_out의 경우 navigation 명령이 어지기 전에 대기시간이 필요하므로 action_transition 상태로 전이
                self.action_state_move_control = self.action_state_enum.ready.value
                # 모든 액션이 종료되면 complete 상태로 전이
                self.task_sequence_state = self.task_sequence_state_enum.complete.value

        elif self.task_sequence_state == self.task_sequence_state_enum.complete.value:
            flag_task_complete = True# task가 완료 된 상태인 단한번의 상태에서 true를 반환하도록 한다.
            self.task_sequence_state = self.task_sequence_state_enum.ready.value
        elif self.task_sequence_state == self.task_sequence_state_enum.error.value:
            flag_task_complete = False# task가 완료 된 상태인 단한번의 상태에서 true를 반환하도록 한다.
            self.task_sequence_state = self.task_sequence_state_enum.ready.value
            # 에러 상태가 되면 기존까지의 상태 전이 과정을 출력
            print("error occured")
            print(self.state_log_task_sequence)

        return flag_task_complete

    def send_goal_navigation(self, x, y, yaw):
        goal_msg = NavigateToPose.Goal()
        PoseStamped_msg = PoseStamped()
        PoseStamped_msg.pose.position.x = x
        PoseStamped_msg.pose.position.y = y
        PoseStamped_msg.pose.position.z = 0.0
        roll = 0.0; pitch = 0.0
        quaternion = quaternion_from_euler(roll, pitch, yaw)
        ori_x = quaternion[0]
        ori_y = quaternion[1]
        ori_z = quaternion[2]
        ori_w = quaternion[3]
        PoseStamped_msg.pose.orientation.w = ori_w
        PoseStamped_msg.pose.orientation.x = ori_x
        PoseStamped_msg.pose.orientation.y = ori_y
        PoseStamped_msg.pose.orientation.z = ori_z
        PoseStamped_msg.header.frame_id = 'map'
        goal_msg._pose = PoseStamped_msg
        self._action_client_navigation.wait_for_server(10)
        self._send_goal_future_navigation = self._action_client_navigation.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback)
        self._send_goal_future_navigation.add_done_callback(self.goal_response_navigation)
    
    def goal_response_navigation(self, future):
        self.goal_handle_navigation = future.result()
        if self.goal_handle_navigation.accepted:
            self.node.get_logger().info('Goal accepted :)')
            self._get_result_future_navigation = self.goal_handle_navigation.get_result_async()
            self._get_result_future_navigation.add_done_callback(self.get_result_callback_navigation)
        else:
            self.node.get_logger().info('Nav Goal rejected :(')


    def get_result_callback_navigation(self, future):
        result = future.result().result
        self.node.get_logger().info('Result: {0}'.format("END"))
        self.action_result_navigation = result

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback.distance_remaining
        self.node.get_logger().info('Received distance remaining: {0}'.format(feedback))

    def send_goal_move_control(self, distance_target_arg:float):
        goal_request = MoveStraight.Goal()
        goal_request.distance_target = distance_target_arg
        self._action_client_move_control.wait_for_server(10)
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
        result = future.result().result
        if result:
            self.node.get_logger().info('Goal succeeded!')
        else:
            self.node.get_logger().info('Goal failed!') #move error
        self.action_result_move_control = result
