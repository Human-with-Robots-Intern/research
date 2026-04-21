"""
LaMMA-P LLM 결과 사전 계산 스크립트

21개 태스크 × N회 반복으로 LLM 호출을 미리 수행하고 결과를 캐시에 저장합니다.
실제 실험 실행 전에 이 스크립트를 먼저 실행하세요.

- 캐시 키: "{case_name}|{instruction_filename}"
- 캐시 값: ["mimic_code_v1", "mimic_code_v2", ..., "mimic_code_vN"]
  → 인덱스 0 = v1 (task_folder_name이 *_v1인 실험에서 사용)
  → 인덱스 N-1 = vN

Usage:
    python3 scripts/precompute_lammap_llm.py \
        --num-attempts 5 \
        --task-folder decomposed_final_revision_260416_realworld \
        --gpt-version gpt-4o \
        --openai-api-key-file api_key \
        --cache-file assets/lammap_llm_cache.json
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.baselines.lammap.lammap_ai2thor import run_lammap_planning
from src.utils.common import create_module_logger

ROS_OBJECTS_PATH = "assets/ros/static/object_init_states.json"
CASES = ["tasks_2_constraints_1", "tasks_3_constraints_1", "tasks_3_constraints_2"]
DURATIONS = [60, 100, 140]  # under, correct, over


def get_objects_ai() -> str:
    with open(ROS_OBJECTS_PATH) as f:
        ros_objs = json.load(f)
    return f"\n\nobjects = {json.dumps(list(ros_objs.keys()))}"


def get_task_string(instruction_filename: str) -> str:
    stem = Path(instruction_filename).stem
    m = re.match(r"\d+_(.*)", stem)
    return m.group(1).replace("_", " ") if m else stem.replace("_", " ")


def collect_all_tasks(assets_path: Path, task_folder: str) -> list:
    """케이스 폴더 × FloorPlan301 아래 모든 task 파일명을 수집합니다.

    task_folder: assets/tasks/ 하위 폴더 이름 (어느 버전이든 파일명은 동일)
    파일 내용은 읽지 않고 파일명만 사용합니다.
    """
    tasks = []
    task_root = assets_path / "tasks" / task_folder
    if not task_root.exists():
        raise FileNotFoundError(f"태스크 폴더를 찾을 수 없습니다: {task_root}")
    for case in CASES:
        scene_dir = task_root / case / "FloorPlan301"
        if not scene_dir.exists():
            continue
        for json_file in sorted(scene_dir.glob("*.json")):
            tasks.append({
                "case_name": case,
                "instruction_filename": json_file.name,
                "task_string": get_task_string(json_file.name),
            })
    return tasks


def load_cache(cache_file: Path) -> dict:
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    return {}


def save_cache(cache_file: Path, cache: dict) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    tmp.replace(cache_file)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LaMMA-P LLM 사전 계산")
    parser.add_argument("--num-attempts", type=int, default=5, help="태스크당 반복 횟수 (v1~vN)")
    parser.add_argument(
        "--task-folder",
        type=str,
        default="decomposed_final_revision_260416_realworld_v5",
        help="파일명 목록을 읽을 기준 task 폴더 이름 (assets/tasks/ 하위, 버전 무관하게 파일명 동일)",
    )
    parser.add_argument("--gpt-version", type=str, default="gpt-4o")
    parser.add_argument("--openai-api-key-file", type=str, default="api_key")
    parser.add_argument(
        "--cache-file",
        type=str,
        default="assets/lammap_llm_cache.json",
        help="캐시 저장 경로",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        default=False,
        help="이미 존재하는 결과도 재생성",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    logger = create_module_logger(module_name="precompute_lammap", level="INFO")

    assets_path = Path(__file__).parent.parent / "assets"
    lammap_base = Path(__file__).parent.parent / "src" / "baselines" / "lammap"
    cache_file = Path(args.cache_file)

    try:
        tasks = collect_all_tasks(assets_path, args.task_folder)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    if not tasks:
        logger.error(f"태스크 파일이 없습니다: {args.task_folder}")
        sys.exit(1)
    total_entries = len(tasks) * len(DURATIONS) * args.num_attempts
    logger.info(f"총 태스크: {len(tasks)} × {len(DURATIONS)}종 duration × {args.num_attempts}회 = {total_entries}개")

    objects_ai = get_objects_ai()
    logger.info(f"objects_ai 로드 완료 (객체 수: {objects_ai.count(',')+1})")

    cache = load_cache(cache_file)

    done = 0

    for duration in DURATIONS:
        logger.info(f"\n{'#'*60}\n# duration = {duration}\n{'#'*60}")
        for task in tasks:
            # 캐시 키: case|instruction|duration
            cache_key = f"{task['case_name']}|{task['instruction_filename']}|{duration}"
            existing = cache.get(cache_key, [])

            if args.skip_existing and len(existing) >= args.num_attempts:
                logger.info(f"[SKIP] {cache_key} (이미 {len(existing)}개)")
                done += args.num_attempts
                continue

            logger.info(
                f"\n{'='*60}\n"
                f"태스크: {task['task_string']}\n"
                f"케이스: {task['case_name']} | duration={duration}\n"
                f"기존: {len(existing)}개 → 목표: {args.num_attempts}개\n"
                f"{'='*60}"
            )

            start_idx = len(existing) if args.skip_existing else 0
            if not args.skip_existing:
                existing = []

            for attempt_idx in range(start_idx, args.num_attempts):
                t0 = time.time()
                logger.info(
                    f"[{done+1}/{total_entries}] duration={duration} v{attempt_idx+1} / {task['instruction_filename']}"
                )

                try:
                    mimic_code = run_lammap_planning(
                        base_path=str(lammap_base),
                        task=task["task_string"],
                        floor_plan=301,
                        objects_ai=objects_ai,
                        gpt_version=args.gpt_version,
                        api_key_file=args.openai_api_key_file,
                        logger=logger,
                        wait_units=duration,
                    )
                    existing.append(mimic_code)
                    logger.info(f"  완료 ({time.time()-t0:.1f}s, {len(mimic_code)}자)")
                except Exception as e:
                    logger.error(f"  실패: {e}")
                    existing.append("")

                cache[cache_key] = existing
                save_cache(cache_file, cache)
                done += 1

    logger.info(
        f"\n사전 계산 완료: {done}개 처리\n"
        f"캐시 위치: {cache_file.resolve()}\n"
        f"캐시 키 수: {len(cache)}"
    )


if __name__ == "__main__":
    main()
