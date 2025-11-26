#!/usr/bin/env python3
"""
Action Failure Analysis Script

이 스크립트는 assets/results 폴더 내의 JSON 파일들을 분석하여
실패한 작업들(execution_status == "FAILURE")을 scene_name별로 정리합니다.
"""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


def find_json_files(root_dir: str) -> List[str]:
    """
    주어진 디렉토리에서 모든 JSON 파일의 경로를 찾습니다.

    Args:
        root_dir: 검색할 루트 디렉토리 경로

    Returns:
        JSON 파일 경로들의 리스트
    """
    json_files = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".json"):
                json_files.append(os.path.join(root, file))
    return json_files


def analyze_json_file(file_path: str) -> Dict[str, Any]:
    """
    JSON 파일을 분석하여 실패한 작업들을 추출합니다.

    Args:
        file_path: 분석할 JSON 파일 경로

    Returns:
        분석 결과 딕셔너리 (scene_name, failed_tasks)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        scene_name = data.get("scene_name", "Unknown")
        plans = data.get("plans", [])

        failed_tasks = []
        for plan in plans:
            if isinstance(plan, dict) and plan.get("execution_status") == "FAILURE":
                subtask_name = plan.get("subtask_name", "Unknown")
                failed_tasks.append(subtask_name)

        return {
            "scene_name": scene_name,
            "failed_tasks": failed_tasks,
            "file_path": file_path,
        }

    except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
        print(f"파일 분석 중 오류 발생: {file_path} - {e}")
        return None


def analyze_failures_by_scene(results_dir: str) -> Dict[str, Dict[str, int]]:
    """
    assets/results 디렉토리의 모든 JSON 파일을 분석하여
    scene_name별로 실패한 작업들과 그 등장 횟수를 정리합니다.

    Args:
        results_dir: results 디렉토리 경로

    Returns:
        scene_name을 키로 하고 {작업명: 등장횟수} 딕셔너리를 값으로 하는 딕셔너리
    """
    json_files = find_json_files(results_dir)
    scene_failures = defaultdict(Counter)

    print(f"총 {len(json_files)}개의 JSON 파일을 분석합니다...")

    for i, file_path in enumerate(json_files, 1):
        print(f"진행률: {i}/{len(json_files)} - {os.path.basename(file_path)}")

        result = analyze_json_file(file_path)
        if result:
            scene_name = result["scene_name"]
            failed_tasks = result["failed_tasks"]

            if failed_tasks:  # 실패한 작업이 있는 경우만 추가
                scene_failures[scene_name].update(failed_tasks)

    # Counter를 일반 딕셔너리로 변환
    return {scene_name: dict(counter) for scene_name, counter in scene_failures.items()}


def print_analysis_results(scene_failures: Dict[str, Dict[str, int]]) -> None:
    """
    분석 결과를 출력합니다.

    Args:
        scene_failures: scene_name별 실패한 작업들과 등장 횟수
    """
    print("\n" + "=" * 80)
    print("ACTION FAILURE ANALYSIS RESULTS")
    print("=" * 80)

    if not scene_failures:
        print("실패한 작업이 발견되지 않았습니다.")
        return

    total_scenes = len(scene_failures)
    total_failures = sum(sum(tasks.values()) for tasks in scene_failures.values())
    unique_failures = sum(len(tasks) for tasks in scene_failures.values())

    print(f"총 분석된 씬 수: {total_scenes}")
    print(f"총 실패한 작업 수: {total_failures}")
    print(f"고유한 실패 작업 수: {unique_failures}")
    print()

    # 씬별로 정렬하여 출력
    for scene_name in sorted(scene_failures.keys()):
        failed_tasks = scene_failures[scene_name]
        total_task_failures = sum(failed_tasks.values())
        print(f"Scene: {scene_name}")
        print(
            f"  실패한 작업 수: {len(failed_tasks)} (총 {total_task_failures}회 실패)"
        )
        print("  실패한 작업들:")

        # 등장 횟수 순으로 정렬하여 출력
        sorted_tasks = sorted(failed_tasks.items(), key=lambda x: (-x[1], x[0]))
        for task, count in sorted_tasks:
            print(f"    - {task} ({count}회)")
        print()


def save_results_to_file(
    scene_failures: Dict[str, Dict[str, int]], output_file: str
) -> None:
    """
    분석 결과를 JSON 파일로 저장합니다.

    Args:
        scene_failures: scene_name별 실패한 작업들과 등장 횟수
        output_file: 출력 파일 경로
    """
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(scene_failures, f, ensure_ascii=False, indent=2)

    print(f"분석 결과가 {output_file}에 저장되었습니다.")


def main() -> None:
    """메인 함수"""
    # 현재 스크립트가 있는 디렉토리를 results 디렉토리로 설정
    script_dir = Path(__file__).parent
    results_dir = str(script_dir)

    print("Action Failure Analysis를 시작합니다...")
    print(f"분석 대상 디렉토리: {results_dir}")

    # 실패한 작업들 분석
    scene_failures = analyze_failures_by_scene(results_dir)

    # 결과 출력
    print_analysis_results(scene_failures)

    # 결과를 파일로 저장
    output_file = os.path.join(results_dir, "action_failure_analysis_results.json")
    save_results_to_file(scene_failures, output_file)


if __name__ == "__main__":
    main()
