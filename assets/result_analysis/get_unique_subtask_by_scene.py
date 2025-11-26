# -*- coding: utf-8 -*-
"""assets/tasks 내 FloorPlan 1, 7, 13, 18, 27에 대하여 각각 모든 json 파일을 읽어 온다.

각 json 파일에서 subtask_name을 추출한다.
동일한 subtask name인 경우, 내부 primitive actions를 비교하여 동일한 경우를 제외한다.
"""
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


def generalize_primitive_action(action: str) -> str:
    """Primitive action 문자열에서 좌표와 같은 세부 정보를 제거하여 일반화합니다.

    Args:
        action (str): 원본 primitive action 문자열.
            (예: "NAVIGATE_TO Pot|-01.22|+00.90|-02.36")

    Returns:
        str: 일반화된 primitive action 문자열.
            (예: "NAVIGATE_TO Pot")
    """
    parts = action.split(" ")
    action_type = parts[0]
    action_args = [arg.split("|")[0] for arg in parts[1:]]
    return " ".join([action_type] + action_args)


def main() -> None:
    """메인 실행 함수."""
    base_path = Path("assets/tasks")
    output_dir = Path("assets/result_analysis/unique_subtasks_by_scene")
    output_dir.mkdir(parents=True, exist_ok=True)  # 결과 저장 디렉토리 생성

    floor_plans = [
        "FloorPlan1",
        "FloorPlan7",
        "FloorPlan13",
        "FloorPlan18",
        "FloorPlan27",
    ]

    for fp in floor_plans:
        scene_path = base_path / fp
        if not scene_path.is_dir():
            print(f"Warning: Directory not found - {scene_path}")
            continue

        print(f"Processing scene: {fp}...")
        json_files = list(scene_path.glob("*.json"))
        if not json_files:
            print(f"No JSON files found in {scene_path}")
            continue

        # Scene-level data structures
        scene_tasks: Dict[str, List[Dict]] = defaultdict(list)
        scene_unique_subtask_keys: Set[Tuple[str, Tuple[str, ...]]] = set()

        for file_path in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    tasks_in_file = json.load(f)

                for task_obj in tasks_in_file:
                    task_name = task_obj.get("Task")
                    if not task_name:
                        continue

                    for subtask_obj in task_obj.get("Subtasks", []):
                        subtask_name = subtask_obj.get("Name")
                        primitive_actions = subtask_obj.get("Executions", {}).get(
                            "PrimitiveActions", []
                        )

                        if not subtask_name or not primitive_actions:
                            continue

                        generalized_actions = tuple(
                            generalize_primitive_action(act)
                            for act in primitive_actions
                        )
                        unique_key = (subtask_name, generalized_actions)

                        if unique_key not in scene_unique_subtask_keys:
                            scene_unique_subtask_keys.add(unique_key)
                            # 원본 파일 정보를 서브태스크 객체에 추가
                            subtask_obj_with_source = subtask_obj.copy()
                            subtask_obj_with_source["source_file"] = str(file_path.name)
                            scene_tasks[task_name].append(subtask_obj_with_source)

            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON from {file_path}")
            except Exception as e:
                print(f"An error occurred while processing {file_path}: {e}")

        # Reconstruct the hierarchical structure for the scene
        output_data = []
        for task_name, subtasks_list in sorted(scene_tasks.items()):
            if subtasks_list:  # Only include tasks with at least one unique subtask
                output_data.append({"Task": task_name, "Subtasks": subtasks_list})

        # Save the result for the scene
        output_path = output_dir / f"{fp}.json"
        print(
            f"\nScene: {fp} - Found {len(scene_unique_subtask_keys)} unique subtasks across all tasks."
        )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"Results for {fp} saved to {output_path}")


if __name__ == "__main__":
    main()
