import os

import yaml

import omnigibson as og
from omnigibson.macros import gm
from omnigibson.robots.manipulation_robot import ManipulationRobot
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=True)


def is_graspable(obj):
    """
    객체가 주어진 로봇의 그리퍼로 잡을 수 있는지 판별하는 함수
    """
    gripper_max_width = 0.3  # 기본값: 0.3m
    if hasattr(obj, "aabb_center") and hasattr(obj, "aabb_extent"):
        obj_width = max(obj.aabb_extent) * 2
    else:
        raise AttributeError(f"Object {obj.name} does not have AABB properties.")

    abilities = obj._abilities if hasattr(obj, "_abilities") else {}
    if "toggleable" in abilities:
        return False

    return obj_width <= (gripper_max_width * 1.1)


def check_action_possibilities(obj):
    """
    객체에 대해 가능한 행동을 판별합니다.
    """

    abilities = obj._abilities if hasattr(obj, "_abilities") else {}
    return {
        "GRASP": is_graspable(obj),
        "OPEN": "openable" in abilities,
        "CLOSE": "openable" in abilities,
        "PLACE_INSIDE": is_graspable(obj),
        "PLACE_ON_TOP": is_graspable(obj),
        "TOGGLE_ON": "toggleable" in abilities,
        "TOGGLE_OFF": "toggleable" in abilities,
    }


def group_objects_by_room_with_actions(scene):
    """
    방별로 객체를 그룹화하고 행동 가능성을 매핑합니다.
    결과는 주어진 방에 대해 가능한 행동과 해당 행동을 수행할 객체 이름을 매핑한 형식으로 반환됩니다.

    Args:
        scene: Scene 객체

    Returns:
        dict: 방별 행동과 해당 객체 이름을 매핑한 사전
    """
    room_objects = {}

    for obj in scene.objects:
        if isinstance(obj, ManipulationRobot):
            continue

        # 객체의 방 정보 확인
        room_names = (
            obj.in_rooms
            if obj.in_rooms
            else [
                scene._seg_map.get_room_instance_by_point(
                    obj.get_position_orientation()[0][:2]
                )
            ]
        )

        # 각 방에서 객체의 가능한 행동을 그룹화
        for room_name in room_names:
            if room_name not in room_objects:
                room_objects[room_name] = {}

            # 객체의 행동 가능성 체크
            actions = check_action_possibilities(obj)
            for action, possible in actions.items():
                if possible:
                    if action not in room_objects[room_name]:
                        room_objects[room_name][action] = []
                    room_objects[room_name][action].append(obj.name)

    # 중복 제거 및 정렬
    for room in room_objects:
        for action in room_objects[room]:
            room_objects[room][action] = sorted(list(set(room_objects[room][action])))

    return room_objects


def main():
    config_filename = os.path.join(og.example_config_path, "fetch_primitives.yaml")
    config = yaml.load(open(config_filename, "r"), Loader=yaml.FullLoader)

    config["scene"]["scene_model"] = "Rs_int"
    config["scene"]["not_load_object_categories"] = ["ceilings"]
    config["objects"] = [
        {
            "type": "DatasetObject",
            "name": "apple",
            "category": "apple",
            "model": "agveuv",
            "position": [-0.3, -1.1, 0.5],
            "orientation": [0, 0, 0, 1],
        },
    ]

    env = og.Environment(configs=config)
    scene = env.scene

    grouped_objects = group_objects_by_room_with_actions(scene)

    print("Grouped Objects by Room:")
    print(grouped_objects)

    env.close()


if __name__ == "__main__":
    main()
