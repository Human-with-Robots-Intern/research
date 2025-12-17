import os
import json
import glob
import sys
import re
from collections import defaultdict
from pathlib import Path

# Add project root to path to allow imports
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Mock colorlog to bypass import error in logger utils
import types
mock_colorlog = types.ModuleType("colorlog")
mock_colorlog.ColoredFormatter = lambda *args, **kwargs: None
sys.modules["colorlog"] = mock_colorlog

try:
    from assets.result_analysis.utils.specs import TASK_SPECS, ConditionGroup
    from assets.result_analysis.utils.state_change_simulate import accumulate_state_changes, load_events_from_file
    from assets.result_analysis.utils.evaluator import (
        _group_satisfied, 
        _evaluate_gcr_mid_with_steps,
        _find_object_state_for_prefix,
        _property_matches
    )
    from src.utils.config.constants import TIMING_TOLERANCE_DEFAULT, TIMING_TOLERANCE_ABS
except ImportError as e:
    print(f"Warning: Could not import analysis modules. Detailed diagnosis will be skipped. Error: {e}")
    TASK_SPECS = {}

def get_missing_properties(snapshot, group: ConditionGroup):
    """Identify which properties in a condition group are missing/mismatched in the snapshot."""
    missing = []
    for cond in group.objects:
        props = _find_object_state_for_prefix(snapshot, cond.object_name_prefix)
        if props is None:
            missing.append(f"Object '{cond.object_name_prefix}' not found")
            continue
        
        for key, expected in cond.required_properties.items():
            if key not in props:
                missing.append(f"{cond.object_name_prefix}.{key} missing (expected {expected})")
            elif not _property_matches(key, props[key], expected):
                missing.append(f"{cond.object_name_prefix}.{key} is {props[key]} (expected {expected})")
    return missing

def diagnose_task_failure(task_name, traj_path):
    """Perform deep analysis of why a task failed."""
    if task_name not in TASK_SPECS:
        return ["Task spec not found for diagnosis"]
    
    spec = TASK_SPECS[task_name]
    
    try:
        if not os.path.exists(traj_path):
            return ["Trajectory log missing"]
            
        events = load_events_from_file(Path(traj_path))
        snapshots = accumulate_state_changes(events)
        end_state = snapshots[-1] if snapshots else {}
        
        diagnosis = []
        
        # 1. Analyze GCR End Failure
        if spec.gcr_end:
            if not _group_satisfied(end_state, spec.gcr_end):
                missing = get_missing_properties(end_state, spec.gcr_end)
                diagnosis.append(f"[GCR End Failed] Final state unmet: {', '.join(missing)}")
        
        # 2. Analyze GCR Mid Failure
        if spec.gcr_mid_groups:
            # Check which mid groups were missed
            passed, satisfied_steps = _evaluate_gcr_mid_with_steps(snapshots, spec.gcr_mid_groups)
            if not passed:
                # Find the specific group that failed
                for idx, group in enumerate(spec.gcr_mid_groups):
                    # Check if this specific group was ever satisfied
                    is_sat = False
                    for snap in snapshots:
                        if _group_satisfied(snap, group):
                            is_sat = True
                            break
                    if not is_sat:
                        # Construct readable description of the missed step
                        desc = []
                        for obj in group.objects:
                            props = [f"{k}={v}" for k,v in obj.required_properties.items()]
                            desc.append(f"{obj.object_name_prefix}({','.join(props)})")
                        diagnosis.append(f"[GCR Mid Failed] Missed intermediate step: {' AND '.join(desc)}")

        # 3. Analyze TSR Failure (Logic mirrors evaluator.py but adds descriptive text)
        if spec.tsrs:
            for tsr_spec in spec.tsrs:
                # We assume we want to re-evaluate to check timing details
                # But simple way is to check the JSON result if available.
                # Here we do a quick re-calc or use general timing info.
                # Let's import constants if possible or use defaults
                target = TIMING_TOLERANCE_DEFAULT
                tol = TIMING_TOLERANCE_ABS
                
                # ... (Logic similar to _evaluate_single_tsr to find duration) ...
                # Since we want to provide "Reason", let's rely on the already computed duration in the caller
                # This function is called with context, maybe we can pass the failed TSR info from JSON?
                pass 
                
        return diagnosis
        
    except Exception as e:
        return [f"Diagnosis error: {e}"]

