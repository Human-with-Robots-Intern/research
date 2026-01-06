import glob
import json
import os
import sys
from pathlib import Path

# Ensure the project root is in sys.path to resolve 'assets' package
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from assets.result_analysis.utils.specs import (
        TASK_SPECS,
        ConditionGroup,
        ObjectCondition,
    )
    from assets.result_analysis.utils.state_change_simulate import (
        accumulate_state_changes,
        load_events_from_file,
    )

    # Import constants for TSR check
    from src.utils.config.constants import (
        TIMING_TOLERANCE_ABS,
        TIMING_TOLERANCE_DEFAULT,
    )
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)


def find_states_dirs(root_dir):
    return glob.glob(os.path.join(root_dir, "states*"))


def get_failed_tasks(json_data):
    """Returns list of task names that failed with (passed=False, duration=None) in TSR."""
    failed_tasks = []
    if not json_data or "tasks" not in json_data:
        return failed_tasks

    for task_name, task_data in json_data.get("tasks", {}).items():
        tsrs = task_data.get("tsrs", {})
        gcr_passed = task_data.get("gcr_satisfied")

        is_failed = False

        # If GCR failed, the task failed
        if not gcr_passed:
            is_failed = True

        # If TSR failed, the task failed
        if tsrs:
            for tsr_name, tsr_data in tsrs.items():
                if tsr_data.get("passed") is False:
                    is_failed = True
                    break

        if is_failed:
            failed_tasks.append(task_name)
    return failed_tasks


def get_object_state(state, prefix):
    """Find object in state matching prefix (case-insensitive)."""
    prefix = prefix.lower()
    for obj_name, props in state.items():
        if (
            obj_name.lower().startswith(prefix)
            or obj_name.split("_")[0].lower() == prefix
        ):
            return obj_name, props
    return None, None


def check_floor(props):
    """Check if object is on the floor."""
    parents = props.get("parentReceptacles")
    if parents and isinstance(parents, list):
        for p in parents:
            if "floor" in p.lower():
                return True
    return False


def diagnose_condition(state, condition):
    """
    Diagnose why a condition is not met in the given state.
    Returns a list of reason strings.
    """
    obj_name, props = get_object_state(state, condition.object_name_prefix)

    if not obj_name:
        return [f"Object '{condition.object_name_prefix}' not found in state."]

    reasons = []

    # Check if on floor
    if check_floor(props):
        reasons.append(f"Object '{obj_name}' is on the Floor.")

    for req_key, req_val in condition.required_properties.items():
        cur_val = props.get(req_key)

        # Special handling for parentReceptacles list matching
        if req_key == "parentReceptacles" and isinstance(req_val, list):
            if not isinstance(cur_val, list):
                reasons.append(
                    f"{req_key} mismatch: Expected list {req_val}, found {type(cur_val)} {cur_val}"
                )
                continue

            # Check if all req items are in cur_val (prefix match)
            missing = []
            for r_item in req_val:
                r_norm = r_item.lower()
                found = False
                for c_item in cur_val:
                    if c_item.lower().startswith(r_norm):
                        found = True
                        break
                if not found:
                    missing.append(r_item)

            if missing:
                reasons.append(
                    f"{req_key} mismatch: Missing {missing}. Found: {cur_val}"
                )

        elif cur_val != req_val:
            reasons.append(f"{req_key} mismatch: Expected {req_val}, found {cur_val}")

    return reasons


def _sum_durations(events, start_idx, end_idx):
    total = 0.0
    for i in range(start_idx, end_idx + 1):
        val = events[i].get("duration", 0.0)
        try:
            total += float(val)
        except (TypeError, ValueError):
            total += 0.0
    return total


