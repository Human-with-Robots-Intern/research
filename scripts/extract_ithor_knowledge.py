### scripts/extract_ithor_knowledge.py
from src.simulation.runner_ai2thor import init_ai2thor_controller
from src.simulation.scene_info_extractor import (
    extract_environment,
    extract_navigation_time,
    extract_object_positions,
)
from src.utils.config import KNOWLEDGE_PATH
from src.utils.io_utils import (
    save_environment_data,
    save_navigation_time,
    save_object_positions,
)


def main(scene_name: str):
    controller = init_ai2thor_controller(scene_name)
    scene = controller.last_event.metadata["sceneName"]

    # 객체 위치 저장
    positions = extract_object_positions(controller)
    save_object_positions(scene, positions, KNOWLEDGE_PATH)

    # 환경 정보 저장
    env, object_ids = extract_environment(controller)
    save_environment_data(scene, env, KNOWLEDGE_PATH)

    # 이동 시간 저장
    move_time = extract_navigation_time(controller, object_ids)
    save_navigation_time(scene, move_time, KNOWLEDGE_PATH)

    print(f"Knowledge extracted and saved for scene: {scene}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract AI2-THOR knowledge and save to JSON."
    )
    parser.add_argument(
        "--scene", type=str, default="FloorPlan1_physics", help="Scene name to load"
    )
    args = parser.parse_args()

    main(args.scene)
