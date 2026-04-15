"""
kitchen 프롬프트 변형 비교 스크립트.

FloorPlan의 instruction들을 여러 프롬프트 버전으로 각각 생성하고
ver12_kitchen(baseline) 대비 구조적 유사도를 비교한다.

Usage:
    python scripts/analysis/compare_prompt_versions.py
    python scripts/analysis/compare_prompt_versions.py --scene FloorPlan1
    python scripts/analysis/compare_prompt_versions.py --scene FloorPlan1 --save
    python scripts/analysis/compare_prompt_versions.py --scene FloorPlan1 --baseline ver12 --save
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import openai
from dotenv import load_dotenv

from src.utils.config.constants import PROMPT_PATH, SCENE_KNOWLEDGE_PATH
from src.utils.task.task_validators import validate_output_format

load_dotenv()

# ── 비교할 프롬프트 버전 ──────────────────────────────────────────────────────
VERSIONS = {
    "ver12": "e2e_generator_ver12_kitchen.txt",  # baseline (1054줄, guidelines+few-shot)
    "ver12_wo_ex": "e2e_generator_ver12_kitchen_wo_few_shot copy.txt",  # 269줄, guidelines only
    "ver12_wo_ex_ck": "e2e_generator_ver12_kitchen_wo_few_shot_w_guidline.txt",  # 299줄, guidelines+checklist
    "ver13": "e2e_generator_ver13_kitchen.txt",  # 511줄, 5-rules+few-shot
    "ver13_wo_ex": "e2e_generator_ver13_kitchen_wo_fewshot.txt",  # 511줄, 5-rules-few-shot
    "ver13_one_shot": "e2e_generator_ver13_kitchen_one_shot.txt",  # 511줄, 5-rules+one-shot
}

ENV_PLACEHOLDER = "<ENVIRONMENT_INFO>"


# ── 지표 계산 ─────────────────────────────────────────────────────────────────


def count_subtasks(tasks: list) -> int:
    return sum(len(t.get("Subtasks", [])) for t in tasks)


def count_constraints(tasks: list) -> int:
    total = 0
    for t in tasks:
        for s in t.get("Subtasks", []):
            total += len(s.get("TemporalConstraints", []))
    return total


def count_actions(tasks: list) -> int:
    total = 0
    for t in tasks:
        for s in t.get("Subtasks", []):
            total += len(s.get("Executions", {}).get("PrimitiveActions", []))
    return total


def action_object_validity(tasks: list, env_data: dict) -> float:
    """
    각 PrimitiveAction의 (action, object_id) 쌍이
    physics_environment.json의 허용 목록에 있는지 검증.
    NAVIGATE_TO, WAIT, SLICE는 별도 처리.
    """
    free_actions = {"NAVIGATE_TO", "WAIT"}
    valid, total = 0, 0

    for task in tasks:
        for subtask in task.get("Subtasks", []):
            for action_str in subtask.get("Executions", {}).get("PrimitiveActions", []):
                parts = action_str.strip().split()
                if not parts:
                    continue
                action = parts[0]

                if action in free_actions:
                    valid += 1
                    total += 1
                    continue

                if len(parts) < 2:
                    total += 1
                    continue

                obj_id = parts[1]
                allowed = env_data.get(action, [])
                # 좌표 포함 ID 또는 타입 이름으로 부분 매칭
                matched = any(
                    obj_id == a or obj_id.split("|")[0] == a.split("|")[0]
                    for a in allowed
                )
                if matched:
                    valid += 1
                total += 1

    return round(valid / total, 3) if total > 0 else 0.0


def toggle_pairing_score(tasks: list) -> float:
    """TOGGLE_ON이 있는 subtask 뒤에 TOGGLE_OFF After 제약이 존재하는지 검사."""
    subtask_names_with_toggle_on = set()
    referenced_by_after = set()

    for task in tasks:
        for subtask in task.get("Subtasks", []):
            actions = subtask.get("Executions", {}).get("PrimitiveActions", [])
            has_toggle_on = any(a.startswith("TOGGLE_ON") for a in actions)
            if has_toggle_on:
                subtask_names_with_toggle_on.add(subtask["Name"])
            for tc in subtask.get("TemporalConstraints", []):
                if tc.get("Type") == "After":
                    referenced_by_after.add(tc.get("Subtask", ""))

    if not subtask_names_with_toggle_on:
        return 1.0  # TOGGLE_ON 없으면 해당 없음

    paired = subtask_names_with_toggle_on & referenced_by_after
    return round(len(paired) / len(subtask_names_with_toggle_on), 3)


def compute_metrics(tasks: list, env_data: dict) -> dict:
    return {
        "valid_format": validate_output_format(tasks),
        "n_tasks": len(tasks),
        "n_subtasks": count_subtasks(tasks),
        "n_constraints": count_constraints(tasks),
        "n_actions": count_actions(tasks),
        "action_validity": action_object_validity(tasks, env_data),
        "toggle_pairing": toggle_pairing_score(tasks),
    }


# ── LLM 호출 ──────────────────────────────────────────────────────────────────


def call_openai(system_prompt: str, user_input: str) -> list | None:
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"# [Input]\n\n{user_input}"},
            ],
            temperature=0,
        )
        content = resp.choices[0].message.content.strip()
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"    [ERROR] {e}")
        return None


# ── 메인 ──────────────────────────────────────────────────────────────────────


def run_comparison(scene: str, save: bool, baseline: str = "ver12"):
    scene_number = int(scene.replace("FloorPlan", ""))
    scene_type = "kitchen"  # 이 스크립트는 kitchen 전용

    # 환경 정보 로드
    env_path = (
        SCENE_KNOWLEDGE_PATH
        / scene_type
        / "environment"
        / f"{scene}_physics_environment.json"
    )
    if not env_path.exists():
        print(f"[ERROR] 환경 파일 없음: {env_path}")
        sys.exit(1)
    with open(env_path, encoding="utf-8") as f:
        env_data = json.load(f)
    env_str = json.dumps(env_data, ensure_ascii=False)

    # Instruction 목록 (기존 태스크 파일명에서 추출)
    task_dir = (
        ROOT
        / "assets"
        / "tasks"
        / "sampled_10_instruction_set_for_final_experiment_251203"
        / "tasks_2_constraints_1"
        / scene
    )
    if not task_dir.exists():
        print(f"[ERROR] 태스크 디렉토리 없음: {task_dir}")
        sys.exit(1)

    instructions = []
    for p in sorted(task_dir.glob("*.json")):
        # "01_boil_water_with_pot..." → "boil water with pot..."
        name = p.stem
        instruction = " ".join(name.split("_")[1:])
        instructions.append(instruction)

    if not instructions:
        print(f"[ERROR] instruction 없음: {task_dir}")
        sys.exit(1)

    # 프롬프트 로드 및 환경 주입
    prompts = {}
    for ver, fname in VERSIONS.items():
        fpath = Path(PROMPT_PATH) / fname
        if not fpath.exists():
            print(f"[SKIP] 프롬프트 없음: {fpath}")
            continue
        text = fpath.read_text(encoding="utf-8")
        prompts[ver] = text.replace(ENV_PLACEHOLDER, env_str)

    if len(prompts) < 2:
        print("[ERROR] 두 버전 모두 필요합니다.")
        sys.exit(1)

    # 비교 실행
    ver_order = [v for v in VERSIONS if v in prompts]
    results = []
    print(f"\n{'='*70}")
    print(f"  프롬프트 비교: {scene}  ({len(instructions)}개 instruction)")
    for ver in ver_order:
        print(f"  {ver:<15}: {VERSIONS[ver]}")
    print(f"  baseline: {baseline}")
    print(f"{'='*70}\n")

    header = f"{'#':<3} {'Instruction':<40} {'버전':<15} {'OK':>3} {'Sub':>4} {'Cons':>5} {'Acts':>5} {'ActV':>6} {'Tog':>5}"
    print(header)
    print("-" * len(header))

    for i, instruction in enumerate(instructions, 1):
        row = {"instruction": instruction, "versions": {}}
        print(f"\n[{i:02d}] {instruction}")

        for ver in ver_order:
            print(f"     {ver:<15}: ", end="", flush=True)
            output = call_openai(prompts[ver], instruction)

            if output is None:
                m = {"valid_format": False}
                print("FAIL")
            else:
                m = compute_metrics(output, env_data)
                status = "OK  " if m["valid_format"] else "FAIL"
                print(
                    f"{status} | sub={m['n_subtasks']:>2} "
                    f"cons={m['n_constraints']:>2} acts={m['n_actions']:>3} "
                    f"actV={m['action_validity']:.2f} tog={m['toggle_pairing']:.2f}"
                )
                m["output"] = output

            row["versions"][ver] = m

        results.append(row)

    # 집계 요약
    print(f"\n{'='*70}")
    print(f"  집계 요약  (baseline={baseline})")
    print(f"{'='*70}")
    metrics_keys = [
        "valid_format",
        "n_subtasks",
        "n_constraints",
        "n_actions",
        "action_validity",
        "toggle_pairing",
    ]

    # baseline 평균값 먼저 계산
    baseline_avgs: dict[str, float] = {}
    for k in metrics_keys:
        vals = []
        for r in results:
            m = r["versions"].get(baseline, {})
            if k in m:
                vals.append(float(m[k]) if not isinstance(m[k], bool) else float(m[k]))
        baseline_avgs[k] = sum(vals) / len(vals) if vals else 0.0

    delta_metrics = ["n_subtasks", "n_constraints", "action_validity", "toggle_pairing"]

    for ver in ver_order:
        vals = {k: [] for k in metrics_keys}
        for r in results:
            m = r["versions"].get(ver, {})
            for k in metrics_keys:
                if k in m:
                    vals[k].append(
                        float(m[k]) if not isinstance(m[k], bool) else float(m[k])
                    )

        n = len([r for r in results if ver in r["versions"]])
        print(f"\n  [{ver}]  (n={n})  {VERSIONS.get(ver, '')}")
        for k in metrics_keys:
            v = vals[k]
            if v:
                avg = sum(v) / len(v)
                if ver != baseline and k in delta_metrics:
                    delta = avg - baseline_avgs[k]
                    print(f"    {k:<22}: avg={avg:.3f}  (Δ {delta:+.3f} vs {baseline})")
                else:
                    print(f"    {k:<22}: avg={avg:.3f}")

    # delta 요약 (baseline 제외)
    if baseline in ver_order:
        print(f"\n{'='*70}")
        print(f"  |delta| 요약 (vs {baseline}, 작을수록 유사)")
        print(f"{'='*70}")
        print(
            f"  {'버전':<15} {'|Δsub|':>8} {'|Δcons|':>8} {'|ΔactV|':>8} {'|Δtog|':>8}  (줄수)"
        )
        line_counts = {
            "ver12": 1054,
            "ver12_wo_ex": 269,
            "ver12_wo_ex_ck": 299,
            "ver13": 511,
        }
        for ver in ver_order:
            if ver == baseline:
                continue
            deltas = []
            for k in delta_metrics:
                v_vals = [
                    float(r["versions"].get(ver, {}).get(k, 0))
                    for r in results
                    if k in r["versions"].get(ver, {})
                ]
                b_vals = [
                    float(r["versions"].get(baseline, {}).get(k, 0))
                    for r in results
                    if k in r["versions"].get(baseline, {})
                ]
                if v_vals and b_vals:
                    paired = [(v, b) for v, b in zip(v_vals, b_vals)]
                    avg_abs_delta = sum(abs(v - b) for v, b in paired) / len(paired)
                else:
                    avg_abs_delta = float("nan")
                deltas.append(avg_abs_delta)
            lc = line_counts.get(ver, "?")
            print(
                f"  {ver:<15} {deltas[0]:>8.3f} {deltas[1]:>8.3f} {deltas[2]:>8.3f} {deltas[3]:>8.3f}  ({lc}줄)"
            )

    # 결과 저장
    if save:
        out_dir = ROOT / "assets" / "results" / "prompt_comparison"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{scene}_all_versions.json"
        save_data = [
            {
                "instruction": r["instruction"],
                **{
                    ver: {
                        k: v
                        for k, v in r["versions"].get(ver, {}).items()
                        if k != "output"
                    }
                    for ver in ver_order
                },
                **{
                    f"{ver}_output": r["versions"].get(ver, {}).get("output")
                    for ver in ver_order
                },
            }
            for r in results
        ]
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        print(f"\n  결과 저장: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="kitchen 프롬프트 변형 비교 (ver12 baseline 대비 delta)"
    )
    parser.add_argument(
        "--scene", default="FloorPlan1", help="비교할 씬 (기본: FloorPlan1)"
    )
    parser.add_argument("--save", action="store_true", help="결과를 JSON으로 저장")
    parser.add_argument(
        "--baseline",
        default="ver12",
        choices=list(VERSIONS.keys()),
        help="delta 기준 버전 (기본: ver12)",
    )
    args = parser.parse_args()
    run_comparison(args.scene, args.save, args.baseline)
