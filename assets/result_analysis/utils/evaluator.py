from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.utils.config.constants import TIMING_TOLERANCE_ABS, TIMING_TOLERANCE_DEFAULT
from src.utils.common.logger import create_module_logger
# Prefer shared project logger
from .specs import ConditionGroup, TaskSpec, TSRSpec, TASK_SPECS
from assets.result_analysis.utils.state_change_simulate import accumulate_state_changes
# Import simulator helpers with safe fallback for script execution


logger = create_module_logger(__name__)


def _norm(s: str) -> str:
    """Lowercased and trimmed string for case-insensitive comparisons."""

    return s.strip().lower()


def _name_matches(candidate: str, prefix: str) -> bool:
    """Check if candidate starts with prefix (case-insensitive)."""

    return _norm(candidate).startswith(_norm(prefix))


def _list_contains_all(actual: Sequence[Any], required: Sequence[Any]) -> bool:
    """Return True if all required items are in actual (case-insensitive)."""

    actual_norm = {_norm(str(x)) for x in actual}
    required_norm = {_norm(str(x)) for x in required}
    return required_norm.issubset(actual_norm)


def _list_contains_all_by_prefix(
    actual: Sequence[Any], required: Sequence[Any]
) -> bool:
    """True if for every required r, there exists a in actual with a.startswith(r)."""

    actual_norm = [_norm(str(x)) for x in actual]
    for r in required:
        r_norm = _norm(str(r))
        if not any(a.startswith(r_norm) for a in actual_norm):
            return False
    return True


@dataclass(frozen=True)
class TSRResult:
    """Single TSR evaluation result."""

    name: str  # e.g., "fill", "boil"
    passed: bool
    duration: Optional[float]
    trigger_step: Optional[int]
    end_step: Optional[int]


@dataclass(frozen=True)
class TaskResult:
    """Task evaluation result (GCR/TSR).
    
    For tasks with multiple TSRs, use tsr_results dict.
    """

    name: str
    gcr_pass: bool
    gcr_mid_satisfied_step: Optional[Dict[str, int]] = None
    tsr_results: Optional[Dict[str, TSRResult]] = None


def _property_matches(key: str, actual_value: Any, expected_value: Any) -> bool:
    """Property matching including special handling for parentReceptacles."""

    if isinstance(expected_value, (list, tuple)):
        if not isinstance(actual_value, (list, tuple)):
            return False
        if _norm(key) == "parentreceptacles":
            return _list_contains_all_by_prefix(actual_value, expected_value)
        return _list_contains_all(actual_value, expected_value)
    return actual_value == expected_value


def _find_object_state_for_prefix(
    snapshot: Mapping[str, Mapping[str, Any]], name_prefix: str
) -> Optional[Mapping[str, Any]]:
    """Find first object state in snapshot whose name starts with prefix."""

    for obj_name, props in snapshot.items():
        if _name_matches(obj_name, name_prefix):
            return props
    return None


def _group_satisfied(
    snapshot: Mapping[str, Mapping[str, Any]], group: ConditionGroup
) -> bool:
    """Check if all conditions in the group are satisfied simultaneously."""

    for cond in group.objects:
        props = _find_object_state_for_prefix(snapshot, cond.object_name_prefix)
        if props is None:
            return False
        for key, expected in cond.required_properties.items():
            if key not in props:
                return False
            if not _property_matches(key, props[key], expected):
                return False
    return True


def _evaluate_gcr_end(
    end_state: Mapping[str, Mapping[str, Any]],
    gcr_end: Optional[ConditionGroup],
) -> bool:
    """Evaluate GCR end condition on end_state."""

    if gcr_end is None:
        return True
    return _group_satisfied(end_state, gcr_end)


