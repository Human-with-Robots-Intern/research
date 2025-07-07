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
from robot_manager_state_transition.robot_entity.robot_mobilebase import Robot_mobilebase
from robot_manager_state_transition.robot_entity.worker_properties import Worker_properties
from robot_manager_state_transition.process.process import Process
from robot_manager_state_transition.task.task_find_state_ver import FindTask
from robot_manager_state_transition.task.task_walk_state_ver import WalkTask
# from robot_manager_state_transition.task.task_maniplation_state_ver import ManipulationTask

class RobotManagerServer(Node):

    def __init__(self):
        super().__init__('robot_manager_server')
        self.srv = self.create_service(RobotManager, 'robot_command', self.do_execute_job, callback_group=MutuallyExclusiveCallbackGroup())
        
        # 로봇 객체 초기화
        self.robot = Robot_mobilebase()
        self.robot.set_name("jackal")
        self.robot.set_type("mobilebase")
        self.robot.set_enable_robot()

        self.robot_worker_properties = self.robot.get_worker_property_instance()
        self.job_state_enum = self.robot_worker_properties.job_state_enum
        self.robot_worker_properties.set_state(self.job_state_enum.ready.value) 

        self.mobilebase_properties = self.robot.get_mobilebase_property_instance()
        self.mobilebase_state_enum = self.mobilebase_properties.mobilebase_state_enum
        self.mobilebase_properties.set_state(self.mobilebase_state_enum.safe_zone.value)
        self.mobilebase_properties.set_location("livingroom")
        self.mobilebase_properties.set_data_dir_path("data_jackal")

        # self.manipulatior_properties = self.robot.get_manipulator_property_instance()
        # self.manipulator_state_enum = self.manipulatior_properties.manipulator_state_enum
        # self.manipulatior_properties.set_state(self.manipulator_state_enum.ready.value)
        # self.manipulatior_properties.set_data_dir_path("data_ur")
        # self.manipulatior_properties.set_data_dir_path("data_franka")

        # self.gripper_properties = self.robot.get_gripper_property_instance()
        # self.gripper_state_enum = self.gripper_properties.gripper_state_enum
        # self.gripper_properties.set_state(self.gripper_state_enum.ready.value)
        # 그리퍼 타입 설정
        # self.gripper_properties.set_gripper_type(self.gripper_properties.gripper_type_enum.robotiq.value)
        # self.gripper_properties.set_gripper_type(self.gripper_properties.gripper_type_enum.panda.value)

        # self.detector_properties = self.robot.get_detector_property_instance()
        # self.detector_state_enum = self.detector_properties.detector_state_enum
        # self.detector_properties.set_state(self.detector_state_enum.ready.value)


        # worker property
        self.robot_manager_worker_properties = Worker_properties()
        # 초기화 실행 문
        self.robot_manager_worker_properties.set_state(self.robot_manager_worker_properties.job_state_enum.ready.value)

        # 개별 프로세스 객체 초기화
        self.task_find = FindTask(self, self.robot)
        self.task_walk = WalkTask(self, self.robot)
        # self.task_manipulation = ManipulationTask(self, self.robot)
        # 사용자 변수 정의
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_success = None

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
                
        response.success = self.get_success()
        return response

    def get_process_entity(self, request:RobotManager.Request) -> Process:
        process_entity_rtn = None
        # 기존의 task id 대응이 너무 부적절해서 다시 대응시킴
        # 0 : find
        # 1 : walk
        # 2~: manipulation 이 활용되는 테스크 open close grab put 등
        if request.instruction == 0:
            process_entity_rtn = self.task_find
        elif request.instruction == 1:
            process_entity_rtn = self.task_walk
        else:
            process_entity_rtn = self.task_manipulation
        return process_entity_rtn

    def do_assign_task(self, process_entity:Process, request_arg:RobotManager.Request):
        print("task_assigning")
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_success = None

        job_state = self.robot_manager_worker_properties.get_state()
        print("task_assigning")
        print("job_state : {}".format(job_state))
        if job_state == self.job_state_enum.ready.value:
            print("requset_task")
            self.flag_job_set = process_entity.do_assign_request(request_arg)
            self.robot_manager_worker_properties.set_state(self.job_state_enum.request.value)# task가 할당되어 작업상태로 상태 변화
            print("self.flag_job_set : {}".format(self.flag_job_set))
            if self.flag_job_set == True:
                self.robot_manager_worker_properties.set_state(self.job_state_enum.request.value)
            else:
                self.robot_manager_worker_properties.set_state(self.job_state_enum.error.value)
        print(self.robot_manager_worker_properties.get_state())

        return self.flag_job_set

    def do_execute_task(self, process_entity:Process):
        job_state = self.robot_manager_worker_properties.get_state()
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            ...
        elif job_state == self.job_state_enum.working.value:
            ...
            process_entity.do_execute()
        elif job_state == self.job_state_enum.complete.value:
            self.flag_job_complete = True
            self.job_success = True
            ...
        elif job_state == self.job_state_enum.error.value:
            self.flag_job_complete = True
            self.job_success = False
            ...

    def do_update_job_state(self, process_entity:Process):
        job_state = self.robot_manager_worker_properties.get_state()
        
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            if self.flag_job_set == True:
                self.robot_manager_worker_properties.set_state(self.job_state_enum.working.value)
        elif job_state == self.job_state_enum.working.value:
            process_entity.do_update()
            if process_entity.do_check_completion() == True:
                print("robot manager process_entity.get_success() {}".format(process_entity.get_success()))
                if process_entity.get_success() == True:
                    self.robot_manager_worker_properties.set_state(self.job_state_enum.complete.value)
                else:
                    self.robot_manager_worker_properties.set_state(self.job_state_enum.error.value)
        elif job_state == self.job_state_enum.complete.value:
            self.robot_manager_worker_properties.set_state(self.job_state_enum.ready.value)
        elif job_state == self.job_state_enum.error.value:
            self.robot_manager_worker_properties.set_state(self.job_state_enum.halt.value)
            print("robot_mananger error 발생")
            # assert 0, "error 발생"
        elif job_state == self.job_state_enum.halt.value:
            ...
            print("robot_mananger Halt 상태")
        
    
    def do_check_completion(self):
        job_complete_rtn = False
        job_state = self.robot_manager_worker_properties.get_state()
        
        if job_state == self.job_state_enum.ready.value or job_state == self.job_state_enum.error.value:
            if self.flag_job_set == True:
                if self.flag_job_complete == True:
                    job_complete_rtn = True
                    self.flag_job_set = False
                    self.flag_job_complete = False
                    if job_state == self.job_state_enum.error.value:
                        self.robot_manager_worker_properties.set_state(self.job_state_enum.halt.value)
        if job_state == self.job_state_enum.halt.value:
            job_complete_rtn = True
            self.job_success = False
        return job_complete_rtn

    def get_success(self):
        return self.job_success

def main():
    rclpy.init()
    node = RobotManagerServer()
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