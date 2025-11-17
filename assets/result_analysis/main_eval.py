from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping
from src.utils.common.logger import create_module_logger
# Import with fallback for script execution
from assets.result_analysis.utils.instruction_parser import load_task_info, parse_instruction_to_tasks
from assets.result_analysis.utils.evaluator import evaluate_tasks, compute_trial_metrics
from assets.result_analysis.utils.summary import aggregate_summary, summary_to_latex_table
from assets.result_analysis.utils.state_change_simulate import accumulate_state_changes, load_events_from_file
from assets.result_analysis.utils.specs import TASK_SPECS

    

logger = create_module_logger(__name__)


def _to_spec_key(task_name: str) -> str:
    """Normalize human-readable task name to TASK_SPECS key."""

    return task_name.lower().replace(" and ", "_and_").replace(" ", "_")


def main() -> None:
    """Traverse states folder, evaluate tasks, and emit summary in JSON/LaTeX."""

    states_folder: Path = Path("assets/results/states100")
    tasks_json_path = Path(__file__).resolve().parents[1] / "tasks" / "floorplan_tasks.json"
    all_task_names, _critical = load_task_info(tasks_json_path)

    if not states_folder.exists():
        logger.error("States folder not found: %s", states_folder)
        return

    for difficulty_dir in sorted(d for d in states_folder.iterdir() if d.is_dir()):
        # difficulty 단위 trials 누적
        trials: List[Mapping[str, Any]] = []
        for task_dir in sorted(t for t in difficulty_dir.iterdir() if t.is_dir()):
            instruction_raw = re.sub(r"^\d{2}_", "", task_dir.name)
            parsed_tasks = parse_instruction_to_tasks(instruction_raw, all_task_names)
            if not parsed_tasks:
                logger.warning("No parsed tasks for instruction_raw: %s", instruction_raw)
                continue
            spec_task_names = [_to_spec_key(t) for t in parsed_tasks]
            valid_task_names = [t for t in spec_task_names if t in TASK_SPECS]
            if not valid_task_names:
                logger.warning(
                    "No valid TASK_SPECS for parsed tasks: %s (instruction_raw=%s)",
                    parsed_tasks,
                    instruction_raw,
                )
                continue

            for scene_dir in sorted(s for s in task_dir.iterdir() if s.is_dir()):
                for approach_dir in sorted(a for a in scene_dir.iterdir() if a.is_dir()):
                    traj_path = approach_dir / "trajectory_log.json"
                    if not traj_path.exists():
                        logger.warning("trajectory_log.json not found: %s", traj_path)
                        continue
                    try:
                        events_data = load_events_from_file(traj_path)
                    except Exception as e:
                        logger.error("Failed to load trajectory: %s (%s)", traj_path, e)
                        continue

                    snapshots_per_step = accumulate_state_changes(events_data)
                    if not snapshots_per_step:
                        logger.warning("Empty snapshots for: %s", traj_path)
                        continue
                    end_state = snapshots_per_step[-1]

                    results = evaluate_tasks(
                        events=events_data,
                        end_state=end_state,
                        task_names=valid_task_names,
                    )
                    print(f"\n[{difficulty_dir.name}/{task_dir.name}/{scene_dir.name}/{approach_dir.name}]")
                    print(f"Parsed tasks: {parsed_tasks}")
                    print(f"Spec task keys: {valid_task_names}")
                    for name, result in results.items():
                        print(
                            f"- {name}: GCR={result.gcr_pass}, TSR={result.tsr_pass}, "
                            f"Duration={result.tsr_duration_sum}, "
                            f"Trigger={result.trigger_step}, End={result.end_step}"
                        )
                    trial_metrics = compute_trial_metrics(
                        parsed_tasks=valid_task_names,
                        task_results=results,
                        events=events_data,
                    )
                    trial_metrics.update(
                        {
                            "difficulty": difficulty_dir.name,
                            "instruction": instruction_raw,
                            "scene": scene_dir.name,
                            "approach": approach_dir.name,
                        }
                    )
                    trials.append(trial_metrics)

        if trials:
            final_summary = aggregate_summary(trials)
            out_dir = states_folder
            summary_path = out_dir / f"{difficulty_dir.name}_summary.json"
            with summary_path.open("w") as f:
                json.dump(final_summary, f, indent=2, sort_keys=True)
            print("\n=== Summary (JSON saved) ===")
            print(summary_path)
            latex_str = summary_to_latex_table(final_summary)
            latex_path = out_dir / f"{difficulty_dir.name}_summary.tex"
            with latex_path.open("w") as f:
                f.write(latex_str)
            print("LaTeX table saved:", latex_path)


if __name__ == "__main__":
    main()


