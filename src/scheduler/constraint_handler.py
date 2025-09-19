from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from src.models.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulingDue,
    SimulationNode,
    TimeSlot,
)
from src.models.task import Subtask
from src.scheduler.action_handler import ActionHandler
from src.utils.common import create_module_logger
from src.utils.config import EPSILON

log = create_module_logger(__name__, True, logging.DEBUG)


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
        """In / Out Edge의 Wrapper. TimeSlot 객체를 반환

        Args:
            subtask_name (str): 타임슬롯을 조회할 태스크 이름
            constraints (DiGraph): 제약 그래프
            direction (str): "in" 또는 "out"
        Returns:
            List[TimeSlot]: TimeSlot 객체를 반환
        """
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
            # 1. 시간 제약 상 시작 가능한 시간 조건 확인
            logical_interaction_start_time, is_critical, status = (
                self.get_logical_interaction_start_time(curr_node, sub)
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
                # 여기서는 Candidate 객체만 추가하고, 추후 scheduling_due 할당 등에서 활용 가능
                # NOT_READY 상태 Subtask는 최소 시작 시간이 None임
                not_yet_candidates.append(
                    Candidate(
                        subtask=sub,
                        is_critical=is_critical,
                        logical_interaction_start_time=logical_interaction_start_time,
                    )
                )  # status 추가
                continue

            # 2. 물리적 제약 조건 확인 (네비게이션 시간 등)
            first_nav_action = (
                sub.execution.primitive_actions[0]
                if sub.execution
                and sub.execution.primitive_actions[0].startswith("NAVIGATE_TO")
                else None
            )

            first_nav_duration = 0.0
            if first_nav_action:
                log.debug(
                    f"  Estimating prep time for '{sub.name}' using first action: '{first_nav_action}' via ActionHandler"
                )
                # curr_node의 현재 시간, 위치 등을 기준으로 첫 액션 실행 시간 추정
                navigation_info: Optional[ActionResult] = (
                    self.action_handler.get_actions_info(curr_node, [first_nav_action])
                )
                # get_actions_info는 빈 actions 목록이 아니면 항상 ActionResult를 반환하므로 prep_info는 None이 아님.
                first_nav_duration = navigation_info.action_duration
                log.debug(
                    f"    Estimated prep duration for first action: {first_nav_duration:.2f}"
                )
            else:
                log.debug(
                    f"  No primitive actions for subtask '{sub.name}'. Prep duration is 0."
                )

            # 3. 최종 시작 가능 시간 계산 및 Feasibility 판단
            #    logical_start_time: 선행 작업 완료 + 제약 간격 이후의 시간 (상호작용 시작 가능 논리적 시간)
            #    current_time + estimated_prep_duration: 현재부터 첫 액션 수행 후의 시간 (물리적 준비 완료 시간)

            # 실제 상호작용이 시작될 수 있는 가장 이른 시간
            # 가능한 상호작용 시간 보다, Logical Interaction Start Time이 더 늦는 경우 -> Logical Interaction Start Time으로 결정 -> 논리적 제약 충족 필요 -> not yet
            # Logical Interaction Start Time보다, 가능한 상호작용 시간이 같거나 늦는 경우 -> 가능한 상호작용 시간으로 결정 -> feasible candidates
            actual_interaction_start_time = max(
                logical_interaction_start_time, current_time + first_nav_duration
            )

            candidate = Candidate(
                subtask=sub,
                is_critical=is_critical,
                logical_interaction_start_time=logical_interaction_start_time,
                actual_interaction_start_time=actual_interaction_start_time,
                estimated_first_nav_duration=first_nav_duration,
            )

            # 현재 시간에 "상호작용을 시작"할 수 있는 경우 feasible
            # 즉, effective_interaction_start_time이 현재 시간과 거의 같아야 함.
            if (
                actual_interaction_start_time
                <= current_time + first_nav_duration + EPSILON
            ):
                log.debug(
                    f"Subtask '{sub.name}' is feasible now (interaction can start at {actual_interaction_start_time:.2f})."
                )
                feasible_candidates.append(candidate)
            else:
                # 즉시 상호작용 시작은 불가능 (논리적 시간 미도래 또는 준비 시간 필요)
                log.debug(
                    f"Subtask '{sub.name}' is not yet feasible for immediate interaction "
                    f"(interaction can start at {actual_interaction_start_time:.2f}). Adding to not_yet_candidates."
                )
                not_yet_candidates.append(candidate)

        self._assign_scheduling_due(feasible_candidates, not_yet_candidates, curr_node)

        return feasible_candidates, not_yet_candidates

    def get_logical_interaction_start_time(
        self, curr_node: SimulationNode, sub: Subtask
    ) -> tuple:
        """
        태스크 'sub'의 논리적 최소 시작 시간을 계산합니다.(시간 제약 상에서 최소 시작 시간)
        선행 태스크 완료 시간과 제약 시간 간격을 기반으로 합니다.
        선행 작업이 아직 완료되지 않은 경우, feasible_candidates/not_yet_candidates에서 예상 완료 시점을 추정하여 반환.
        반환: (logical_interaction_start_time(절대 시간계), is_critical, status)
        Status: "COMPLETED", "NOT_READY", "FAILED_PREDECESSOR", "CONSTRAINT_ERROR", "CONFLICT"
        """

        curr_constraints = curr_node.state.constraints
        # CONSTRAINT_ERROR: 제약 그래프가 없거나 사이클을 갖는 경우
        if not curr_constraints or not isinstance(curr_constraints, nx.DiGraph):
            log.error(
                f"Invalid constraint graph provided for state at time {curr_node.state.current_time:.2f}. Cannot process subtask '{sub.name}'."
            )
            return None, False, "CONSTRAINT_ERROR"
        if not nx.is_directed_acyclic_graph(curr_constraints):
            log.error(
                f"CONSTRAINT ERROR: Cycle detected in the constraint graph for state at time {curr_node.state.current_time:.2f}! "
                f"Cannot reliably calculate earliest start time for '{sub.name}'. Check constraint update logic."
            )
            return None, False, "CONSTRAINT_ERROR"

        # COMPLETED: 태스크가 아직 제약 그래프에 없는 경우 -> 동적으로 생성된 것으로 간주
        if sub.name not in curr_constraints:
            log.debug(
                f"Subtask '{sub.name}' not found in constraint graph. Assuming ready at time 0."
            )
            return 0.0, False, "COMPLETED"

        completed_subtasks_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_entries
        }
        # COMPLETED : Subtask에 시간 제약이 부재한 경우에는 언제든지 수행되도 되는 것
        in_edges = list(curr_constraints.in_edges(sub.name, data=True))
        if not in_edges:
            log.debug(f"Subtask '{sub.name}' has no predecessors. Ready at time 0.")
            return 0.0, False, "COMPLETED"

        # 선행 작업이 있는 Task에 대하여
        critical_times = []
        non_critical_earliest_start = 0.0
        all_predecessors_finished = True
        any_predecessor_failed = False
        failure_reason = ""

        for pred_name, _, edge_data in in_edges:
            info = edge_data.get("info", {})
            interval = float(info.get("Interval", 0.0))
            is_crit = info.get("IsCritical", False)

            pred_entry: Optional[CompletedEntry] = completed_subtasks_map.get(
                pred_name, None
            )

            if pred_entry is None:
                all_predecessors_finished = False
                continue

            if hasattr(pred_entry, "execution_status"):
                pred_status = pred_entry.execution_status
                if pred_status is False:
                    any_predecessor_failed = True
                    failure_reason = (
                        f"Predecessor '{pred_name}' sched execution status FAILED."
                    )
                    log.warning(f"'{sub.name}' cannot start: {failure_reason}")
                    break
            pred_end_time = pred_entry.schedule_end_time
            curr_logical_interaction_start_time = pred_end_time + interval

            # Critical / Non-critical 분리
            if is_crit:
                critical_times.append(curr_logical_interaction_start_time)
            else:
                non_critical_earliest_start = max(
                    non_critical_earliest_start, curr_logical_interaction_start_time
                )
        # 선행 작업 성공 / 실패 여부 확인
        if any_predecessor_failed:
            log.error(
                f"Final status for '{sub.name}': FAILED_PREDECESSOR ({failure_reason})"
            )
            return None, False, "FAILED_PREDECESSOR"

        if all_predecessors_finished:
            final_start_time = 0.0
            is_final_critical = False
            tc_conflict_detected = False

            if critical_times:
                # 하나의 Subtask u,v pair 간 복수의 Critical 제약이 존재하는 경우,
                earliest_critical_time = min(critical_times)
                latest_critical_time = max(critical_times)
                if abs(earliest_critical_time - latest_critical_time) > EPSILON:
                    # Must satisfy all critical intervals: pick the latest (most restrictive) time
                    log.warning(
                        f"CRITICAL CONSTRAINT MULTI-START for '{sub.name}': candidates={sorted(critical_times)} -> resolved={latest_critical_time:.2f}"
                    )
                    final_start_time = latest_critical_time
                else:
                    final_start_time = earliest_critical_time

                is_final_critical = True
                if EPSILON < non_critical_earliest_start - final_start_time:
                    # Prefer the stricter (later) non-critical requirement without failing scheduling
                    log.warning(
                        f"CRITICAL/NON-CRITICAL TENSION for '{sub.name}': crit_start {final_start_time:.2f} earlier than non-critical {non_critical_earliest_start:.2f}. Using non-critical."
                    )
                    final_start_time = non_critical_earliest_start
            else:
                final_start_time = non_critical_earliest_start
                is_final_critical = False

            log.debug(
                f"Final status for '{sub.name}': COMPLETED. Earliest logical start: {final_start_time:.2f} (Critical: {is_final_critical})"
            )
            return (final_start_time, is_final_critical, "COMPLETED")

        log.debug(f"Final status for '{sub.name}': NOT_READY (no predecessor info)")
        return None, False, "NOT_READY"

    def _assign_scheduling_due(
        self,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
        curr_node: SimulationNode,
    ) -> None:
        """
        Assigns scheduling due to feasible candidates based on the logical earliest start time
        of the next upcoming critical task found in the not_yet list.
        Modifies the feasible list IN-PLACE.
        """
        # Find the earliest logical start time among upcoming critical tasks
        crit_candidates = [c for c in not_yet_candidates if c.is_critical]

        valid_crit_candidates = []
        for critical_candidate in crit_candidates:
            # logical_interaction_start_time이 유효한 경우는 선행 작업이 완료된 경우 또는 in edge 시간 제약이 없는 경우
            # 현재 시각 또는 미래 시각에 도래할 not yet critical candidate가 feasible candidate의 scheduling due를 결정
            if (
                critical_candidate.logical_interaction_start_time is not None
                and critical_candidate.logical_interaction_start_time
                >= curr_node.state.current_time
            ):
                valid_crit_candidates.append(critical_candidate)
            else:
                log.warning(
                    f"Critical candidate '{critical_candidate.subtask.name}' in not_yet list has invalid logical_start_time ({critical_candidate.logical_interaction_start_time}). Excluding from scheduling_due calculation."
                )

        if not valid_crit_candidates:
            # No upcoming valid critical tasks
            scheduling_due = float("inf")
            due_related_sub_name = None
            log.debug(
                f"현재 not yet list에 critical subtask가 존재하지 않아, scheduling due가 inf로 처리됩니다."
            )
        else:
            # Sort by logical start time to find the *next* critical scheduling_due
            valid_crit_candidates.sort(key=lambda x: x.logical_interaction_start_time)
            next_crit = valid_crit_candidates[0]
            # The scheduling_due is the logical start time of the next critical task
            scheduling_due = next_crit.logical_interaction_start_time
            due_related_sub_name = next_crit.subtask.name
            log.debug(
                f"Next critical task '{due_related_sub_name}' sets scheduling_due at LogicalEST {scheduling_due:.2f}"
            )

        # Assign the calculated scheduling_due to all feasible candidates (IN-PLACE)
        new_scheduling_due = SchedulingDue(
            due_date=scheduling_due, due_related_sub_name=due_related_sub_name
        )
        for feasible_candidate in feasible_candidates:
            feasible_candidate.scheduling_due = new_scheduling_due

        if feasible_candidates:
            log.debug(
                f"Assigned scheduling_due {new_scheduling_due} to {len(feasible_candidates)} feasible candidates."
            )
        # No return needed as feasible list is modified in-place
