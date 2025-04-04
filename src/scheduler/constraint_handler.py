from typing import List, Optional, Tuple

from networkx import DiGraph

from core.dataclass import Candidate, Deadline, SimulationNode, TimeSlot
from core.task import Subtask
from src.utils.common import create_module_logger
from src.utils.config import EPSILON, LOG_ROUND

log = create_module_logger(module_name=__name__, module_log=True)


class ConstraintHandler:

    def get_time_slots(
        self, subtask_name: str, constraints: DiGraph, direction: str
    ) -> TimeSlot:
        edges = (
            list(constraints.out_edges(subtask_name, data=True))
            if direction == "out"
            else list(constraints.in_edges(subtask_name, data=True))
        )

        if not edges:
            return [TimeSlot(0, False, None)]

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
        return time_slots

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
        feasible_candidates = self._assign_deadlines(
            feasible_candidates, not_yet_candidates
        )

        return (feasible_candidates, not_yet_candidates)

    def _assign_deadlines(
        self, feasible: List[Candidate], not_yet: List[Candidate]
    ) -> List[Candidate]:
        # find next critical in not_yet
        crit_candidates = [c for c in not_yet if c.is_critical]
        crit_candidates.sort(key=lambda x: x.earliest_start_time)

        if not crit_candidates:
            # no upcoming critical
            for c in feasible:
                c.deadline = Deadline(float("inf"), None)
            return feasible

        next_crit = crit_candidates[0]
        for c in feasible:
            c.deadline = Deadline(next_crit.earliest_start_time, next_crit.subtask.name)
        return feasible

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
            # 선행이 전혀 없다면 0초부터 시작 가능
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
                log.debug(
                    f"[get_earliest_start_time] Critical Edge: {pred_name} → {sub.name} ({candidate_start})\n"
                )
                critical_times.append(candidate_start)
            else:
                non_critical_earliest = max(non_critical_earliest, candidate_start)
        log.debug(f"[get_earliest_start_time] Critical Times: {critical_times}\n")
        log.debug(
            f"[get_earliest_start_time] Non-critical Earliest: {non_critical_earliest}\n"
        )
        # 이제 critical_starts가 비어있지 않다면,
        # "Critical"이라는 것은 "이 특정 시각에 딱 시작"해야 한다는 정책
        # 여러 critical edge가 서로 다른 시간을 요구하면 conflict
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
