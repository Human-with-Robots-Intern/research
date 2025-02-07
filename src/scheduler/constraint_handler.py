from typing import List, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from core.task import Subtask
from scheduler.cost_manager import NavigationManager
from scheduler.dataclass import Candidate, SchedulerState, SimulationNode, TimeSlot
from utils import create_module_logger
from utils.constants import LOG_ROUND

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
        """
        주어진 서브태스크의 in/out 방향 엣지들을 확인하여,
        Critical/Non-critical 간 압축 로직으로 Interval을 계산한 뒤,
        TimeSlot(NamedTuple: (Interval, IsCritical, LinkedSubtask)) 형태로 반환.

        조건:
          - Critical 엣지가 여러 개면 모두 같은 Interval이어야 함 (다르면 충돌로 간주)
          - Non-critical 엣지는 Interval 중 최댓값을 사용
          - Critical과 Non-critical이 동시에 존재하면 Critical interval >= Non-critical 최댓값이어야 함
          - 엣지가 없으면 TimeSlot(0, False, None)을 반환.
        """

        edges = (
            list(constraints.out_edges(subtask_name, data=True))
            if direction == "out"
            else list(constraints.in_edges(subtask_name, data=True))
        )

        # 주어진 subtask에 제약이 없는 경우
        if not edges:
            return TimeSlot(0, False, None)

        critical_intervals = []
        non_critical_intervals = []

        # Critical / Non-critical 엣지 구분
        for u, v, data in edges:
            interval = data["info"]["Interval"]
            is_crit = data["info"]["IsCritical"]
            linked_subtask = v if direction == "out" else u

            if is_crit:
                critical_intervals.append((interval, linked_subtask))
            else:
                non_critical_intervals.append((interval, linked_subtask))

        # ? Critical과 Non-critical이 함께 있을 때, Critical이 Non-critical보다 늦어야 하는 경우만 커버되는거 아님?
        # ? 예외 케이스가 있잖아. Non-critical이 더 늦고, Critical이 더 빠르게 시작해야 하는 경우는 커버가 되긴 하니?
        # ? 근데, 무조건 Critical이 중요하니까 Critical을 반드시 따라야 한다고 생각 해야 할 것 같다. 왜냐면 Critical은 실패 가능성이 높은 작업이니까.
        # Critical 엣지 처리
        if critical_intervals:
            distinct_crit_vals = {t[0] for t in critical_intervals}
            # Critical 엣지가 여러 개면 모두 같은 Interval이어야 함
            if len(distinct_crit_vals) > 1:
                return TimeSlot(0, False, None)

            crit_interval, crit_linked = critical_intervals[0]

            if non_critical_intervals:
                max_non_crit_interval, _ = max(
                    non_critical_intervals, key=lambda x: x[0]
                )
                if crit_interval < max_non_crit_interval:
                    return TimeSlot(0, False, None)
            return TimeSlot(crit_interval, True, crit_linked)
        else:
            max_interval, max_linked = max(non_critical_intervals, key=lambda x: x[0])
            return TimeSlot(max_interval, False, max_linked)

    def get_actual_duration(
        self, curr_state: SchedulerState, subtask_name: str
    ) -> TimeSlot:
        time_slot = self.get_time_slots(subtask_name, curr_state.constraints, "in")
        for ce in curr_state.completed_subtasks:
            if ce.subtask.name == time_slot.related_subtask_name:
                actual_duration = curr_state.current_time - ce.end_time
                break
        return actual_duration

    def find_parallel_window(self, current_node: SimulationNode) -> float:
        """
        (예시) 이미 '진행 중'인 Uncontrollable 서브태스크가 있으면,
        그 작업의 남은 시간을 병렬 구간으로 보고 반환한다.
        - 여기서는 단순히 'type이 Uncontrollable이고 end_time > 현재'인 서브태스크 중 최댓값을 찾는 예시
        """

        now = current_node.state.current_time
        max_remaining = 0.0

        # completed_subtasks는 '이미 끝난' 작업이라는 점에서 'in-progress' 확인이 애매하지만,
        # 만약 "끝나지 않은" subtask를 별도 관리한다면 여기서 참조.

        for ce in current_node.state.completed_subtasks:
            time_slots = self.get_time_slots(
                ce.subtask.name, current_node.state.constraints, "out"
            )
            parallel_window_end_time_candidate = ce.end_time + time_slots.interval
            if parallel_window_end_time_candidate > now:
                # 아직 종료 안 되었다고 가정
                remaining = ce.end_time - now
                if remaining > max_remaining:
                    max_remaining = remaining

        return max_remaining

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
        log.debug("get_feasible_subtasks: 시작")
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
                if abs(current_time - earliest_start_time) < 1e-9:
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
                if current_time >= earliest_start_time - 1e-9:
                    feasible_candidates.append(
                        Candidate(sub, False, earliest_start_time)
                    )
                else:
                    not_yet_candidates.append(
                        Candidate(sub, False, earliest_start_time)
                    )
        not_yet_candidates = sorted(
            filter(lambda x: x.is_critical, not_yet_candidates),
            key=lambda x: x.earliest_start_time,
        )
        for candidate in feasible_candidates:
            candidate.deadline = (
                not_yet_candidates[0].earliest_start_time
                if not_yet_candidates
                else float("inf")
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
            unique_critical = set(critical_times)
            if len(unique_critical) != 1:
                log.error(
                    f"Conflict: multiple distinct critical times for '{sub.name}': {unique_critical}\n"
                )
                raise ValueError("Multiple distinct critical times found, conflict.")
            only_crit_time = unique_critical.pop()
            return (only_crit_time, True)
        else:
            return (non_critical_earliest, False)