def analyze_tsr_interval(events, trigger_idx, end_idx):
    """Analyze what happened during the TSR interval based on DURATION."""
    if trigger_idx is None or end_idx is None:
        return ""
    
    action_durations = defaultdict(float)
    total_duration = 0.0
    
    start = trigger_idx + 1
    end = end_idx 
    
    if start >= end:
        return " (Immediate transition)"
        
    for i in range(start, end):
        if i < len(events):
            event = events[i]
            act = event.get("primitive_action", "").split(" ")[0]
            dur = float(event.get("duration", 0.0))
            
            action_durations[act] += dur
            total_duration += dur
            
    if total_duration <= 0.001:
        return ""
        
    # Get ALL actions sorted by time spent
    sorted_actions = sorted(action_durations.items(), key=lambda x: x[1], reverse=True)
    
    # Format: ACTION 12.3s (45%)
    desc_parts = []
    for k, v in sorted_actions:
        # Ignore negligible durations (<0.1%) to keep string clean, unless it's very short overall
        percent = (v / total_duration) * 100
        if percent < 0.1 and total_duration > 1.0:
            continue
        desc_parts.append(f"{k} {v:.1f}s ({percent:.0f}%)")
        
    desc = ", ".join(desc_parts)
    return f" [Actions: {desc}]"

def diagnose_tsr_trigger_failure(tsr_spec, snapshots):
    """Find out why the trigger was never met."""
    # Check what was missing in the trigger condition throughout the trajectory
    # We look for the 'closest' attempt or the most common missing prop
    
    from collections import Counter
    missing_counter = Counter()
    
    for snap in snapshots:
        missing = get_missing_properties(snap, tsr_spec.trigger)
        for m in missing:
            missing_counter[m] += 1
            
    # If snapshots exist but trigger never met
    if not snapshots:
        return "No states recorded"
        
    # Get the most persistent missing properties
    # If a property is missing in 100% of steps, it's a hard blocker
    total_steps = len(snapshots)
    persistent = [k for k, v in missing_counter.items() if v > total_steps * 0.9]
    
    if persistent:
        return f"Consistently missing: {', '.join(persistent[:2])}"
    
    # Otherwise, show what was missing in the last step
    last_missing = get_missing_properties(snapshots[-1], tsr_spec.trigger)
    return f"Ended with missing: {', '.join(last_missing[:2])}"

def format_tsr_failure(tsr_name, tsr_info, events, snapshots, tsr_spec=None):
    """Format TSR failure reason with deep analysis."""
    if not tsr_info.get("passed", False):
        duration = tsr_info.get("duration")
        
        # Case 1: Trigger never met
        if duration is None:
            reason = f"TSR '{tsr_name}' failed: Trigger condition never met"
            if tsr_spec and snapshots:
                diagnosis = diagnose_tsr_trigger_failure(tsr_spec, snapshots)
                reason += f" ({diagnosis})"
            return reason
        
        # Case 2: Timing failure
        target = TIMING_TOLERANCE_DEFAULT
        try:
            target = TIMING_TOLERANCE_DEFAULT
        except:
            pass
            
        diff = duration - target
        trigger_step = tsr_info.get("trigger_step")
        end_step = tsr_info.get("end_step")
        
        # Analyze activity during the interval
        activity_summary = ""
        if trigger_step is not None and end_step is not None:
             activity_summary = analyze_tsr_interval(events, trigger_step, end_step)
            
        if abs(diff) > 2.0:
            status = "Too Long" if diff > 0 else "Too Short"
            return f"TSR '{tsr_name}' failed: Duration {duration:.2f}s is {status} (Target ~{target}s){activity_summary}"
        else:
            return f"TSR '{tsr_name}' failed: Duration {duration:.2f}s (Mismatch){activity_summary}"
    return None

