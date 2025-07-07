#변경사함
#franka를 find와 walk처럼 star_task로 따로 만들어줌. 
#namespace가 충돌하는 문제를 parameter로 받아서 처리하는 것으로 해결.
from robot_manager_interface.srv import RobotManager
import rclpy
from rclpy.node import Node
from robot_manager.task_find import FindTask
from robot_manager.task_walk import WalkTask
from robot_manager.task_open import OpenTask
from robot_manager.task_close import CloseTask
from robot_manager.task_putin import PutInTask
from robot_manager.task_putback import PutBackTask
from robot_manager.task_switchon import SwitchOnTask
from robot_manager.task_switchoff import SwitchOffTask
from robot_manager.task_grap import GrapTask

class RobotManagerServer(Node):

    def __init__(self):
        super().__init__('robot_manager_server')
        self.srv = self.create_service(RobotManager, 'robot_command', self.select_what_to_do_callback)
        
        self.find_task = FindTask(self)
        self.walk_task = WalkTask(self)
        self.open_task = OpenTask(self)
        self.close_task = CloseTask(self)
        self.switchon_task = SwitchOnTask(self)
        self.switchoff_task = SwitchOffTask(self)
        self.grap_task = GrapTask(self)
        self.putin_task = PutInTask(self)
        self.putback_task = PutBackTask(self)

    def select_what_to_do_callback(self, request, response):
        self.planner_instruction = [request.b, request.c, request.d]
        if(self.state_of_task == 'free'):
            if self.planner_task_dictionary[self.planner_instruction[0]] == 'Find':
                response.success = self.find_task.do()
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'Walk':
                response.success = self.walk_task.do()
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'Grab':
                response.success = self.grap_task.do()
                response.success = True
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'PutIn':
                response.success = self.putin_task.do()
                response.success = True
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'PutBack':
                response.success = self.putback_task.do()
                response.success = True
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'SwitchOn':
                response.success = self.switchon_task.do()
                response.success = True
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'SwitchOff':
                response.success = self.switchoff_task.do()
                response.success = True
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'Open':
                response.success = self.open_task.do()
                response.success = True
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'Close':
                response.success = self.close_task.do()
                response.success = False
            elif self.planner_task_dictionary[self.planner_instruction[0]] == 'Finish':
                print('Successfully finished!')
            else:
                print('error_code_0: There is no planner_instruction.')
        elif (self.state_of_task == 'task_ing'):
            print('error_code_1: The previous task is still running.')
        else:
            assert 0, 'error_code_2: The previous task was interrupted by an error.' #프로그램 강제 종료 코드

        return response

def main():
    rclpy.init()
    node = RobotManagerServer()
    try:
        node.get_logger().info("Starting server node, shut down with CTRL-C")
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.\n')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()