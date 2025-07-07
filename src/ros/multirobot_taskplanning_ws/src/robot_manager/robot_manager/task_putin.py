# ros2 모듈
import rclpy
from rclpy.action import ActionClient
# ros2 메시지 모듈
from geometry_msgs.msg import Pose
from general_client_python.manipulation_task import ManipulationTask
from franka_msgs.action import Grasp
from franka_msgs.action import Move

# 파이썬 모듈
import time
import json

class PutInTask(ManipulationTask):
    def __init__(self, node_arg):# 초기화 때 json 파일의 경로를 함께 전달.
        super().__init__(node_arg)
        self.node = node_arg
        self.load_pose_data_from_json("planner_instruction/marker_pose.json")# json 에 저장된 정보를 미리 불러오는 과정

        self.action_client_gripper_grasp = ActionClient(self.node, Grasp, '/panda_gripper/grasp')
        self.action_client_gripper_move = ActionClient(self.node, Move, '/panda_gripper/move')

    def find_id_by_location_name(self):
        with open("planner_instruction/instruction_position.json", 'r') as file:
            data = json.load(file)
            nodes = data['nodes']
            for node in nodes:
                if node['class_name'] == self.node.location:
                    return node['id']
        return None  # If class_name is not found

    def get_sequence_length(self, object_id, action_id):
        with open("planner_instruction/marker_pose.json", 'r') as file:
            data = json.load(file)
            # JSON 파일에서 object_id, action_id에 해당하는 시퀀스들을 찾음
            sequences = data.get(str(object_id), {}).get(str(action_id), {})
            # 시퀀스의 개수를 반환
            sequence_len = len(sequences)
            return sequence_len

    def do_move_cam_default_pose(self, object_id_arg, action_id_arg):
        # object_id_arg = self.find_id_by_class_name()
        pose_offset_data = self.get_pose_sequence(object_id_arg, action_id_arg, 0)
        pose_offset = pose_offset_data['pose']
        success = False # 기본 상태는 False로 설정하여 성공한 경우에만, True 로 업데이트
        plan_result = self.do_send_plan_rosmsg(pose_offset)

        if not plan_result:
            print("plan failed")
        else:# plan 이 성공 하였을 때만 동작을 수행 
            exec_result = self.do_exec_plan()
            if not exec_result:
                print("execution failed")
            else: 
                success = True
        return success

    def do_ready(self):
        success = False # 기본 상태는 False로 설정하여 성공한 경우에만, True 로 업데이트
        pose_initial = Pose()

        pose_initial.position.x = 0.02364812049874723
        pose_initial.position.y = 0.023975777870172386
        pose_initial.position.z = 0.6169407016125963
        pose_initial.orientation.x = 0.9227398404429652
        pose_initial.orientation.y = -0.3853978331340968
        pose_initial.orientation.z = -0.0033495265149815906
        pose_initial.orientation.w = 0.002911657081366515
        
        plan_result = self.do_send_plan_rosmsg(pose_initial)

        if not plan_result:
            print("plan failed")
        else:# plan 이 성공 하였을 때만 동작을 수행 
            exec_result = self.do_exec_plan()
            if not exec_result:
                print("execution failed")
            else: 
                success = True
        return success
    
    def do_end_pose(self, location_id_arg):
        success = False # 기본 상태는 False로 설정하여 성공한 경우에만, True 로 업데이트
        pose = Pose()

        if location_id_arg == 8:#desk
            pose.position.x = 0.306891
            pose.position.y = 0.0
            pose.position.z = 0.590282
            pose.orientation.x = 0.92388
            pose.orientation.y = -0.382683
            pose.orientation.z = 0.0
            pose.orientation.w = 0.0
        elif location_id_arg == 9:#bathroomcabinet
            pose.position.x = 0.49339871206877683
            pose.position.y = -0.09573746532327454
            pose.position.z = 0.3974521849862713
            pose.orientation.x = -0.4395214314906485
            pose.orientation.y = 0.8980273480222165
            pose.orientation.z = -0.01554789428183811
            pose.orientation.w = 0.011227486272397374
        elif location_id_arg == 17:#kitchentable
            pose.position.x = 0.306891
            pose.position.y = 0.0
            pose.position.z = 0.590282
            pose.orientation.x = 0.92388
            pose.orientation.y = -0.382683
            pose.orientation.z = 0.0
            pose.orientation.w = 0.0
        elif location_id_arg == 19:#washstand
            pose.position.x = 0.36599465553263405
            pose.position.y = -0.008254176730369822
            pose.position.z = 0.8683427422978605
            pose.orientation.x = 0.8722099729394692
            pose.orientation.y = -0.3743454336574623
            pose.orientation.z = 0.2918091871594167
            pose.orientation.w = -0.11816369025253674
        elif location_id_arg == 21:#kitchencabinet
            pose.position.x = 0.306891
            pose.position.y = 0.0
            pose.position.z = 0.75
            pose.orientation.x = 0.92388
            pose.orientation.y = -0.382683
            pose.orientation.z = 0.0
            pose.orientation.w = 0.0
        elif location_id_arg == 22:#bookshelf
            pose.position.x = 0.3805498124187676
            pose.position.y = 0.0019738184574467454
            pose.position.z = 0.6837304698542138
            pose.orientation.x = 0.8840995226247059
            pose.orientation.y = -0.30368233949638684
            pose.orientation.z = 0.3355366986449731
            pose.orientation.w = -0.11644824874252398

        plan_result = self.do_send_plan_rosmsg(pose)

        if not plan_result:
            print("plan failed")
        else:# plan 이 성공 하였을 때만 동작을 수행 
            exec_result = self.do_exec_plan()
            if not exec_result:
                print("execution failed")
            else: 
                success = True
        return success

    
    def do_hold(self, object_id):# 그리퍼를 잡는 함수
        # object_id 의 종류마다 잡는 간격을 달리해야 한다.
        # 이러한 정보도 csv 혹은 json 형식으로 저장하기
        gripper_info = self.get_gripper_info_from_json(object_id)
        print("<test_00>")
        print(gripper_info)
        if gripper_info["type"] == "hard":
            goal_request = Grasp.Goal()
            goal_request.width = float(gripper_info["data"]["width"])
            goal_request.speed = float(gripper_info["data"]["speed"])
            goal_request.force = float(gripper_info["data"]["force"])
            goal_request.epsilon.inner = float(gripper_info["data"]["epsilon"]["inner"])
            goal_request.epsilon.outer = float(gripper_info["data"]["epsilon"]["outer"])
            self.goal_responce_future_gripper = self.action_client_gripper_grasp.send_goal_async(goal_request)
            rclpy.spin_until_future_complete(self.node, self.goal_responce_future_gripper)
            self.goal_response_gripper(self.goal_responce_future_gripper)
            rclpy.spin_until_future_complete(self.node, self.get_result_future_gripper)
            result = self.get_result_callback_gripper(self.get_result_future_gripper)
        elif gripper_info["type"] == "soft":
            goal_request = Move.Goal()
            goal_request.width = float(gripper_info["data"]["width"])
            goal_request.speed = float(gripper_info["data"]["speed"])
            self.goal_responce_future_gripper = self.action_client_gripper_move.send_goal_async(goal_request)
            rclpy.spin_until_future_complete(self.node, self.goal_responce_future_gripper)
            self.goal_response_gripper(self.goal_responce_future_gripper)
            rclpy.spin_until_future_complete(self.node, self.get_result_future_gripper)
            result = self.get_result_callback_gripper(self.get_result_future_gripper)
        return result 

    def do_open(self):
        goal_request = Move.Goal()
        goal_request.width = 0.08 # 놓아줄 때는 그리퍼를 최대로 벌린다. 
        goal_request.speed = 0.03

        self.goal_responce_future_gripper = self.action_client_gripper_move.send_goal_async(goal_request)
        rclpy.spin_until_future_complete(self.node, self.goal_responce_future_gripper)
        self.goal_response_gripper(self.goal_responce_future_gripper)
        rclpy.spin_until_future_complete(self.node, self.get_result_future_gripper)
        result = self.get_result_callback_gripper(self.get_result_future_gripper)
        
        return result 

    def do_close(self):
        goal_request = Move.Goal()
        goal_request.width = 0.00 # 놓아줄 때는 그리퍼를 최대로 벌린다. 
        goal_request.speed = 0.03

        self.goal_responce_future_gripper = self.action_client_gripper_move.send_goal_async(goal_request)
        rclpy.spin_until_future_complete(self.node, self.goal_responce_future_gripper)
        self.goal_response_gripper(self.goal_responce_future_gripper)
        rclpy.spin_until_future_complete(self.node, self.get_result_future_gripper)
        result = self.get_result_callback_gripper(self.get_result_future_gripper)
        
        return result 

    def goal_response_gripper(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.node.get_logger().info('Goal rejected :(')
            return 
        self.node.get_logger().info('Goal accepted :)')
        self.get_result_future_gripper = goal_handle.get_result_async()

    def get_result_callback_gripper(self, future):
        result = future.result().result
        self.node.get_logger().info('Result: {0}'.format(result.success))
        return result.success

    def get_gripper_info_from_json(self, id_number_arg):
        file_path = 'planner_instruction/gripper.json'
        id_number = str(id_number_arg)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if id_number in data:
                    print("<test01>")
                    return data[id_number]
                else:
                    print("<test02>")
                    return None
        except FileNotFoundError:
            print(f"File '{file_path}' not found.")
            return None
        except json.JSONDecodeError:
            print(f"Error decoding JSON from file '{file_path}'.")
            return None
        
    def do_sequence(self, object_id, action_id, pose_object):
        success = False
        iter = 1
        sequence_len = self.get_sequence_length(object_id, action_id) # 시퀀스 길이 정보를 받아올 수 있어야 명령의 종료 조건을 알 수 있다.
        
        while True:
            print("test_04")
            print("sequence_len : {}/{}".format(iter, sequence_len))
            if iter >= sequence_len:
                success = True# 종료조건에 의해 정상 종료 될때만 성공으로 종료
                break
            print("test_05")
            pose_offset_data = self.get_pose_sequence(object_id, action_id, iter)
            pose_offset = pose_offset_data['pose']
            is_relative = pose_offset_data['is_relative']

            print("test_06")
            if is_relative == True:
                pose_new_robot_hand = self.do_calc_end_effector_position(pose_object, pose_offset)
                plan_result = self.do_send_plan_rosmsg(pose_new_robot_hand)
            else:
                plan_result = self.do_send_plan_rosmsg(pose_offset)

            if not plan_result:
                print("plan failed")
                break
            else:# plan 이 성공 하였을 때만 동작을 수행 
                exec_result = self.do_exec_plan()
                if not exec_result:
                    print("execution failed")
                    break 

            iter = iter + 1
        print("success : {}".format(success))
        return success

    def do(self):
        action_id_pre_grap = self.node.planner_instruction[0]
        action_id_post_grap = 15# 임시 하드코딩
        location_id = self.find_id_by_location_name()
        print("location_id : {}".format(location_id))
        success_do = False
        success_pre_grap = False
        success_post_grap = False
        success_cam_default_pose_rtn = self.do_move_cam_default_pose(location_id, action_id_pre_grap)

        if success_cam_default_pose_rtn == True:
            time.sleep(1.5)
            pose_object = self.get_abs_object_pose(location_id)
            print("pose_object: {}".format(pose_object))
            if pose_object is not None:
                print("test_00")
                success_pre_grap = self.do_sequence(location_id, action_id_pre_grap, pose_object)
                if success_pre_grap == True: # 물체를 잡기전 근처에 다가가는 과정에 성공한 경우
                    self.do_open() # 그리퍼의 기본 상태는 열린 상태로 유지

            if success_pre_grap == True: # 이전 행동이 성공한 경우만 다음 행동을 수행
                print("test_01")
                success_post_grap = self.do_sequence(location_id, action_id_post_grap, pose_object)
                if success_post_grap == True: # 물체를 바로 잡을 수 있을 정도로 완전히 다가가는 과정에 성공한 경우
                    self.do_close() # 물체에 충분히 다가감에 성공하였으므로 물체를 그랩
            print("test_03")
        return success_do