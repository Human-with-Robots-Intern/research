from robot_manager_interface.srv import RobotManager
import rclpy
from rclpy.node import Node
from robot_manager.instruction import make_instruction
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup

class RobotManagerClient(Node):

    def __init__(self):
        super().__init__('robot_manager_client')

        # callback group 설정
        self.client_cb_group = MutuallyExclusiveCallbackGroup()  # 하나의 콜백만 실행되도록 설정
        self.timer_cb_group = ReentrantCallbackGroup()  # 동시에 여러 콜백이 실행될 수 있도록 설정

        # 클라이언트 생성 시 callback group 할당
        self.cli_h = self.create_client(RobotManager, 'a200_0000/robot_command', callback_group=self.client_cb_group)
        self.cli_j = self.create_client(RobotManager, 'j100_0638/robot_command', callback_group=self.client_cb_group)
        self.cli_u = self.create_client(RobotManager, 'ur5/robot_command', callback_group=self.client_cb_group)

        # 서비스 대기
        while not self.cli_h.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        while not self.cli_j.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        while not self.cli_u.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        
        self.client_entity_list = [self.cli_h, self.cli_j, self.cli_u]

    def get_instruction(self, robot_model, instruction, A, B):
        req_temp = RobotManager.Request()      
        req_temp.robot_model = robot_model
        req_temp.instruction = instruction
        req_temp.a = A                          
        req_temp.b = B

        # 비동기 호출 시 callback group 사용
        future = self.client_entity_list[robot_model].call_async(req_temp)
        return future

def main(args=None):
    rclpy.init(args=args)
    
    # 노드 및 executor 생성
    robot_manager_service_client = RobotManagerClient()
    executor = rclpy.executors.MultiThreadedExecutor()  # 멀티스레딩을 위한 executor
    executor.add_node(robot_manager_service_client)

    try:
        # 여러 번 요청을 실행하는 루프 추가'
        while rclpy.ok():
            request = robot_manager_service_client.make_instruction()  # 새 요청 생성
            #예시1 : task들이 만들어지는 속도가 빠를때 -> 배열로 저장, 저장된 배열을 첫번째부터 불러오게하고 self.node.iter을 +1 함. future_complete가 되면 while문이 다시 돌아서 다음 줄을 받아오게 함.
            #예시2 : iter을 1씩 더하면서, 새 요청이 생성될때마다 다음 동작을 만들어서 request로 반환해도됨.
            if request != None:
                future = robot_manager_service_client.get_instruction(request[0], request[1], request[2], request[3])

                # 서비스 호출 완료 대기
                rclpy.spin_until_future_complete(robot_manager_service_client, future)

                # 결과 처리
                response = future.result()
                if response and response.success:
                    robot_manager_service_client.get_logger().info('Result = succeeded')
                else:
                    robot_manager_service_client.get_logger().info('Result = failed')
            else:
                break
    except KeyboardInterrupt:
        robot_manager_service_client.get_logger().info('Keyboard interrupt, shutting down.')

    # 노드 및 executor 종료
    robot_manager_service_client.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
