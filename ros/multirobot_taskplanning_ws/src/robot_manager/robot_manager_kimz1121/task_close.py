# ros2 모듈
# ros2 메시지 모듈
from geometry_msgs.msg import Pose
from general_client_python.manipulation_task import ManipulationTask
import json
import time

class CloseTask(ManipulationTask):
    def __init__(self, node_arg): #초기화 때 json 파일의 경로를 함께 전달.
        super().__init__(node_arg)# 부모 클래스 초기화
        self.node = node_arg
        self.load_pose_data_from_json("planner_instruction/marker_pose.json")# json 에 저장된 정보를 미리 불러오는 과정

    def find_id_by_class_name(self):
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


    def do_move_cam_default_pose(self):
        object_id_arg = self.find_id_by_class_name()
        pose_offset_data = self.get_pose_sequence(object_id_arg, self.node.planner_instruction[0], 0)
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

        pose_initial.position.x = 0.30681968747587174
        pose_initial.position.y = 0.0
        pose_initial.position.z = 0.6169407016125963
        pose_initial.orientation.x = 0.9229493117182168
        pose_initial.orientation.y = -0.3848871697409148
        pose_initial.orientation.z = -0.005103909312547584
        pose_initial.orientation.w = 0.0006202236913912168
        
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

    def do(self):
        object_id_arg = self.find_id_by_class_name()
        sequence_len = self.get_sequence_length(object_id_arg, self.node.planner_instruction[0]) # 시퀀스 길이 정보를 받아올 수 있어야 명령의 종료 조건을 알 수 있다.
        iter = 1
        success_do = False
        success_cam_default_pose_rtn = self.do_move_cam_default_pose()
        print('camera 전')
        if success_cam_default_pose_rtn == True:
            time.sleep(1)
            pose_object = self.get_abs_object_pose(object_id_arg)
            print('camera 후')

            if pose_object is not None:
                while True:
                    if iter >= sequence_len:
                        success_do = True# 종료조건에 의해 정상 종료 될때만 성공으로 종료
                        break

                    pose_offset_data = self.get_pose_sequence(object_id_arg, self.node.planner_instruction[0], iter)
                    pose_offset = pose_offset_data['pose']
                    is_relative = pose_offset_data['is_relative']

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
            
            self.do_ready()

        return success_do