def analyze_task_failure(task_name, snapshots, events, task_data_json=None):
    if not TASK_SPECS:
        return "TASK_SPECS empty"

    spec = TASK_SPECS.get(task_name)
    if not spec:
        normalized = task_name.lower().replace(" and ", "_and_").replace(" ", "_")
        spec = TASK_SPECS.get(normalized)

    if not spec:
        return f"Spec not found for task: {task_name}"

    report_lines = []

    # Check what actually failed according to the JSON result
    gcr_failed = False
    tsr_failed_map = {}

    if task_data_json:
        if not task_data_json.get("gcr_satisfied"):
            gcr_failed = True

        tsrs_data = task_data_json.get("tsrs", {})
        for t_name, t_data in tsrs_data.items():
            if t_data.get("passed") is False:
                tsr_failed_map[t_name] = t_data.get("duration")

    # --- GCR Analysis ---
    report_lines.append(f"Analyzing Task: {task_name}")

    if gcr_failed:
        report_lines.append("  [Overall GCR]: FAILED in Evaluation Result")
    else:
        report_lines.append("  [Overall GCR]: PASSED in Evaluation Result")

    # 1. GCR Mid Groups
    if spec.gcr_mid_groups:
        report_lines.append("  [GCR Mid-Conditions]")
        for i, group in enumerate(spec.gcr_mid_groups):
            satisfied_step = -1
            failure_reasons = []

            for idx, state in enumerate(snapshots):
                errors = []
                for obj_cond in group.objects:
                    diags = diagnose_condition(state, obj_cond)
                    errors.extend(diags)
                if not errors:
                    satisfied_step = idx
                    break
                if idx == len(snapshots) - 1:
                    failure_reasons = errors

            if satisfied_step != -1:
                report_lines.append(f"    Group {i+1}: PASSED at step {satisfied_step}")
            else:
                report_lines.append(f"    Group {i+1}: FAILED. Never met.")
                report_lines.append(f"      Reasons (last state):")
                for r in failure_reasons:
                    report_lines.append(f"        - {r}")

    # 2. GCR End
    if spec.gcr_end:
        report_lines.append("  [GCR End-Condition]")

        last_state = snapshots[-1]
        errors = []
        for obj_cond in spec.gcr_end.objects:
            diags = diagnose_condition(last_state, obj_cond)
            errors.extend(diags)

        if not errors:
            report_lines.append("    PASSED (at final state).")
        else:
            report_lines.append("    FAILED (at final state).")
            for r in errors:
                report_lines.append(f"      - {r}")
    else:
        if not spec.gcr_mid_groups:
            report_lines.append("  (No GCR Mid or End conditions defined)")

    # --- TSR Analysis ---
    tsrs = spec.tsrs if spec.tsrs else []
    if tsrs:
        report_lines.append("  [TSR Analysis]")
        for tsr in tsrs:

            # Label if this specific TSR failed in JSON
            is_failed_in_eval = tsr.name in tsr_failed_map
            status_str = "FAILED" if is_failed_in_eval else "PASSED"
            report_lines.append(f"    TSR '{tsr.name}' ({status_str} in Eval):")

            # Trigger
            trigger_step = -1
            trigger_failure_reasons = []

            for idx, state in enumerate(snapshots):
                errors = []
                for obj_cond in tsr.trigger.objects:
                    diags = diagnose_condition(state, obj_cond)
                    errors.extend(diags)

                if not errors:
                    trigger_step = idx
                    break

                if idx == len(snapshots) - 1:
                    trigger_failure_reasons = errors

            if trigger_step != -1:
                report_lines.append(f"      Trigger: PASSED at step {trigger_step}")
            else:
                report_lines.append(f"      Trigger: FAILED. Condition never met.")
                report_lines.append(f"        Last state reasons:")
                for r in trigger_failure_reasons:
                    report_lines.append(f"          - {r}")

                # Additional Diagnostics for Trigger Failure
                relevant_actions = []
                trigger_objects = [
                    o.object_name_prefix.lower() for o in tsr.trigger.objects
                ]

                for i, evt in enumerate(events):
                    action = evt.get("primitive_action", "")
                    for obj in trigger_objects:
                        if obj in action.lower():
                            relevant_actions.append(f"Step {i}: {action}")

                if relevant_actions:
                    report_lines.append(
                        f"        Relevant actions found in log (last 5):"
                    )
                    for ra in relevant_actions[-5:]:
                        report_lines.append(f"          {ra}")
                else:
                    report_lines.append(
                        f"        No relevant actions found involving trigger objects."
                    )
                continue  # Skip End analysis if Trigger failed

            # End
            end_step = -1
            end_failure_reasons = []

            for idx in range(trigger_step, len(snapshots)):
                state = snapshots[idx]
                errors = []
                for obj_cond in tsr.end.objects:
                    diags = diagnose_condition(state, obj_cond)
                    errors.extend(diags)

                if not errors:
                    end_step = idx
                    break

                if idx == len(snapshots) - 1:
                    end_failure_reasons = errors

            if end_step != -1:
                report_lines.append(f"      End: PASSED at step {end_step}")

                # Check Duration if FAILED in eval but PASSED trigger/end
                if is_failed_in_eval:
                    # Calculate duration exactly like evaluator
                    if end_step - trigger_step <= 1:
                        tsr_duration = 0.0
                    else:
                        tsr_duration = _sum_durations(
                            events, trigger_step + 1, end_step - 1
                        )

                    report_lines.append(f"      [Duration Check]:")
                    report_lines.append(
                        f"        Calculated Duration: {tsr_duration:.2f}"
                    )
                    report_lines.append(
                        f"        Target: {TIMING_TOLERANCE_DEFAULT}, Tolerance: {TIMING_TOLERANCE_ABS}"
                    )

                    diff = abs(tsr_duration - TIMING_TOLERANCE_DEFAULT)
                    if diff > TIMING_TOLERANCE_ABS:
                        report_lines.append(
                            f"        -> FAILED: Duration {tsr_duration:.2f} is out of tolerance (diff={diff:.2f} > {TIMING_TOLERANCE_ABS})"
                        )
                    else:
                        report_lines.append(
                            f"        -> WARNING: Duration seems OK locally but failed in JSON log (val={tsr_failed_map[tsr.name]})."
                        )

            else:
                report_lines.append(
                    f"      End: FAILED. Condition never met after trigger."
                )
                report_lines.append(f"        Last state reasons:")
                for r in end_failure_reasons:
                    report_lines.append(f"          - {r}")

    return "\n".join(report_lines)