def analyze_failures():
    base_path = "assets/results/states100"
    pattern = os.path.join(base_path, "*", "*", "*", "dag_bayesian_DEFAULT", "evaluation_result.json")
    
    files = glob.glob(pattern)
    print(f"Found {len(files)} files to analyze.")
    
    failure_cases = []
    
    for file_path in files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            is_failure = False
            failure_reasons = []
            
            # Load trajectory for deep analysis
            traj_path = os.path.join(os.path.dirname(file_path), "trajectory_log.json")
            events = []
            snapshots = []
            
            if os.path.exists(traj_path):
                try:
                    events = load_events_from_file(Path(traj_path))
                    snapshots = accumulate_state_changes(events)
                except:
                    pass

            tasks = data.get("tasks", {})
            for task_name, task_info in tasks.items():
                
                # Check GCR
                if not task_info.get("gcr_satisfied", False):
                    is_failure = True
                    failure_reasons.append(f"Task '{task_name}' GCR Failed")
                    
                    if task_name in TASK_SPECS:
                        diagnoses = diagnose_task_failure(task_name, traj_path)
                        for d in diagnoses:
                            failure_reasons.append(f"  -> {d}")
                
                # Check TSRs
                tsrs = task_info.get("tsrs", {})
                for tsr_name, tsr_info in tsrs.items():
                    if not tsr_info.get("passed", False):
                        is_failure = True
                        
                        # Find TSR Spec for diagnosis
                        tsr_spec = None
                        if task_name in TASK_SPECS and TASK_SPECS[task_name].tsrs:
                            for t in TASK_SPECS[task_name].tsrs:
                                if t.name == tsr_name:
                                    tsr_spec = t
                                    break
                        
                        reason = format_tsr_failure(tsr_name, tsr_info, events, snapshots, tsr_spec)
                        failure_reasons.append(reason)

            if is_failure:
                metadata = data.get("metadata", {})
                failure_cases.append({
                    "path": file_path,
                    "traj_path": traj_path,
                    "metadata": metadata,
                    "reasons": failure_reasons
                })
                
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    print(f"\nTotal Failure Cases Found: {len(failure_cases)}")
    
    # Aggregation
    by_difficulty = defaultdict(int)
    by_scene = defaultdict(int)
    by_gcr_object = defaultdict(int) # Object causing GCR failure
    by_tsr_task = defaultdict(int)   # Task causing TSR failure
    
    # Cross Analysis: Scene x Failure
    by_scene_gcr = defaultdict(int)
    by_scene_tsr = defaultdict(int)
    
    for case in failure_cases:
        meta = case['metadata']
        scene = meta.get('scene', 'unknown')
        by_difficulty[meta.get('difficulty', 'unknown')] += 1
        by_scene[scene] += 1
        
        for r in case['reasons']:
            # Analyze GCR failure strings
            if "GCR End Failed" in r or "GCR Mid Failed" in r:
                match = re.search(r"([a-zA-Z0-9_]+)\(", r.split(":")[-1])
                if match:
                    obj = match.group(1)
                    by_gcr_object[obj] += 1
                    by_scene_gcr[f"{scene}::{obj}"] += 1
                else:
                    if "Task '" in r:
                        task = r.split("'")[1]
                        by_gcr_object[f"Task:{task}"] += 1
                        by_scene_gcr[f"{scene}::Task:{task}"] += 1
                        
            # Analyze TSR failure strings
            if "TSR '" in r:
                task_match = re.search(r"TSR '([^']+)'", r)
                if task_match:
                    task = task_match.group(1)
                    by_tsr_task[task] += 1
                    by_scene_tsr[f"{scene}::{task}"] += 1

    # Save detailed report
    report_path = "failure_analysis_report.txt"
    with open(report_path, "w") as f:
        f.write(f"Total Failure Cases Found: {len(failure_cases)}\n\n")
        
        f.write("=== Failures by Difficulty ===\n")
        for k, v in sorted(by_difficulty.items(), key=lambda x: x[1], reverse=True):
            f.write(f"{k}: {v}\n")
        f.write("\n")
        
        f.write("=== Failures by Scene ===\n")
        for k, v in sorted(by_scene.items(), key=lambda x: x[1], reverse=True):
            f.write(f"{k}: {v}\n")
        f.write("\n")
        
        f.write("=== Top GCR Failures (Scene :: Object) ===\n")
        for k, v in sorted(by_scene_gcr.items(), key=lambda x: x[1], reverse=True)[:15]:
            f.write(f"{k}: {v}\n")
        f.write("\n")
        
        f.write("=== Top TSR Failures (Scene :: Task) ===\n")
        for k, v in sorted(by_scene_tsr.items(), key=lambda x: x[1], reverse=True)[:15]:
            f.write(f"{k}: {v}\n")
        f.write("\n")
            
        f.write("=== Detailed Failure Cases ===\n")
        failure_cases.sort(key=lambda x: (x['metadata'].get('difficulty', ''), x['metadata'].get('instruction', '')))
        
        for case in failure_cases:
            meta = case['metadata']
            f.write("-" * 80 + "\n")
            f.write(f"File: {case['path']}\n")
            f.write(f"Difficulty: {meta.get('difficulty')}\n")
            f.write(f"Instruction: {meta.get('instruction')}\n")
            f.write(f"Scene: {meta.get('scene')}\n")
            f.write("Reasons:\n")
            for reason in case['reasons']:
                f.write(f"  - {reason}\n")
            
            # Simple Trajectory summary (Last 3 steps)
            try:
                if os.path.exists(case['traj_path']):
                    with open(case['traj_path'], 'r') as tf:
                        traj = json.load(tf)
                        if traj:
                            f.write("\n  Last Actions:\n")
                            for action in traj[-3:]:
                                f.write(f"    [{action.get('index')}] {action.get('primitive_action')}\n")
            except:
                pass
            f.write("\n")
    
    print(f"\nDetailed report saved to {report_path}")

if __name__ == "__main__":
    analyze_failures()
