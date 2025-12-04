# import
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import JointState
from moveit_proxy_interface.srv import SendPlanJoint
from moveit_proxy_interface.srv import ExecPlan


# class
class InitialAngle(Node):
    # node
    def __init__(self):
        super().__init__('initial_angle')
        
        # angle 값 던지기
        self.sendangle = self.create_client(SendPlanJoint,'/moveit_proxy_send_plan_joint')
        while not self.sendangle.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('wait for service_1')
        self.req_sendangle = SendPlanJoint.Request()
        
        
        # 실행 여부
        self.execplan = self.create_client(ExecPlan, '/moveit_proxy_exec_plan')
        while not self.execplan.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('wait for service_3')
        self.req_execplan = ExecPlan.Request()



    # service request & respond
    def SendInitialAngle(self, joint_state:JointState):
        self.req_sendangle.goal_joint_state = joint_state
        # respond
        self.InitialAngle = self.sendangle.call_async(self.req_sendangle)
        # spin
        rclpy.spin_until_future_complete(self, self.InitialAngle)
        # return respond
        return self.InitialAngle.result()
    
    def ExecRobot(self):
        self.ExecutionRobot = self.execplan.call_async(self.req_execplan)
        rclpy.spin_until_future_complete(self, self.ExecutionRobot)
        return self.ExecutionRobot.result()
        
        
        
        
# main code
def main(args=None):
    rclpy.init(args=args)
    
    Initial_angle = InitialAngle()
    
    initial_angle_value = JointState()
    
    initial_angle_value.name = [
        'panda_joint1',
        'panda_joint2',
        'panda_joint3',
        'panda_joint4',
        'panda_joint5',
        'panda_joint6',
        'panda_joint7',
    ]
    
    initial_angle_value.position = [
        -0.14418620161215462,
        -1.3178362867085236,
        0.010821177704270638,
        1.8310953216999253,
        -0.15186596935620558,
        0.6409683040905391,
        1.283054573961982,
    ]

    ''' For Last position
    name:
        - panda_joint1
        - panda_joint2
        - panda_joint3
        - panda_joint4
        - panda_joint5
        - panda_joint6
        - panda_joint7
        - panda_finger_joint1
        - panda_finger_joint2
    position:
        - 1.2868524171251163
        - 0.3471273701358832
        - 2.1153583180684707
        - -1.921720486136316
        - -0.45519595258044737
        - 0.6964357091155318
        - -0.8418293189333839
        - 0.0401843897998333
        - 0.0401843897998333
    '''


    ''' For experience on the table
    name:
        - panda_joint1
        - panda_joint2
        - panda_joint3
        - panda_joint4
        - panda_joint5
        - panda_joint6
        - panda_joint7
        - panda_finger_joint1
        - panda_finger_joint2
    position:
        - 1.8096882593599695
        - -0.695616532608249
        - 0.20159193290123473
        - -2.0333234136760163
        - 0.18822961209895253
        - 2.0577680183607714
        - 0.6709617981049749
        - 0.0401843897998333
        - 0.0401843897998333
    '''

    plan_result = Initial_angle.SendInitialAngle(initial_angle_value)
    exec_plan = Initial_angle.ExecRobot()
    # getangle = Initial_angle.GetRobotCurrentAngle()
    
    if not plan_result or not plan_result.result:
        print("plan failed, ", plan_result)
        Initial_angle.destroy_node()
        rclpy.shutdown()
        return
    print("plan success, ", plan_result)

    if not exec_plan or not exec_plan.result:
        print("execution failed, ", exec_plan)
        Initial_angle.destroy_node()
        rclpy.shutdown()
        return
    print("execution success, ", exec_plan)
    
    
    
    Initial_angle.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()