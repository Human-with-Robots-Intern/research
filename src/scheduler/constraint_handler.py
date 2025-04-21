import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from networkx import DiGraph

from core.dataclass import Candidate, Deadline, SimulationNode, TimeSlot
from core.task import Subtask

# from scheduler.action_handler import ActionHandler
from src.utils.config import EPSILON, LOG_ROUND

# [추가됨] TYPE_CHECKING 블록 내에서만 ActionHandler 임포트
if TYPE_CHECKING:
    from scheduler.action_handler import ActionHandler

log = logging.getLogger(__name__)


class ConstraintHandler:

    def __init__(self, action_handler: "ActionHandler"):
        """
        ConstraintHandler 초기화. ActionHandler 인스턴스를 주입받습니다.
        """
        self.action_handler = action_handler
        log.debug("ConstraintHandler initialized with ActionHandler.")

    def get_time_slots(
        self, subtask_name: str, constraints: DiGraph, direction: str
    ) -> List[TimeSlot]:
        edges = (
            list(constraints.out_edges(subtask_name, data=True))
            if direction == "out"
            else list(constraints.in_edges(subtask_name, data=True))
        )

        if not edges:
            return []

        time_slots = []

        for u, v, data in edges:
            interval = data.get("info", {}).get("Interval", 0.0)
            is_crit = data.get("info", {}).get("IsCritical", False)
            linked_subtask = v if direction == "out" else u

            time_slots.append(TimeSlot(float(interval), is_crit, linked_subtask))
        return time_slots

    def get_feasible_candidates(
        self,
        curr_node: SimulationNode,
    ) -> Tuple[List[Candidate], List[Candidate]]:
        """
        현재 상태에서 feasible/not-yet 후보를 결정합니다.
        모든 Task에 대해 네비게이션 시간을 고려하여 실행 가능 시점(adjusted_start_time)을 조정하고,
        원래의 논리적 시작 시간(logical_start_time)도 함께 저장합니다.
        """

        feasible_candidates: List[Candidate] = []
        not_yet_candidates: List[Candidate] = []

        current_time = curr_node.state.current_time
        remaining_subtasks = curr_node.state.remaining_subtasks

        for sub in remaining_subtasks:
            logical_start_time, is_critical, pred_status = self.get_earliest_start_time(
                curr_node, sub
            )

            if pred_status == "FAILED":
                log.warning(f"Subtask '{sub.name}' 건너뛰기: 선행 작업 실패.")
                continue
            if logical_start_time is None:
                log.debug(f"Subtask '{sub.name}' 실행 불가: 선행 미완료.")
                continue

            estimated_nav_time = 0.0
            try:
                if sub.execution and sub.execution.primitive_actions:
                    first_action = sub.execution.primitive_actions[0]
                    action_type = first_action.split()[0].upper()
                    if action_type == "NAVIGATE_TO":
                        action_info = self.action_handler.get_actions_info(
                            curr_node, [first_action]
                        )
                        estimated_nav_time = (
                            action_info.time_used if action_info else 0.0
                        )
            except (IndexError, AttributeError, Exception) as e:
                log.warning(
                    f"Task '{sub.name}'의 네비게이션 시간 예측 오류: {e}. 이동 시간 0으로 가정."
                )
                estimated_nav_time = 0.0

            adjusted_start_time_val = logical_start_time - estimated_nav_time
            log.debug(
                f"Task '{sub.name}': LogicalEST={logical_start_time:.2f}, NavTime={estimated_nav_time:.2f}, AdjustedEST={adjusted_start_time_val:.2f}"
            )

            candidate_obj = Candidate(
                subtask=sub,
                is_critical=is_critical,
                adjusted_start_time=adjusted_start_time_val,
                logical_start_time=logical_start_time,
            )

            check_time = adjusted_start_time_val

            if is_critical:
                # Case 1: Critical task needs to start exactly now (within EPSILON)
                if abs(current_time - check_time) < EPSILON:
                    feasible_candidates.append(candidate_obj)
                # Case 2: It's not time yet for the critical task
                elif current_time < check_time:
                    not_yet_candidates.append(candidate_obj)
                # Case 3: We are past the required start time (check_time)
                else:  # current_time > check_time
                    # Log a critical warning, but don't immediately abort the entire search branch.
                    # This candidate is practically infeasible and will likely get a very high
                    # heuristic cost (due to negative slack), effectively pruning it later.
                    log.critical(  # Use critical level for higher visibility
                        f"CRITICAL TIMING POTENTIALLY MISSED for '{sub.name}'! "
                        f"Current Time: {round(current_time, LOG_ROUND)}, "
                        f"Required Start (Adj. EST): {round(check_time, LOG_ROUND)}. "
                        f"This candidate will likely be pruned by heuristic."
                    )
            else:
                if current_time >= check_time - EPSILON:
                    feasible_candidates.append(candidate_obj)
                else:
                    not_yet_candidates.append(candidate_obj)

        feasible_candidates = self._assign_deadlines(
            feasible_candidates, not_yet_candidates
        )

        return (feasible_candidates, not_yet_candidates)

    def _assign_deadlines(
        self, feasible: List[Candidate], not_yet: List[Candidate]
    ) -> List[Candidate]:
        crit_candidates = [c for c in not_yet if c.is_critical]
        crit_candidates.sort(key=lambda x: x.adjusted_start_time)

        if not crit_candidates:
            for c in feasible:
                c.deadline = Deadline(float("inf"), None)
            return feasible

        next_crit = crit_candidates[0]
        deadline_time = next_crit.adjusted_start_time
        deadline_reason_subtask_name = next_crit.subtask.name

        for c in feasible:
            c.deadline = Deadline(deadline_time, deadline_reason_subtask_name)
        return feasible

    def get_earliest_start_time(
        self, curr_node: SimulationNode, sub: Subtask
    ) -> Tuple[Optional[float], bool, Optional[str]]:
        """
        서브태스크 'sub'의 논리적 earliest_start 및 선행 상태를 반환.
        (이 함수는 이동 시간을 고려하지 않음)
        반환: (logical_start_time, is_critical, predecessor_status)
              predecessor_status: "COMPLETED", "FAILED", or None
        """
        curr_constraints = curr_node.state.constraints
        completed_subtasks_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_subtasks
        }

        if sub.name not in curr_constraints:
            log.warning(
                f"Subtask '{sub.name}' not found in constraint graph. Assuming start time 0."
            )
            return (0.0, False, "COMPLETED")

        in_edges = list(curr_constraints.in_edges(sub.name, data=True))
        if not in_edges:
            return (0.0, False, "COMPLETED")

        critical_times = []
        non_critical_earliest_start = 0.0
        all_predecessors_finished = True
        any_predecessor_failed = False

        for pred_name, _, edge_data in in_edges:
            info = edge_data.get("info", {})
            interval = float(info.get("Interval", 0.0))
            is_crit = info.get("IsCritical", False)

            pred_entry = completed_subtasks_map.get(pred_name)

            if not pred_entry:
                all_predecessors_finished = False
                continue

            pred_status = getattr(pred_entry.subtask, "execution_status", None)
            if pred_status is False:
                any_predecessor_failed = True
                log.warning(f"Predecessor '{pred_name}' for '{sub.name}' FAILED.")
                break

            pred_end_time = pred_entry.end_time
            candidate_start = pred_end_time + interval
            if is_crit:
                critical_times.append(candidate_start)
            else:
                non_critical_earliest_start = max(
                    non_critical_earliest_start, candidate_start
                )

        if any_predecessor_failed:
            return (None, False, "FAILED")
        if not all_predecessors_finished:
            return (None, False, None)

        if critical_times:
            first_crit_time = critical_times[0]
            for ct in critical_times[1:]:
                if abs(first_crit_time - ct) > EPSILON:
                    log.error(
                        f"CONFLICT: Multiple distinct critical times for '{sub.name}': {critical_times}."
                    )
                    return (None, False, "FAILED")
            if first_crit_time < non_critical_earliest_start - EPSILON:
                log.error(
                    f"CONFLICT: Critical start {first_crit_time:.2f} for '{sub.name}' before non-critical {non_critical_earliest_start:.2f}."
                )
                return (None, False, "FAILED")
            return (first_crit_time, True, "COMPLETED")
        else:
            return (non_critical_earliest_start, False, "COMPLETED")
