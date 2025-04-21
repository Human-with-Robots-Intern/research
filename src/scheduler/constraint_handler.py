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
        Adjusts start times based on navigation estimates (from ActionHandler)
        and logical constraints, then checks against current time.
        """
        feasible_candidates: List[Candidate] = []
        not_yet_candidates: List[Candidate] = []

        current_time = curr_node.state.current_time
        remaining_subtasks = curr_node.state.remaining_subtasks

        for sub in remaining_subtasks:
            # 1. 논리적 제약 조건 확인 (선행 태스크 완료 여부, 시간 제약)
            logical_start_time, is_critical, status = self.get_earliest_start_time(
                curr_node, sub
            )

            # 선행 태스크 실패 또는 제약 조건 오류/충돌 시 후보에서 제외
            if status in ["FAILED_PREDECESSOR", "CONSTRAINT_ERROR", "CONFLICT"]:
                log.warning(
                    f"Subtask '{sub.name}' cannot be scheduled due to status: {status}. Skipping."
                )
                continue

            # 선행 태스크 미완료 시 not_yet 후보로 분류
            if (
                status == "NOT_READY"
            ):  # logical_start_time is None when status is NOT_READY
                log.debug(
                    f"Subtask '{sub.name}' is not yet ready (predecessors not finished). Adding to not_yet_candidates."
                )
                # not_yet 후보에 필요한 정보 추가 (예: 예상 준비 시간 등)
                # 여기서는 Candidate 객체만 추가하고, 추후 deadline 할당 등에서 활용 가능
                not_yet_candidates.append(
                    Candidate(subtask=sub, is_critical=is_critical, status="NOT_READY")
                )  # status 추가
                continue

            # 논리적으로는 시작 가능 (status == "COMPLETED" 또는 다른 유효 상태)
            # 이제 물리적 준비 시간(네비게이션 등) 고려

            # 2. 물리적 제약 조건 확인 (네비게이션 시간 등)
            estimated_prep_time = 0.0  # 네비게이션 외 다른 준비 시간도 포함될 수 있음
            try:
                # --- 수정: 첫 액션 기반 준비 시간 예측 (ActionHandler 의존성 명시) ---
                first_action = (
                    sub.execution.primitive_actions[0]
                    if sub.execution and sub.execution.primitive_actions
                    else None
                )
                if first_action:

                    log.debug(
                        f"  Estimating prep time for '{sub.name}' using first action: '{first_action}' via ActionHandler"
                    )
                    prep_info: Optional[ActionResult] = (
                        self.action_handler.get_actions_info(curr_node, [first_action])
                    )
                    if prep_info and prep_info.success:  # 성공적으로 예측된 경우만 사용
                        estimated_prep_time = prep_info.action_duration
                        log.debug(f"    Estimated prep time: {estimated_prep_time:.2f}")
                    elif prep_info and not prep_info.success:
                        log.warning(
                            f"    ActionHandler simulation for first action '{first_action}' FAILED. Assuming 0 prep time, but feasibility check might be inaccurate."
                        )
                        # 실패 시에도 계속 진행하되, 경고 남김 (또는 후보 제외 고려)
                    else:  # prep_info가 None인 경우 (ActionHandler 내부 오류)
                        log.warning(
                            f"    Could not get prep time info for '{first_action}' from ActionHandler. Assuming 0 prep time."
                        )
                else:
                    log.debug(
                        f"  Subtask '{sub.name}' has no actions. Assuming 0 prep time."
                    )
                # --- 수정 끝 ---
            except Exception as e_prep_est:
                log.error(
                    f"  Error estimating preparation time for subtask '{sub.name}': {e_prep_est}",
                    exc_info=True,
                )
                # 예측 실패 시 안전하게 0으로 처리하거나 후보에서 제외 고려

            # 3. 최종 시작 가능 시간 계산 및 Feasibility 판단
            #    논리적 시작 시간과 물리적 준비 완료 시간 중 더 늦은 시간
            #    (현재 시간 + 준비 시간) vs (논리적 시작 시간)
            # --- 수정: 계산 방식 명확화 ---
            # required_prep_finish_time = current_time + estimated_prep_time
            # earliest_possible_start_time = max(logical_start_time, required_prep_finish_time) # 논리적 시간과 물리적 준비 완료 시간 중 더 늦은 시간

            # 대안적 해석: 논리적으로 시작 가능한 시간(logical_start_time) 이후에,
            #              추가로 물리적 준비 시간(estimated_prep_time)이 필요함.
            #              단, 이 준비는 current_time부터 시작될 수 있음.
            # 준비 완료 시점 = current_time + estimated_prep_time
            # 시작 가능 시점 = max(logical_start_time, current_time + estimated_prep_time) -> 이 방식이 더 적절해 보임
            estimated_physical_ready_time = current_time + estimated_prep_time
            adjusted_start_time = max(logical_start_time, estimated_physical_ready_time)
            # --- 수정 끝 ---

            # 최종 후보 생성 (정보 추가)
            candidate = Candidate(
                subtask=sub,
                is_critical=is_critical,
                status=status,  # 논리적 상태 ("COMPLETED")
                logical_start_time=logical_start_time,
                earliest_start_time=adjusted_start_time,  # 최종 조정된 예상 시작 시간
            )

            # 현재 시간에 즉시 시작 가능한 경우 feasible
            # 주의: estimated_prep_time이 0이고 logical_start_time <= current_time 인 경우
            if adjusted_start_time <= current_time + EPSILON:
                log.debug(
                    f"Subtask '{sub.name}' is feasible now. Adjusted start: {adjusted_start_time:.2f}"
                )
                feasible_candidates.append(candidate)
            else:
                # 즉시 시작은 불가능 (논리적 시간 미도래 또는 준비 시간 필요)
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
        Status: "COMPLETED", "NOT_READY", "FAILED_PREDECESSOR", "CONSTRAINT_ERROR", "CONFLICT"
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
        failure_reason = ""  # 실패 이유 로깅용

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
                # --- 수정: execution_status 확인 강화 ---
                if hasattr(pred_entry.subtask, "execution_status"):
                    pred_status = pred_entry.subtask.execution_status
                    if pred_status is False:  # 명시적으로 False인 경우만 실패
                        any_predecessor_failed = True
                        failure_reason = f"Predecessor '{pred_name}' explicitly FAILED."
                        log.warning(f"'{sub.name}' cannot start: {failure_reason}")
                        break
                    elif pred_status is None:
                        log.warning(
                            f"Predecessor '{pred_name}' completed but 'execution_status' is None. Assuming SUCCESS."
                        )
                        # 성공으로 간주하고 계속 진행
                    # else: pred_status is True (성공)
                else:
                    # 속성 자체가 없는 경우 (레거시 또는 오류), 기본값 True 가정은 유지하되 경고
                    log.warning(
                        f"Predecessor '{pred_name}' completed but lacks 'execution_status' attribute. Assuming SUCCESS."
                    )
                # --- 수정 끝 ---
            except Exception as e_status:
                log.error(
                    f"Error accessing execution_status for '{pred_name}': {e_status}. Treating as FAILED.",
                    exc_info=True,
                )
                any_predecessor_failed = True
                failure_reason = f"Error checking status of predecessor '{pred_name}'."
                break

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
            log.info(
                f"Final status for '{sub.name}': FAILED_PREDECESSOR ({failure_reason})"
            )
            return None, False, "FAILED_PREDECESSOR"

        if not all_predecessors_finished:
            log.debug(f"Final status for '{sub.name}': NOT_READY")
            return None, False, "NOT_READY"

        # --- Check for conflicts if all predecessors completed successfully ---
        final_start_time = 0.0
        is_final_critical = False
        conflict_detected = False  # 충돌 상태 플래그

        if critical_times:
            # If there are critical constraints, find the earliest and latest required start times
            earliest_critical_time = min(critical_times)
            latest_critical_time = max(critical_times)

            # --- 수정: 충돌 검사 및 로깅 강화 ---
            if (
                abs(earliest_critical_time - latest_critical_time) > EPSILON
            ):  # 수정된 허용 오차 사용
                log.error(
                    f"CRITICAL CONSTRAINT CONFLICT for '{sub.name}': Multiple distinct critical start times required: {sorted(critical_times)}. Check constraint logic."
                )
                # Policy: 충돌 시 실행 불가 처리 (또는 가장 늦은 시간 사용 등 정책 결정 필요)
                # 현재: 실행 불가 (CONFLICT)
                conflict_detected = True
            else:
                # All critical times agree (within tolerance)
                final_start_time = earliest_critical_time  # 또는 평균값 사용 등

            is_final_critical = True

            # Check non-critical conflict only if critical times were consistent
            if (
                not conflict_detected
                and final_start_time < non_critical_earliest_start - EPSILON
            ):
                log.error(
                    f"CRITICAL/NON-CRITICAL CONFLICT for '{sub.name}': Required critical start {final_start_time:.2f} "
                    f"is EARLIER than latest non-critical requirement {non_critical_earliest_start:.2f}. Check constraint logic."
                )
                # Policy: 충돌 시 실행 불가 처리
                conflict_detected = True

            if conflict_detected:
                log.info(f"Final status for '{sub.name}': CONFLICT")
                return None, True, "CONFLICT"  # is_critical=True 유지
            # --- 수정 끝 ---
        else:
            # No critical constraints
            final_start_time = non_critical_earliest_start
            is_final_critical = False

        # 모든 검사 통과
        log.debug(
            f"Final status for '{sub.name}': COMPLETED. Earliest logical start: {final_start_time:.2f} (Critical: {is_final_critical})"
        )
        return (final_start_time, is_final_critical, "COMPLETED")

    def _assign_deadlines(
        self,
        feasible: List[Candidate],
        not_yet: List[Candidate],
        curr_node: SimulationNode,  # 현재 노드 정보는 로깅 외에는 사용되지 않음
    ) -> None:  # 반환 타입 제거 (in-place 수정)
        """
        Assigns deadlines to feasible candidates based on the logical earliest start time
        of the next upcoming critical task found in the not_yet list.
        Modifies the feasible list IN-PLACE.
        """
        # Find the earliest logical start time among upcoming critical tasks
        # --- 수정: 상태 확인 제거 (get_earliest_start_time에서 이미 실패/충돌 걸러짐) ---
        crit_candidates = [c for c in not_yet if c.is_critical]

        # --- 수정: logical_start_time 유효성 확인 및 정렬 ---
        valid_crit_candidates = []
        for c in crit_candidates:
            if c.logical_start_time is not None and c.logical_start_time >= 0:
                valid_crit_candidates.append(c)
            else:
                log.warning(
                    f"Critical candidate '{c.subtask.name}' in not_yet list has invalid logical_start_time ({c.logical_start_time}). Excluding from deadline calculation."
                )

        if not valid_crit_candidates:
            # No upcoming valid critical tasks
            deadline_time = float("inf")
            deadline_reason_subtask_name = "None"
            log.debug(
                "No upcoming valid critical tasks found in not_yet list. Assigning infinite deadline."
            )
        else:
            # Sort by logical start time to find the *next* critical deadline
            valid_crit_candidates.sort(key=lambda x: x.logical_start_time)
            next_crit = valid_crit_candidates[0]
            # The deadline is the logical start time of the next critical task
            deadline_time = next_crit.logical_start_time
            deadline_reason_subtask_name = next_crit.subtask.name
            log.debug(
                f"Next critical task '{deadline_reason_subtask_name}' sets deadline at LogicalEST {deadline_time:.2f}"
            )
        # --- 수정 끝 ---

        # Assign the calculated deadline to all feasible candidates (IN-PLACE)
        new_deadline = Deadline(
            due_date=deadline_time, subtask_name=deadline_reason_subtask_name
        )
        for cand in feasible:
            cand.deadline = new_deadline

        # 로깅 추가 (할당된 데드라인 확인)
        if feasible:
            log.debug(
                f"Assigned deadline {new_deadline} to {len(feasible)} feasible candidates."
            )
        # No return needed as feasible list is modified in-place
