import json
import logging
import sys
from pathlib import Path
from typing import Optional

import ai2thor.controller

from ithor.utils.math_utils import load_navigation_graph
from scheduler.action_handler import ActionHandler
from src.models.task import Subtask
from src.simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller
from src.utils.io_utils import task_io
from src.utils.task.task_util import TaskUtil


def find_physics_file(scene_name: str) -> Optional[Path]:
    """assets/scene_knowledge 내에서 physics_environment.json 파일을 검색합니다."""
    base_search_path = Path.cwd() / "assets" / "scene_knowledge"
    for subdir in base_search_path.iterdir():
        if subdir.is_dir():
            file_path = (
                subdir / "environment" / f"{scene_name}_physics_environment.json"
            )
            if file_path.exists():
                return file_path
    return None


def initialize_scene_from_physics_file(
    controller: ai2thor.controller.Controller, physics_file_path: Path
):
    """..._physics_environment.json 파일을 읽어 컨트롤러의 객체 상태를 초기화합니다."""
    with open(physics_file_path, "r") as f:
        env_data = json.load(f)

    # 객체의 열림/토글 상태를 먼저 설정합니다.
    for obj_id, obj_data in env_data.get("objects", {}).items():
        if obj_data.get("is_open") is not None:
            action = "OpenObject" if obj_data["is_open"] else "CloseObject"
            controller.step(action=action, objectId=obj_id, forceAction=True)
        if obj_data.get("is_toggled") is not None:
            action = "ToggleObjectOn" if obj_data["is_toggled"] else "ToggleObjectOff"
            controller.step(action=action, objectId=obj_id, forceAction=True)

    # 객체 위치를 설정합니다.
    object_poses = [
        {
            "objectId": obj_id,
            "position": obj_data["position"],
            "rotation": obj_data["rotation"],
        }
        for obj_id, obj_data in env_data.get("objects", {}).items()
    ]
    if object_poses:
        event = controller.step(action="SetObjectPoses", objectPoses=object_poses)
        if not event.metadata["lastActionSuccess"]:
            logging.error(
                f"Failed to set object poses: {event.metadata['errorMessage']}"
            )

    # 에이전트 위치를 설정합니다.
    agent_data = env_data.get("agent")
    if agent_data:
        controller.step(
            action="Teleport",
            position=agent_data["position"],
            rotation=agent_data["rotation"],
            horizon=agent_data.get("cameraHorizon", 30.0),
            standing=True,
        )


def main():
    """메인 실행 함수"""
    # --- 1. 설정 ---
    SCENE_NAME = "FloorPlan1"
    TARGET_SUBTASK_NAME = "Put Book in Cabinet"

    # --- 로거 설정 ---
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("SubtaskTest")

    # --- 2. 경로 설정 ---
    subtask_scene_path = (
        Path.cwd()
        / "assets/result_analysis/unique_subtasks_by_scene"
        / f"{SCENE_NAME}.json"
    )
    task_dir_path = Path.cwd() / "assets/legacy_task/tasks" / SCENE_NAME

    # --- 3. 테스트할 서브태스크와 원본 파일 찾기 ---
    source_task_filename = None
    with open(subtask_scene_path, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    for task in tasks:
        for subtask in task.get("Subtasks", []):
            if subtask.get("Name") == TARGET_SUBTASK_NAME:
                source_task_filename = subtask.get("source_file")
                break
        if source_task_filename:
            break

    if not source_task_filename:
        raise ValueError(
            f"Subtask '{TARGET_SUBTASK_NAME}' not found in {subtask_scene_path}"
        )

    logger.info(
        f"Found subtask '{TARGET_SUBTASK_NAME}' in source file: {source_task_filename}"
    )

    # --- 4. 컨트롤러 시작 및 환경 설정 ---
    controller = None
    try:
        physics_file = find_physics_file(SCENE_NAME)
        if not physics_file:
            raise FileNotFoundError(f"Physics file for scene '{SCENE_NAME}' not found.")

        with open(physics_file, "r") as f:
            env_json = json.load(f)
        controller_scene_name = env_json.get("scene_name", SCENE_NAME)

        logger.info(f"Initializing controller for scene: {controller_scene_name}")
        controller = init_ai2thor_controller(SCENE_NAME, platform=None)
        initialize_scene_from_physics_file(controller, physics_file)
        logger.info("AI2Thor scene initialized to the task's starting state.")

        # nav_graph = load_navigation_graph(controller)
        # action_handler = ActionHandler(nav_graph, real_world_mode=False)

        # --- 5. Subtask 객체 빌드 및 선택 ---
        original_task_path = task_dir_path / source_task_filename
        original_task_data = task_io.load_task_data_from_file(str(original_task_path))

        processed_subtasks, _, _ = TaskUtil.build_tasks_and_constraints(
            task_data=original_task_data,
            scene_file_name=f"{SCENE_NAME}_physics_environment.json",
        )

        final_subtask_to_execute = None
        for subtask_obj in processed_subtasks:
            if subtask_obj.name == TARGET_SUBTASK_NAME:
                final_subtask_to_execute = subtask_obj
                break

        if not final_subtask_to_execute:
            raise ValueError(
                f"Could not find processed subtask '{TARGET_SUBTASK_NAME}'"
            )

        # --- 6. 서브태스크 실행 ---
        logger.info(f"Executing subtask: {final_subtask_to_execute.name}")
        execute_subtask(controller, final_subtask_to_execute, logger)
        logger.info("Execution finished successfully.")

    except Exception as e:
        logger.exception(f"An error occurred during execution: {e}")
    finally:
        if controller:
            controller.stop()
            logger.info("Controller stopped.")


if __name__ == "__main__":
    main()
