import copy
import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from core.dataclass import ActionResult, Candidate, Deadline, SimulationNode, TimeSlot
from core.task import Subtask

# from scheduler.action_handler import ActionHandler
from src.utils.config import EPSILON, LARGE_NUMBER, LOG_ROUND

# [추가됨] TYPE_CHECKING 블록 내에서만 ActionHandler 임포트
if TYPE_CHECKING:
    from scheduler.action_handler import ActionHandler

log = logging.getLogger(__name__)

# Define a tolerance for critical task start time checks
CRITICAL_TIME_TOLERANCE = 0.05  # Example: 50ms tolerance, adjust as needed


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
        Determines feasible and not-yet-feasible candidates from the current state.
        Adjusts start times based on navigation estimates and checks against current time.
        """
        feasible_candidates: List[Candidate] = []
        not_yet_candidates: List[Candidate] = []

        current_time = curr_node.state.current_time
        remaining_subtasks = curr_node.state.remaining_subtasks
        log.debug(
            f"Checking {len(remaining_subtasks)} remaining subtasks at time {current_time:.2f}"
        )

        for sub in remaining_subtasks:
            # 1. 논리적 제약 조건 확인 (선행 태스크 완료 여부, 시간 제약)
            logical_start_time, is_critical, status = self.get_earliest_start_time(
                curr_node, sub
            )

            # 선행 태스크 실패 또는 제약 조건 오류 시 후보에서 제외
            if (
                status == "FAILED_PREDECESSOR"
                or status == "CONSTRAINT_ERROR"
                or status == "CONFLICT"
            ):
                log.warning(
                    f"Subtask '{sub.name}' cannot be scheduled due to status: {status}. Skipping."
                )
                continue

            # 선행 태스크 미완료 시 not_yet 후보로 분류 (status == "NOT_READY")
            if logical_start_time is None or status == "NOT_READY":
                log.debug(
                    f"Subtask '{sub.name}' is not yet ready (predecessors not finished). Adding to not_yet_candidates."
                )
                # not_yet 후보에 필요한 정보 추가 (예: 예상 준비 시간 등)
                # 여기서는 Candidate 객체만 추가하고, 추후 deadline 할당 등에서 활용 가능
                not_yet_candidates.append(
                    Candidate(subtask=sub, is_critical=is_critical, status="NOT_READY")
                )  # status 추가
                continue

            # 2. 물리적 제약 조건 확인 (네비게이션 시간 등)
            #    - 현재 위치에서 서브태스크 시작 위치까지 네비게이션 시간 예측
            #    - 서브태스크 실행에 필요한 자원 가용성 확인 (예: 특정 도구, 공간 등 - 현재 미구현)
            estimated_nav_time = 0.0
            try:
                # 첫 번째 액션(주로 네비게이션)을 기반으로 시간 예측 시도
                first_action = (
                    sub.execution.primitive_actions[0]
                    if sub.execution and sub.execution.primitive_actions
                    else None
                )
                if first_action and first_action.upper().startswith("NAVIGATE_TO"):
                    # ActionHandler를 사용하여 네비게이션 시간 예측
                    # 주의: get_actions_info는 실제 시뮬레이션 기반일 수 있으므로 비용이 클 수 있음
                    # 더 가벼운 예측 함수가 ActionHandler에 필요할 수 있음
                    nav_info: Optional[ActionResult] = (
                        self.action_handler.get_actions_info(curr_node, [first_action])
                    )
                    if nav_info:
                        estimated_nav_time = (
                            nav_info.action_duration
                        )  # action_duration이 순수 네비게이션 시간을 나타낸다고 가정
                    else:
                        log.warning(
                            f"Could not estimate navigation time for '{first_action}' for subtask '{sub.name}'. Assuming 0."
                        )
                # 다른 종류의 첫 액션에 대한 준비 시간 예측 로직 추가 가능
            except Exception as e_nav_est:
                log.error(
                    f"Error estimating preparation time for subtask '{sub.name}': {e_nav_est}",
                    exc_info=True,
                )
                # 예측 실패 시 안전하게 0으로 처리하거나 후보에서 제외할 수 있음

            # 3. 최종 시작 가능 시간 계산 및 Feasibility 판단
            #    물리적 준비 시간(네비게이션) + 논리적 시작 가능 시간
            earliest_possible_start_time = logical_start_time + estimated_nav_time

            # 현재 시간 이후에만 시작 가능
            adjusted_start_time = max(current_time, earliest_possible_start_time)

            # 최종 후보 생성
            candidate = Candidate(
                subtask=sub,
                is_critical=is_critical,
                status=status,  # "COMPLETED" 또는 다른 유효 상태
                logical_start_time=logical_start_time,
                estimated_nav_time=estimated_nav_time,
                earliest_start_time=adjusted_start_time,  # 최종 조정된 시작 시간
            )

            # 현재 시간에 즉시 시작 가능한 경우 feasible
            if adjusted_start_time <= current_time + EPSILON:
                log.debug(
                    f"Subtask '{sub.name}' is feasible now. Adjusted start: {adjusted_start_time:.2f}"
                )
                feasible_candidates.append(candidate)
            else:
                # 즉시 시작은 불가능하지만, 미래에 가능할 것으로 예상되는 경우 not_yet
                log.debug(
                    f"Subtask '{sub.name}' is not yet feasible (requires nav/wait). Adjusted start: {adjusted_start_time:.2f}. Adding to not_yet_candidates."
                )
                not_yet_candidates.append(candidate)

        return feasible_candidates, not_yet_candidates

    def get_earliest_start_time(
        self, curr_node: SimulationNode, sub: Subtask
    ) -> Tuple[Optional[float], bool, str]:
        """
        Calculates the logical earliest start time for subtask 'sub' based on
        predecessor completion times and constraint intervals.
        Returns: (earliest_start_time, is_critical, status)
        Status can be: "COMPLETED", "NOT_READY", "FAILED_PREDECESSOR", "CONSTRAINT_ERROR", "CONFLICT"
        """
        curr_constraints = curr_node.state.constraints
        if not curr_constraints or not isinstance(curr_constraints, nx.DiGraph):
            log.error(
                f"Invalid constraint graph provided for state at time {curr_node.state.current_time:.2f}. Cannot process subtask '{sub.name}'."
            )
            return None, False, "CONSTRAINT_ERROR"

        if sub.name not in curr_constraints:
            log.debug(
                f"Subtask '{sub.name}' not found in constraint graph. Assuming ready at time 0."
            )
            # 제약 그래프에 없는 태스크는 선행 조건 없이 즉시 가능하다고 간주 (시간 0)
            return 0.0, False, "COMPLETED"  # 상태 COMPLETED로 명시

        if not nx.is_directed_acyclic_graph(curr_constraints):
            log.error(
                f"CONSTRAINT ERROR: Cycle detected in the constraint graph for state at time {curr_node.state.current_time:.2f}! "
                f"Cannot reliably calculate earliest start time for '{sub.name}'. Check constraint update logic."
            )
            return None, False, "CONSTRAINT_ERROR"

        # Create a map for faster lookup of completed task entries
        completed_subtasks_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_subtasks
        }

        # Get incoming edges (predecessors)
        in_edges = list(curr_constraints.in_edges(sub.name, data=True))
        if not in_edges:
            # No predecessors, can start immediately
            log.debug(f"Subtask '{sub.name}' has no predecessors. Ready at time 0.")
            return 0.0, False, "COMPLETED"

        critical_times = []
        non_critical_earliest_start = 0.0
        all_predecessors_finished = True
        any_predecessor_failed = False

        for pred_name, _, edge_data in in_edges:
            info = edge_data.get("info", {})
            interval = float(
                info.get("Interval", 0.0)
            )  # Time gap after predecessor ends
            is_crit = info.get(
                "IsCritical", False
            )  # Is this a critical timing constraint?

            # Find the completion entry for the predecessor
            pred_entry = completed_subtasks_map.get(pred_name)

            if not pred_entry:
                # If any predecessor is not yet completed
                all_predecessors_finished = False
                log.debug(
                    f"Predecessor '{pred_name}' for '{sub.name}' not completed yet."
                )
                # Continue checking other predecessors for potential failures, but cannot determine start time yet
                continue  # Cannot calculate start time if a predecessor is not finished

            # --- Check predecessor execution status ---
            try:
                # Use getattr for safe access
                pred_status = getattr(
                    pred_entry.subtask, "execution_status", True
                )  # 기본값을 True로 간주 (상태 기록이 없는 경우 성공으로 가정)
                if pred_status is None:
                    # 속성 자체가 없거나 값이 None인 경우 (이 경우는 위 기본값 True로 인해 거의 발생 안 함)
                    log.warning(
                        f"Predecessor '{pred_name}' for '{sub.name}' completed but 'execution_status' is None. Assuming SUCCESS based on default."
                    )
                    pred_status = True  # 명시적으로 True 설정
                elif pred_status is False:
                    # If any predecessor explicitly failed
                    any_predecessor_failed = True
                    log.warning(
                        f"Predecessor '{pred_name}' for '{sub.name}' FAILED execution. '{sub.name}' cannot start."
                    )
                    break  # Exit the loop early

            except Exception as e_status:  # 예상치 못한 다른 에러 발생 시
                log.error(
                    f"Error accessing execution_status for predecessor '{pred_name}': {e_status}. Treating as FAILED.",
                    exc_info=True,
                )
                any_predecessor_failed = True
                break  # 이 서브태스크는 실행 불가, 루프 중단

            # --- Calculate potential start time based on this predecessor ---
            # (any_predecessor_failed가 True면 이 부분은 실행되지 않음)
            pred_end_time = pred_entry.end_time
            candidate_start_time = pred_end_time + interval

            if is_crit:
                critical_times.append(candidate_start_time)
            else:
                # For non-critical, the task can only start after the latest predecessor finishes
                non_critical_earliest_start = max(
                    non_critical_earliest_start, candidate_start_time
                )

        # --- Determine final result based on checks ---
        if any_predecessor_failed:
            # If any predecessor failed, return FAILED status
            return None, False, "FAILED_PREDECESSOR"

        if not all_predecessors_finished:
            # If predecessors are okay so far but not all finished, return None status
            return None, False, "NOT_READY"

        # --- Check for conflicts if all predecessors completed successfully ---
        final_start_time = 0.0
        is_final_critical = False

        if critical_times:
            # If there are critical constraints, find the earliest and latest required start times
            earliest_critical_time = min(critical_times)
            latest_critical_time = max(critical_times)

            # Check for conflicting critical times
            if abs(earliest_critical_time - latest_critical_time) > EPSILON:
                log.error(
                    f"CRITICAL CONSTRAINT CONFLICT for '{sub.name}': Multiple distinct critical start times required by predecessors: {sorted(critical_times)}. "
                    f"This indicates an issue in the constraint graph definition or update logic. "
                    f"Cannot resolve conflict. Marking as infeasible."
                )
                # Policy: Use the latest required critical time in case of conflict.
                return None, True, "CONFLICT"
            else:
                # All critical times agree
                final_start_time = earliest_critical_time

            is_final_critical = True

            # Check if the (latest) critical time conflicts with non-critical time
            if final_start_time < non_critical_earliest_start - EPSILON:
                log.error(
                    f"CRITICAL/NON-CRITICAL CONFLICT for '{sub.name}': Required critical start time {final_start_time:.2f} "
                    f"is EARLIER than latest non-critical requirement {non_critical_earliest_start:.2f}. "
                    f"This indicates an issue in the constraint graph definition or update logic. "
                    f"Cannot resolve conflict. Marking as infeasible."
                )
                # Policy: Respect the non-critical dependency, use the later time.
                return None, True, "CONFLICT"
                # is_final_critical remains True because a critical constraint was involved.
        else:
            # No critical constraints, determined by latest non-critical predecessor
            final_start_time = non_critical_earliest_start
            is_final_critical = False

        log.debug(
            f"Subtask '{sub.name}' ready at {final_start_time:.2f} (Critical: {is_final_critical})"
        )
        return (final_start_time, is_final_critical, "COMPLETED")

    def _assign_deadlines(
        self,
        feasible: List[Candidate],
        not_yet: List[Candidate],
        curr_node: SimulationNode,
    ) -> List[Candidate]:
        """
        Assigns deadlines to feasible candidates based on the earliest upcoming
        critical task found in the not_yet list (excluding those already missed).
        """
        # Find the earliest start time among upcoming critical tasks THAT HAVE NOT BEEN MISSED
        crit_candidates = [
            c
            for c in not_yet
            if c.is_critical and c.status != "MISSED_CRITICAL"  # 상태 확인 추가
        ]
        # --- 수정: logical_start_time 기준으로 정렬 ---
        # 데드라인은 논리적 시작 시간을 기준으로 설정되어야 함
        crit_candidates.sort(
            key=lambda x: x.logical_start_time
        )  # latest_departure_time 대신 logical_start_time 사용

        if not crit_candidates:
            # No upcoming non-missed critical tasks in the 'not_yet' list
            deadline_time = float("inf")
            deadline_reason_subtask_name = "None"
        else:
            next_crit = crit_candidates[0]
            # The deadline is the logical start time of the next critical task
            # --- 수정: deadline_time을 logical_start_time으로 설정 ---
            deadline_time = (
                next_crit.logical_start_time
            )  # adjusted_start_time(latest_departure_time) 대신 사용
            deadline_reason_subtask_name = next_crit.subtask.name
            log.debug(
                # f"Next critical task '{deadline_reason_subtask_name}' sets deadline at LogicalEST {deadline_time:.2f}" # 로그 수정
                f"Next critical task '{deadline_reason_subtask_name}' sets deadline at LogicalEST {deadline_time:.2f}"  # 로그 수정
            )

        return feasible