def _evaluate_gcr_mid_with_steps(
    snapshots: Sequence[Mapping[str, Mapping[str, Any]]],
    groups: Optional[Sequence[ConditionGroup]],
) -> Tuple[bool, Optional[Dict[str, int]]]:
    """Evaluate mid conditions and return (passed, dict_of_satisfied_steps).
    
    Returns a dict mapping generated group names to their satisfied step indices.
    """

    if not groups:
        return True, None
    
    steps_dict = {}
    for idx, group in enumerate(groups):
        step = _find_first_step_index(snapshots, group)
        if step is None:
            return False, None
        
        # Generate key name: e.g. "fork_faucet_1"
        obj_names = [obj.object_name_prefix for obj in group.objects]
        base_name = "_".join(obj_names)
        key = f"{base_name}_{idx + 1}"
        steps_dict[key] = step
            
    return True, steps_dict


def _find_first_step_index(
    snapshots: Sequence[Mapping[str, Mapping[str, Any]]], group: ConditionGroup
) -> Optional[int]:
    """Index of first step where group is satisfied."""

    for idx, s in enumerate(snapshots):
        if _group_satisfied(s, group):
            return idx
    return None


def _find_first_step_index_after(
    snapshots: Sequence[Mapping[str, Mapping[str, Any]]],
    group: ConditionGroup,
    start_inclusive: int,
) -> Optional[int]:
    """Index of first step >= start_inclusive where group is satisfied."""

    for idx in range(start_inclusive, len(snapshots)):
        if _group_satisfied(snapshots[idx], group):
            return idx
    return None


def _sum_durations(
    events: Sequence[Mapping[str, Any]],
    start_idx: int,
    end_idx: int,
    duration_key: str = "duration",
) -> float:
    """Sum duration values in events[start_idx..end_idx]."""

    total = 0.0
    for i in range(start_idx, end_idx + 1):
        val = events[i].get(duration_key, 0.0)
        try:
            total += float(val)
        except (TypeError, ValueError):
            logger.warning("Invalid duration value: %s", val)
            total += 0.0
    return total


def _sum_all_durations(
    events: Sequence[Mapping[str, Any]], duration_key: str = "duration"
) -> float:
    """Sum all duration values in events."""

    if not events:
        return 0.0
    return _sum_durations(events, 0, len(events) - 1, duration_key=duration_key)


def _evaluate_single_tsr(
    *,
    tsr_spec: TSRSpec,
    snapshots: Sequence[Mapping[str, Mapping[str, Any]]],
    events: Sequence[Mapping[str, Any]],
    duration_key: str = "duration",
    tsr_target_duration: float = TIMING_TOLERANCE_DEFAULT,
    tsr_tolerance: float = TIMING_TOLERANCE_ABS,
) -> TSRResult:
    """Evaluate a single TSR specification.
    
    Duration is calculated between trigger and end steps (exclusive of both endpoints).
    """

    trigger_idx = _find_first_step_index(snapshots, tsr_spec.trigger)
    if trigger_idx is None:
        return TSRResult(
            name=tsr_spec.name,
            passed=False,
            duration=None,
            trigger_step=None,
            end_step=None,
        )

    end_idx = _find_first_step_index_after(snapshots, tsr_spec.end, trigger_idx)
    if end_idx is None:
        return TSRResult(
            name=tsr_spec.name,
            passed=False,
            duration=None,
            trigger_step=trigger_idx,
            end_step=None,
        )

    # Duration 계산: trigger_step과 end_step 제외, 그 사이만 계산
    # trigger_idx와 end_idx가 같거나 연속이면 duration은 0
    if end_idx - trigger_idx <= 1:
        tsr_duration = 0.0
    else:
        # trigger_idx + 1 부터 end_idx - 1 까지
        tsr_duration = _sum_durations(events, trigger_idx + 1, end_idx - 1, duration_key=duration_key)
    if tsr_spec.is_ciritcal:
        tsr_ok = abs(float(tsr_target_duration)- tsr_duration) <= float(tsr_tolerance)
    else:
        tsr_ok = float(tsr_target_duration)- tsr_duration <= float(tsr_tolerance)
    

    return TSRResult(
        name=tsr_spec.name,
        passed=tsr_ok,
        duration=tsr_duration,
        trigger_step=trigger_idx,
        end_step=end_idx,
    )


