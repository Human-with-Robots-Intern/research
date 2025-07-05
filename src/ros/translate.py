"""
scheduler 가 반환한 명령을 ros 명령어로 변환(mapping)하는 코드
"""

import csv
import json
from typing import List


class InstructionTranslator:
    def __init__(self):
        self.action_mapping = json.load(open("src/ros/action_mapping.json"))
        self.object_mapping = json.load(open("src/ros/object_mapping.json"))
        self.object_positions = json.load(open("src/ros/object_positions.json"))
        pass
    
    def translate(self, instruction: str) -> List[int]:
        action_and_object= instruction.split("|")[0]
        action, object= action_and_object.split(" ")
        action_id = self.action_mapping[action]
        object_id = self.object_mapping[object]
        object_position = self.object_positions[object][0]
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

