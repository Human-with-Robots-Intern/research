# ros2 기본 요소 모듈
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

# ros2 사용자 정의 인터페이스 모듈
from robot_manager_interface.srv import RobotManager
from geometry_msgs.msg import Pose
from std_msgs.msg import Empty
from control_msgs.action import GripperCommand

# 기본 파이썬 모듈
import enum

# 사용자 정의 파이썬 모듈
from robot_manager_state_transition.robot_entity.robot_mobile_manipulator import Robot_mobile_manipulator
from robot_manager_state_transition.process.process import Process
from robot_manager_state_transition.process.moveit_client_process import MoveitClient
from robot_manager_state_transition.process.object_detector_process import ObjectDetector 
from robot_manager_state_transition.process.gripper_client_process import GripperClient 

class Process_test_server(Node):

    def __init__(self):
        super().__init__('robot_manager_server')
        self.srv = self.create_service(RobotManager, 'robot_command', self.do_execute_job, callback_group=MutuallyExclusiveCallbackGroup())
        
        # 로봇 객체 초기화
        self.robot = Robot_mobile_manipulator()
        self.robot.set_name("husky")
        self.robot.set_type("mobile_manipulator")
        self.robot.set_enable_robot()

        self.worker_properties = self.robot.get_worker_property_instance()
        self.job_state_enum = self.worker_properties.job_state_enum
        self.worker_properties.set_state(self.job_state_enum.ready.value) 

        self.mobilebase_properties = self.robot.get_mobilebase_property_instance()
        self.mobilebase_state_enum = self.mobilebase_properties.mobilebase_state_enum
        self.mobilebase_properties.set_state(self.mobilebase_state_enum.safe_zone.value)

        self.manipulatior_properties = self.robot.get_manipulator_property_instance()
        self.manipulator_state_enum = self.manipulatior_properties.manipulator_state_enum
        self.manipulatior_properties.set_state(self.manipulator_state_enum.ready.value) 

        self.gripper_properties = self.robot.get_gripper_property_instance()
        self.gripper_state_enum = self.gripper_properties.gripper_state_enum
        self.gripper_properties.set_state(self.gripper_state_enum.ready.value)
        # 그리퍼 타입 설정
        self.gripper_properties.set_gripper_type(self.gripper_properties.gripper_type_enum.robotiq.value)
        # self.gripper_properties.set_gripper_type(self.gripper_properties.gripper_type_enum.panda.value)

        self.camera_properties = self.robot.get_detector_property_instance()
        self.camera_state_enum = self.camera_properties.camera_state_enum
        self.camera_properties.set_state(self.camera_state_enum.ready.value)

        # 개별 프로세스 객체 초기화
        # self.moveit_client_process = MoveitClient(self, self.robot)# find 하나만 먼저 초기화
        # self.object_detector_process = ObjectDetector(self, self.robot)# find 하나만 먼저 초기화
        self.gripper_client_process = GripperClient(self, self.robot)
        # 사용자 변수 정의
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_result = None

        self.process_entity = None

        print("robot is ready")

    def do_execute_job(self, request:RobotManager.Request, response:RobotManager.Response):
        print("do_execute_job")
        self.process_entity = self.get_process_entity(request)
        self.process_entity.do_reset_log()
        self.do_assign_task(self.process_entity, request)
        while True:
            self.do_execute_task(self.process_entity)
            self.do_update_job_state(self.process_entity)
            if self.do_check_completion() == True:
                self.process_entity.do_print_log()
                break
                
        response.success = self.get_result()
        return response

    def get_process_entity(self, request:RobotManager.Request) -> Process:
        process_entity_rtn = None
        if request.instruction == 1:
            process_entity_rtn = self.moveit_client_process
        elif request.instruction == 2:
            process_entity_rtn = self.object_detector_process
        elif request.instruction == 3:
            process_entity_rtn = self.gripper_client_process
        return process_entity_rtn

    def get_request_data(self, request_arg:RobotManager.Request):
        if request_arg.instruction == 1:
            if request_arg.a == 0:
                request_data = Pose()
                request_data.position.x = 0.02364812049874723
                request_data.position.y = 0.023975777870172386
                request_data.position.z = 0.6169407016125963
                request_data.orientation.x = 0.9227398404429652
                request_data.orientation.y = -0.3853978331340968
                request_data.orientation.z = -0.0033495265149815906
                request_data.orientation.w = 0.002911657081366515
            else:
                request_data = Pose()
                request_data.position.x = 0.0820556379122898
                request_data.position.y = 0.0
                request_data.position.z = 0.9394492158040775
                request_data.orientation.x = 0.8856628254535612
                request_data.orientation.y = -0.3726193209874958
                request_data.orientation.z = 0.2553469033917659
                request_data.orientation.w = -0.10749027939617793
        elif request_arg.instruction == 2:
            request_data = Empty()
        elif request_arg.instruction == 3:
            if request_arg.a == 0:# close
                request_data = GripperCommand.Goal()
                request_data.command.position = 0.00
                request_data.command.max_effort = 0.0
            elif request_arg.a == 1:# open
                request_data = GripperCommand.Goal()
                request_data.command.position = 0.04
                request_data.command.max_effort = 0.0
            elif request_arg.a == 2:# hold 0.02
                request_data = GripperCommand.Goal()
                request_data.command.position = 0.02
                request_data.command.max_effort = 0.0
        return request_data

    def do_assign_task(self, process_entity:Process, request_arg:RobotManager.Request):
        print("task_assigning")
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_result = None

        request = self.get_request_data(request_arg)

        job_state = self.worker_properties.get_state()
        print("task_assigning")
        print("job_state : {}".format(job_state))
        if job_state == self.job_state_enum.ready.value:
            print("requset_task")
            self.flag_job_set = process_entity.do_assign_request(request)
            self.worker_properties.set_state(self.job_state_enum.request.value)# task가 할당되어 작업상태로 상태 변화
            print("self.flag_job_set : {}".format(self.flag_job_set))
            if self.flag_job_set == True:
                self.worker_properties.set_state(self.job_state_enum.request.value)
            else:
                self.worker_properties.set_state(self.job_state_enum.error.value)
        print(self.worker_properties.get_state())

        return self.flag_job_set

    def do_execute_task(self, process_entity:Process):
        job_state = self.worker_properties.get_state()
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            ...
        elif job_state == self.job_state_enum.working.value:
            ...
            process_entity.do_execute()
        elif job_state == self.job_state_enum.complete.value:
            self.flag_job_complete = True
            self.job_result = True
            ...
        elif job_state == self.job_state_enum.error.value:
            self.flag_job_complete = True
            self.job_result = False
            ...

    def do_update_job_state(self, process_entity:Process):
        job_state = self.worker_properties.get_state()
        
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            if self.flag_job_set == True:
                self.worker_properties.set_state(self.job_state_enum.working.value)
        elif job_state == self.job_state_enum.working.value:
            process_entity.do_update()
            if process_entity.do_check_completion() == True:
                print("process_entity.get_success() {}".format(process_entity.get_success()))
                if process_entity.get_success() == True:
                    self.worker_properties.set_state(self.job_state_enum.complete.value)
                else:
                    self.worker_properties.set_state(self.job_state_enum.error.value)
        elif job_state == self.job_state_enum.complete.value:
            self.worker_properties.set_state(self.job_state_enum.ready.value)
        elif job_state == self.job_state_enum.error.value:
            job_state = self.job_state_enum.halt.value
            print("robot_mananger error 발생")
            # assert 0, "error 발생"
        elif job_state == self.job_state_enum.halt.value:
            ...
            print("robot_mananger Halt 상태")
        ...
    
    def do_check_completion(self):
        job_complete_rtn = False
        job_state = self.robot.get_worker_property_instance().get_state()
        
        if job_state == self.job_state_enum.ready.value or job_state == self.job_state_enum.error.value:
            if self.flag_job_set == True:
                if self.flag_job_complete == True:
                    job_complete_rtn = True
                    self.flag_job_set = False
                    self.flag_job_complete = False
                    if job_state == self.job_state_enum.error.value:
                        self.robot.get_worker_property_instance().set_state(self.job_state_enum.halt.value)
        if job_state == self.job_state_enum.halt.value:
            job_complete_rtn = True
            self.job_result = False
        return job_complete_rtn

    def get_result(self):
        return self.job_result

def main():
    rclpy.init()
    node = Process_test_server()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        node.get_logger().info("Starting server node, shut down with CTRL-C")
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.\n')
        node.process_entity.do_print_log()
    executor.remove_node(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()