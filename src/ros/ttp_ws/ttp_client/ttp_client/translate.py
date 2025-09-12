"""
scheduler 가 반환한 명령을 ros 명령어로 변환(mapping)하는 코드
"""

import csv
import json
import time
from typing import List


class InstructionTranslator:
    def __init__(self):
        self.action_mapping = json.load(open("src/ros/ttp_ws/data/action_mapping.json"))
        self.object_mapping = json.load(open("src/ros/ttp_ws/data/object_mapping.json"))
        pass
    
    def translate(self, instruction: str) -> List[int]:
        print(f"instruction: {instruction}")
        # 매번 불러와서 물체의 최신 위치를 가져와야함. 
        self.object_positions = json.load(open("src/ros/ttp_ws/data/object_positions.json"))
        
        split_instruction= instruction.split(" ")        
        action, object = split_instruction[0], split_instruction[1]
        action_id = self.action_mapping[action]        
        object_id = self.object_mapping[object.lower()]
        object_position = self.object_positions[object.lower()]
        return [0, action_id, object_id, object_position]
    
    def _get_obj_id(self, obj_name: str) -> int:
        with open("src/ros/object_mapping.json", "r") as f:
            data = json.load(f)
        for item in data:
            if item["class_name"] == obj_name:
                return item["id"]
        return None




def main():
    pass





if __name__ == "__main__":
    main()

