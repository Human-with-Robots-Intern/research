from robot_manager_interface.srv import RobotManager
import sys
import rclpy
from rclpy.node import Node
import csv
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor


class RobotManagerClient(Node):

    def __init__(self):
        super().__init__('robot_manager_client')
        self.cli_h = self.create_client(RobotManager, '/robot_command') 
        while not self.cli_h.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.client_entity_list = [self.cli_h]

    def send_request(self, robot_model, instruction, A, B):
        req_temp = RobotManager.Request()      
        req_temp.robot_model = robot_model
        req_temp.instruction = instruction
        req_temp.a = A                          
        req_temp.b = B
        future = self.client_entity_list[robot_model].call_async(req_temp)
        return future

def main(args=None):
    rclpy.init(args=args)
    robot_manager_service_client = RobotManagerClient()
    with open('planner_instruction/instruction001.csv', mode='r', newline='') as instruction_file:
        next(csv.reader(instruction_file))
        print(instruction_file)
        for row in csv.reader(instruction_file):
            try:
                robot_model = int(row[0])
                instruction = int(row[1])
                A = int(row[2]) if row[2] else 100
                B = int(row[3]) if row[3] else 100
                print(robot_model, instruction, A, B)
                future = robot_manager_service_client.send_request(robot_model, instruction, A, B)
                while rclpy.ok():
                    rclpy.spin_once(robot_manager_service_client)
                    if future.done():
                        try:
                            response = future.result()
                        except Exception as e:
                            robot_manager_service_client.get_logger().info(
                                'Service call failed %r' % (e,))
                            sys.exit('종료')
                        else:
                            if response.success == True:
                                robot_manager_service_client.get_logger().info(
                                    'Result = successed')  # CHANGE
                            else:
                                robot_manager_service_client.get_logger().info(
                                    'Result = failed')  # CHANGE
                                sys.exit('종료')
                        break
            except ValueError as e:
                print(f"Skipping invalid row: {row}, Error: {e}")
    robot_manager_service_client.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()