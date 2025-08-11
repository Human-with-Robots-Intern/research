# ros2 기본 요소 모듈
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

# ros2 사용자 정의 인터페이스 모듈
from robot_manager_interface.srv import RobotManager

# 기본 파이썬 모듈
import enum

# 사용자 정의 파이썬 모듈
# from robot_manager.task_find import FindTask
from robot_manager_state_transition.task_find_state_ver import FindTask 
# from robot_manager.task_walk import WalkTask
# from robot_manager.task_open import OpenTask
# from robot_manager.task_close import CloseTask
# from robot_manager.task_putin import PutInTask
# from robot_manager.task_putback import PutBackTask
# from robot_manager.task_switchon import SwitchOnTask
# from robot_manager.task_switchoff import SwitchOffTask
# from robot_manager.task_grap import GrapTask

from robot_manager_state_transition.robot_entity.robot_mobile_manipulator import Robot_mobile_manipulator

class RobotManagerServer(Node):

    def __init__(self):
        super().__init__('robot_manager_server')
        self.srv = self.create_service(RobotManager, 'robot_command', self.do_execute_job, callback_group=MutuallyExclusiveCallbackGroup())
        
        # 사용자 정의 객체 초기화 
        # task 종류 enum 정의
        class Task_list_enum(enum.Enum):
            find = enum.auto()
            walk = enum.auto()
            grab = enum.auto()
            put_in = enum.auto()
            put_back = enum.auto()
            switch_on = enum.auto()
            switch_off = enum.auto()
            open = enum.auto()
            close = enum.auto()
        
        self.task_list_enum = Task_list_enum
        
        # 로봇 객체 초기화
        self.robot = Robot_mobile_manipulator()
        self.robot.set_name("husky")
        self.robot.set_type("mobile_manipulator")
        self.robot.set_enable_robot()

        self.worker_properties = self.robot.get_worker_property_instance()
        self.job_state_enum = self.worker_properties.job_state_enum
        self.worker_properties.set_state(self.job_state_enum.ready.value) 

        self.manipulatior_properties = self.robot.get_detector_property_instance()
        self.manipulator_state_enum = self.manipulatior_properties.camera_state_enum
        self.manipulatior_properties.set_state(self.manipulator_state_enum.ready.value) 

        self.mobilebase_properties = self.robot.get_mobilebase_property_instance()
        self.mobilebase_state_enum = self.mobilebase_properties.mobilebase_state_enum
        self.mobilebase_properties.set_state(self.mobilebase_state_enum.safe_zone.value) 
        # 개별 테스크 객체 초기화
        self.find_task = FindTask(self, self.robot)# find 하나만 먼저 초기화
        # self.walk_task = WalkTask(self)
        # self.open_task = OpenTask(self)
        # self.close_task = CloseTask(self)
        # self.switchon_task = SwitchOnTask(self)
        # self.switchoff_task = SwitchOffTask(self)
        # self.grap_task = GrapTask(self)
        # self.putin_task = PutInTask(self)
        # self.putback_task = PutBackTask(self)

        # 사용자 변수 정의
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_result = None

        print("robot is ready")

    def do_execute_job(self, request:RobotManager.Request, response:RobotManager.Response):
        task_entity = self.get_task_entity(request)
        self.task_entity = task_entity
        self.do_assign_task(task_entity, request)
        while True:
            self.do_execute_task(task_entity)
            self.do_update_job_state(task_entity)
            if self.do_check_completion() == True:
                break
        
        response.success = self.get_result()
        return response

    def get_task_entity(self, request:RobotManager.Request):
        task_entity_rtn = None
        
        if request.instruction == self.task_list_enum.find.value:
            task_entity_rtn = self.find_task
        elif request.instruction == self.task_list_enum.walk.value:
            task_entity_rtn = self.walk_task
        elif request.instruction == self.task_list_enum.grab.value:
            task_entity_rtn = self.grap_task
        elif request.instruction == self.task_list_enum.put_in.value:
            task_entity_rtn = self.putin_task
        elif request.instruction == self.task_list_enum.put_back.value:
            task_entity_rtn = self.putback_task
        elif request.instruction == self.task_list_enum.switch_on.value:
            task_entity_rtn = self.switchon_task
        elif request.instruction == self.task_list_enum.switch_on.value:
            task_entity_rtn = self.switchoff_task
        elif request.instruction == self.task_list_enum.open.value:
            task_entity_rtn = self.open_task
        elif request.instruction == self.task_list_enum.close.value:
            task_entity_rtn = self.close_task
        print("find.value : {}".format(self.task_list_enum.find.value))
        print(task_entity_rtn)
        return task_entity_rtn

    def do_assign_task(self, task_entity, request):
        self.flag_job_set = False
        self.flag_job_complete = False
        self.job_result = None

        job_state = self.worker_properties.get_state()
        print("task_assigning")
        print("job_state : {}".format(job_state))
        if job_state == self.job_state_enum.ready.value:
            print("requset_task")
            self.flag_job_set = task_entity.set_request(request)
            self.worker_properties.set_state(self.job_state_enum.request.value)# task가 할당되어 작업상태로 상태 변화
            print("self.flag_job_set : {}".format(self.flag_job_set))
            if self.flag_job_set == True:
                self.worker_properties.set_state(self.job_state_enum.request.value)
            else:
                self.worker_properties.set_state(self.job_state_enum.error.value)
        print(self.worker_properties.get_state())

    def do_execute_task(self, task_entity):
        job_state = self.worker_properties.get_state()
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            ...
        elif job_state == self.job_state_enum.working.value:
            ...
            task_entity.do()
        elif job_state == self.job_state_enum.complete.value:
            self.flag_job_complete = True
            self.job_result = True
            ...
        elif job_state == self.job_state_enum.error.value:
            self.flag_job_complete = True
            self.job_result = False
            ...

    def do_update_job_state(self, task_entity):
        task_entity.do_update_state()
        job_state = self.worker_properties.get_state()
        
        if job_state == self.job_state_enum.ready.value:
            ...
        elif job_state == self.job_state_enum.request.value:
            if self.flag_job_set == True:
                self.worker_properties.set_state(self.job_state_enum.working.value)
        elif job_state == self.job_state_enum.working.value:
            if task_entity.do_check_completion() == True:
                if task_entity.get_result() == True:
                    self.worker_properties.set_state(self.job_state_enum.complete.value)
                else:
                    self.worker_properties.set_state(self.job_state_enum.error.value)
        elif job_state == self.job_state_enum.complete.value:
            self.worker_properties.set_state(self.job_state_enum.ready.value)
        elif job_state == self.job_state_enum.error.value:
            ...
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
    node = RobotManagerServer()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        node.get_logger().info("Starting server node, shut down with CTRL-C")
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.\n')
        node.task_entity.do_print_log()
    executor.remove_node(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()