def evaluate_task(
    *,
    name: str,
    events: Sequence[Mapping[str, Any]],
    task_spec: TaskSpec,
    duration_key: str = "duration",
    tsr_target_duration: float = TIMING_TOLERANCE_DEFAULT,
    tsr_tolerance: float = TIMING_TOLERANCE_ABS,
) -> TaskResult:
    """Evaluate a single task for GCR/TSR."""

    snapshots = accumulate_state_changes(events)
    end_state = snapshots[-1]
    gcr_end_ok = _evaluate_gcr_end(end_state, task_spec.gcr_end)
    gcr_mid_ok, gcr_mid_steps = _evaluate_gcr_mid_with_steps(snapshots, task_spec.gcr_mid_groups)
    gcr_ok = gcr_end_ok and gcr_mid_ok

    tsr_results_dict: Optional[Dict[str, TSRResult]] = None

    if task_spec.tsrs:
        tsr_results_dict = {}
        for tsr_spec in task_spec.tsrs:
            tsr_result = _evaluate_single_tsr(
                tsr_spec=tsr_spec,
                snapshots=snapshots,
                events=events,
                duration_key=duration_key,
                tsr_target_duration=tsr_target_duration,
                tsr_tolerance=tsr_tolerance,
            )
            tsr_results_dict[tsr_spec.name] = tsr_result

    return TaskResult(
        name=name,
        gcr_pass=gcr_ok,
        gcr_mid_satisfied_step=gcr_mid_steps if gcr_ok else None,
        tsr_results=tsr_results_dict,
    )


def evaluate_tasks(
    *,
    events: Sequence[Mapping[str, Any]],
    task_names: Sequence[str],
    duration_key: str = "duration",
) -> Dict[str, TaskResult]:
    """Evaluate multiple tasks by spec keys."""

    result: Dict[str, TaskResult] = {}
    for task_name in task_names:
        spec = TASK_SPECS.get(task_name)
        if spec is None:
            logger.warning("Undefined task spec: %s. Marking as failed GCR/TSR.", task_name)
            result[task_name] = TaskResult(
                name=task_name,
                gcr_pass=False,
            )
            continue
        result[task_name] = evaluate_task(
            name=task_name,
            events=events,
            task_spec=spec,
            duration_key=duration_key,
        )
    return result


def compute_trial_metrics(
    *,
    parsed_tasks: Sequence[str],
    task_results: Mapping[str, TaskResult],
    events: Sequence[Mapping[str, Any]],
    duration_key: str = "duration",
) -> Mapping[str, Any]:
    """Compute trial-level summary metrics for one instruction run (approach).

    Rules:
    - instruction_gcr: 1 if all parsed tasks pass GCR, else 0.
    - tsr: average over tasks with defined TSR only (exclude None).
      If all are None, tsr is None.
    - sr (strict success): 1 if instruction_gcr==1 and
      (tsr is None or tsr >= 0.5); else 0.
    - makespan: sum of all event durations.
    """

    num_tasks = len(parsed_tasks)
    gcr_successes = 0
    tsr_samples: List[float] = []
    for spec_key in parsed_tasks:
        result = task_results.get(spec_key)
        if result is None:
            # Unknown task spec -> treat as failed GCR/TSR
            continue
        if result.gcr_pass:
            gcr_successes += 1        
        # Check tsr_results
        if result.tsr_results:
            all_passed = all(r.passed for r in result.tsr_results.values())
            tsr_samples.append(1.0 if all_passed else 0.0)
    instruction_gcr = 1 if gcr_successes == num_tasks else 0
    tsr: Optional[float]
    if tsr_samples:
        tsr = sum(tsr_samples) / float(len(tsr_samples))
    else:
        tsr = None
    makespan = _sum_all_durations(events, duration_key=duration_key)
    # SR rule
    if instruction_gcr == 1:
        if tsr is None or tsr == 1:
            sr = 1
        else:
            sr = 0
    else:
        sr = 0
    return {"instruction_gcr": instruction_gcr, "tsr": tsr, "sr": sr, "makespan": makespan}