def main():
    print(
        "Running Enhanced Diagnostic Version (with GCR Analysis & Status Check & Duration)"
    )
    root_dir = "assets/results"
    states_dirs = find_states_dirs(root_dir)

    differing_cases = []
    print(f"Scanning {len(states_dirs)} states directories...")

    for states_dir in states_dirs:
        for root, dirs, files in os.walk(states_dir):
            if "dag_edf" not in dirs:
                continue

            # Find all bayesian directories
            bayesian_dirs = [d for d in dirs if d.startswith("dag_bayesian_")]
            if not bayesian_dirs:
                continue

            # Load EDF data
            edf_path = os.path.join(root, "dag_edf", "evaluation_result.json")
            if not os.path.exists(edf_path):
                continue

            try:
                with open(edf_path, "r") as f:
                    e_data = json.load(f)
            except Exception:
                continue

            e_failed_tasks = get_failed_tasks(e_data)

            # Compare each bayesian folder
            for bayes_dir in bayesian_dirs:
                bayesian_path = os.path.join(root, bayes_dir, "evaluation_result.json")
                if not os.path.exists(bayesian_path):
                    continue

                try:
                    with open(bayesian_path, "r") as f:
                        b_data = json.load(f)

                    b_failed_tasks = get_failed_tasks(b_data)

                    # We are looking for cases where Bayesian Failed AND EDF Passed
                    if b_failed_tasks and not e_failed_tasks:
                        task_name = b_failed_tasks[0]
                        traj_path = os.path.join(root, bayes_dir, "trajectory_log.json")

                        # Pass the specific task data to analyze_task_failure
                        task_data_json = b_data.get("tasks", {}).get(task_name)

                        analysis = "Log not found"
                        if os.path.exists(traj_path):
                            events = load_events_from_file(Path(traj_path))
                            snapshots = accumulate_state_changes(events)
                            analysis = analyze_task_failure(
                                task_name, snapshots, events, task_data_json
                            )

                        differing_cases.append(
                            {
                                "approach": bayes_dir,
                                "eval_path": bayesian_path,
                                "traj_path": traj_path,
                                "task_name": task_name,
                                "analysis": analysis,
                            }
                        )
                except Exception as e:
                    print(f"Error processing {bayesian_path}: {e}")

    differing_cases.sort(key=lambda x: (x["approach"], x["eval_path"]))

    output_file = "differing_cases_report.txt"
    with open(output_file, "w") as f:
        f.write("Cases where dag_bayesian_* failed but dag_edf did not:\n")
        f.write(
            "================================================================================================\n"
        )
        if not differing_cases:
            f.write("No matching cases found.\n")

        for case in differing_cases:
            f.write(f"Approach: {case['approach']}\n")
            f.write(f"Eval Path: {case['eval_path']}\n")
            f.write(f"Traj Path: {case['traj_path']}\n")
            f.write(f"Failed Task: {case['task_name']}\n")
            f.write(f"Analysis:\n{case['analysis']}\n")
            f.write("-" * 80 + "\n")
            f.write("\n")

    print(f"Found {len(differing_cases)} cases. Saved to {output_file}")


if __name__ == "__main__":
    main()
