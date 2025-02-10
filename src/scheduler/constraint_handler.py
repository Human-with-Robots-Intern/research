from typing import List, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from core.task import Subtask
from scheduler.cost_manager import NavigationManager
from scheduler.dataclass import (
    Candidate,
    Deadline,
    SchedulerState,
    SimulationNode,
    TimeSlot,
)
from utils import create_module_logger
from utils.constants import EPSILON, LOG_ROUND

log = create_module_logger(module_name=__name__, is_file_handler=True)


class ConstraintHandler:
    def __init__(self):
        """
        constraints: nx.DiGraph
          - 각 edge(u->v)에 "info": {"Interval": float, "IsCritical": bool}가 존재
        """
        pass

    def get_time_slots(
        self, subtask_name: str, constraints: DiGraph, direction: str
    ) -> TimeSlot:
        edges = (
            list(constraints.out_edges(subtask_name, data=True))
            if direction == "out"
            else list(constraints.in_edges(subtask_name, data=True))
        )

        if not edges:
            return TimeSlot(0, False, None)

        time_slots = []
        linked_subtasks = []  # 여러 개일 수 있음

        # 1) 모든 엣지를 순회하며 Critical/Non-critical 분류
        for u, v, data in edges:
            interval = data["info"]["Interval"]
            is_crit = data["info"]["IsCritical"]
            linked_subtask = v if direction == "out" else u
            linked_subtasks.append(linked_subtask)

            if is_crit:
                time_slots.append(TimeSlot(interval, True, linked_subtask))
            else:
                time_slots.append(TimeSlot(interval, False, linked_subtask))
        return max(time_slots, key=lambda x: x.interval)

    def get_actual_duration(
        self, curr_state: SchedulerState, subtask_name: str
    ) -> float:
        time_slot = self.get_time_slots(subtask_name, curr_state.constraints, "in")
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == time_slot.related_subtask_name:
                actual_duration = curr_state.current_time - ce.end_time
                break
        return actual_duration

    def get_feasible_candidates(
        self,
        curr_node: SimulationNode,
    ) -> Tuple[List[Candidate], List[Candidate]]:
        """
        현재 스케줄 상태(state)에서,
        - 지금 당장 실행 가능한 서브태스크 목록 (feasible)
        - 아직 시간이 안 되어 대기해야 하는 서브태스크 목록 (not_yet)
            --> (Subtask, earliest_start, is_critical)
        """

        feasible_candidates: List["Subtask"] = []
        not_yet_candidates: List[Tuple["Subtask", float, bool]] = []

        current_time = curr_node.state.current_time
        remaining_subtasks = curr_node.state.remaining_subtasks

        for sub in remaining_subtasks:
            earliest_start_time, is_critical = self.get_earliest_start_time(
                curr_node, sub
            )
            if earliest_start_time is None:
                log.debug(f"Subtask '{sub.name}' 실행 불가: 선행 미완료\n")
                continue

            if is_critical:
                if abs(current_time - earliest_start_time) < EPSILON:
                    feasible_candidates.append(
                        Candidate(sub, True, earliest_start_time)
                    )
                elif current_time < earliest_start_time:
                    not_yet_candidates.append(Candidate(sub, True, earliest_start_time))
                else:
                    log.error(
                        f"현재 {round(current_time, LOG_ROUND)}에서 '{sub.name}'의 Critical Timing ({earliest_start_time})을 놓쳤음\n"
                    )
                    return [], []
            else:
                if current_time >= earliest_start_time - EPSILON:
                    feasible_candidates.append(
                        Candidate(sub, False, earliest_start_time)
                    )
                else:
                    not_yet_candidates.append(
                        Candidate(sub, False, earliest_start_time)
                    )
        not_yet_candidates_for_deadline = sorted(
            filter(lambda x: x.is_critical, not_yet_candidates),
            key=lambda x: x.earliest_start_time,
        )
        for candidate in feasible_candidates:
            next_candidate = (
                not_yet_candidates_for_deadline[0]
                if not_yet_candidates_for_deadline
                else None
            )
            candidate.deadline = Deadline(
                next_candidate.earliest_start_time if next_candidate else float("inf"),
                next_candidate.subtask.name if next_candidate else None,
            )

        return (feasible_candidates, not_yet_candidates)

    def get_earliest_start_time(
        self, curr_node: SimulationNode, sub: "Subtask"
    ) -> Tuple[Optional[float], bool]:
        """
        서브태스크 'sub'의 선행 조건을 기반으로 earliest_start을 계산.
          - 선행이 미완료면 (None, False) 반환.
          - Critical 엣지들이 모두 동일한 시간을 가져야 함.
          - Non-critical의 경우, candidate_start의 최댓값 사용.
          - Critical과 Non-critical이 함께 있으면, critical_time >= max(non-critical_times)여야 함.
          - 반환: (earliest_start, is_exact)
            * earliest_start가 None이면 실행 불가능
            * is_exact가 True면 정확히 그 시간에만 실행 가능
        """
        curr_constraints = curr_node.state.constraints

        in_edges = list(curr_constraints.in_edges(sub.name, data=True))

        if not in_edges:
            return (0.0, False)

        critical_times = []
        non_critical_earliest = 0.0

        for pred_name, _, edge_data in in_edges:
            info = edge_data["info"]
            interval = info["Interval"]
            is_crit = info["IsCritical"]

            # 선행 서브태스크의 완료 정보 확인 (Dependency)
            pred_entry = next(
                (
                    ce
                    for ce in curr_node.state.completed_subtasks
                    if ce.subtask.name == pred_name
                ),
                None,
            )
            if not pred_entry:
                # 아직 선행 완료 X -> 실행 불가능
                return (None, False)

            candidate_start = pred_entry.end_time + interval
            if is_crit:
                critical_times.append(candidate_start)
            else:
                non_critical_earliest = max(non_critical_earliest, candidate_start)

        # ? Critical과 Non-critical이 함께 있을 때, Critical이 Non-critical보다 늦어야 하는 경우만 커버되는거 아님?
        # ? 예외 케이스가 있잖아. Non-critical이 더 늦고, Critical이 더 빠르게 시작해야 하는 경우는 커버가 되긴 하니?
        # ? 근데, 무조건 Critical이 중요하니까 Critical을 반드시 따라야 한다고 생각 해야 할 것 같다. 왜냐면 Critical은 실패 가능성이 높은 작업이니까.
        if critical_times:
            first_crit = critical_times[0]
            for ct in critical_times[1:]:
                # Critical Time이 다 같아야 함
                if abs(first_crit - ct) > EPSILON:
                    log.error(
                        f"[get_earliest_start_time] Multiple distinct critical times for '{sub.name}' → conflict.{critical_times}\n",
                    )

                    return (None, False)

            return (first_crit, True)
        else:
            return (non_critical_earliest, False)
