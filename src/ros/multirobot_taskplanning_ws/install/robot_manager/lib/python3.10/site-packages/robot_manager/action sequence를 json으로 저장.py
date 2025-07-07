import json
import os
from geometry_msgs.msg import Pose

class ActionOffsetManager:
    def __init__(self):
        self.offset_dict = {}

    def set_action_offset(self, object_a_id: int, object_b_id: int, action_id: int, subaction: str, sequence_id: int, pose_offset: Pose, is_relative: bool):
        if object_a_id not in self.offset_dict:
            self.offset_dict[object_a_id] = {}
        if object_b_id not in self.offset_dict[object_a_id]:
            self.offset_dict[object_a_id][object_b_id] = {}
        if action_id not in self.offset_dict[object_a_id][object_b_id]:
            self.offset_dict[object_a_id][object_b_id][action_id] = {}
        if subaction not in self.offset_dict[object_a_id][object_b_id][action_id]:
            self.offset_dict[object_a_id][object_b_id][action_id][subaction] = {}
        
        self.offset_dict[object_a_id][object_b_id][action_id][subaction][sequence_id] = {'pose': pose_offset, 'is_relative': is_relative}
        self.save_offsets_to_json()

    def get_action_offset(self, object_a_id: int, object_b_id: int, action_id: int, subaction: str, sequence_id: int):
        if (object_a_id in self.offset_dict and
            object_b_id in self.offset_dict[object_a_id] and
            action_id in self.offset_dict[object_a_id][object_b_id] and
            subaction in self.offset_dict[object_a_id][object_b_id][action_id] and
            sequence_id in self.offset_dict[object_a_id][object_b_id][action_id][subaction]):
            return self.offset_dict[object_a_id][object_b_id][action_id][subaction][sequence_id]
        else:
            return None

    def save_offsets_to_json(self, filename="planner_instruction/marker_pose.json"):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        for object_a_id, object_b_dict in self.offset_dict.items():
            if str(object_a_id) not in existing_data:
                existing_data[str(object_a_id)] = {}
            for object_b_id, action_dict in object_b_dict.items():
                if str(object_b_id) not in existing_data[str(object_a_id)]:
                    existing_data[str(object_a_id)][str(object_b_id)] = {}
                for action_id, subaction_dict in action_dict.items():
                    if str(action_id) not in existing_data[str(object_a_id)][str(object_b_id)]:
                        existing_data[str(object_a_id)][str(object_b_id)][str(action_id)] = {}
                    for subaction, sequence_dict in subaction_dict.items():
                        if subaction not in existing_data[str(object_a_id)][str(object_b_id)][str(action_id)]:
                            existing_data[str(object_a_id)][str(object_b_id)][str(action_id)][subaction] = {}
                        for sequence_id, data in sequence_dict.items():
                            pose_offset = data['pose']
                            is_relative = data['is_relative']
                            existing_data[str(object_a_id)][str(object_b_id)][str(action_id)][subaction][str(sequence_id)] = {
                                'position': {
                                    'x': pose_offset.position.x,
                                    'y': pose_offset.position.y,
                                    'z': pose_offset.position.z
                                },
                                'orientation': {
                                    'x': pose_offset.orientation.x,
                                    'y': pose_offset.orientation.y,
                                    'z': pose_offset.orientation.z,
                                    'w': pose_offset.orientation.w
                                },
                                'is_relative': is_relative
                            }

        with open(filename, 'w') as file:
            json.dump(existing_data, file, indent=4)

    def load_offsets_from_json(self, filename="planner_instruction/marker_pose.json"):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                data = json.load(file)
                for object_a_id, object_b_dict in data.items():
                    self.offset_dict[int(object_a_id)] = {}
                    for object_b_id, action_dict in object_b_dict.items():
                        self.offset_dict[int(object_a_id)][int(object_b_id)] = {}
                        for action_id, subaction_dict in action_dict.items():
                            self.offset_dict[int(object_a_id)][int(object_b_id)][int(action_id)] = {}
                            for subaction, sequence_dict in subaction_dict.items():
                                self.offset_dict[int(object_a_id)][int(object_b_id)][int(action_id)][subaction] = {}
                                for sequence_id, pose_data in sequence_dict.items():
                                    pose_offset = Pose()
                                    pose_offset.position.x = pose_data['position']['x']
                                    pose_offset.position.y = pose_data['position']['y']
                                    pose_offset.position.z = pose_data['position']['z']
                                    pose_offset.orientation.x = pose_data['orientation']['x']
                                    pose_offset.orientation.y = pose_data['orientation']['y']
                                    pose_offset.orientation.z = pose_data['orientation']['z']
                                    pose_offset.orientation.w = pose_data['orientation']['w']
                                    is_relative = pose_data['is_relative']
                                    self.offset_dict[int(object_a_id)][int(object_b_id)][int(action_id)][subaction][int(sequence_id)] = {'pose': pose_offset, 'is_relative': is_relative}

# 사용 예시:
manager = ActionOffsetManager()

pose1 = Pose()
pose1.position.x = 1.0
pose1.position.y = 2.0
pose1.position.z = 3.0
pose1.orientation.x = 0.0
pose1.orientation.y = 0.0
pose1.orientation.z = 0.0
pose1.orientation.w = 1.0

pose2 = Pose()
pose2.position.x = 4.0
pose2.position.y = 5.0
pose2.position.z = 6.0
pose2.orientation.x = 0.0
pose2.orientation.y = 0.0
pose2.orientation.z = 0.0
pose2.orientation.w = 1.0

manager.set_action_offset(1, 2, 1, 'pre_grap', 1, pose1, is_relative=True)
manager.set_action_offset(1, 2, 1, 'end_grap', 2, pose2, is_relative=False)
manager.set_action_offset(2, 3, 1, 'goto_hell', 1, pose1, is_relative=True)

# 오프셋 데이터를 JSON 파일로 저장 및 로드
manager.save_offsets_to_json()
manager.load_offsets_from_json()

pose_initial = Pose()
action_offset_data = manager.get_action_offset(2, 3, 1, 'subaction1', 1)

if action_offset_data is not None:
    if action_offset_data['is_relative'] == True:
        action_offset = action_offset_data['pose']
        is_relative = action_offset_data['is_relative']
        pose_initial.position.x = action_offset.position.x
        pose_initial.position.y = action_offset.position.y
        pose_initial.position.z = action_offset.position.z
        pose_initial.orientation.x = action_offset.orientation.x
        pose_initial.orientation.y = action_offset.orientation.y
        pose_initial.orientation.z = action_offset.orientation.z
        pose_initial.orientation.w = action_offset.orientation.w
        print(f"Is relative: {is_relative}")
        print(pose_initial)
else:
    print("No data found for the specified parameters.")
