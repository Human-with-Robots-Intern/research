from typing import List, Optional, Tuple

import networkx as nx

from core.task import Subtask
from scheduler.cost_manager import NavigationManager
from scheduler.dataclass import Candidate, SimulationNode, TemporalConstraint
from utils import create_module_logger

log = create_module_logger(module_name=__name__)


class ConstraintHandler:
    def __init__(self):
        """
        constraints: nx.DiGraph
          - 각 edge(u->v)에 "info": {"Interval": float, "IsCritical": bool}가 존재
        """
        pass

    def get_temporal_constraints(
        self, subtask_name: str, constraints: nx.DiGraph, direction: str
    ) -> TemporalConstraint:
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
        log.debug(
            f"get_temporal_constraints: subtask '{subtask_name}', direction '{direction}'"
        )
        edges = (
            list(constraints.out_edges(subtask_name, data=True))
            if direction == "out"
            else list(constraints.in_edges(subtask_name, data=True))
        )

        if not edges:
            return TemporalConstraint(0, False, None)

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

        # Critical 엣지 처리
        if critical_intervals:
            distinct_crit_vals = {t[0] for t in critical_intervals}
            if len(distinct_crit_vals) > 1:

                return TemporalConstraint(0, False, None)

            crit_interval, crit_linked = critical_intervals[0]

            if non_critical_intervals:
                max_noncrit_interval, _ = max(
                    non_critical_intervals, key=lambda x: x[0]
                )
                if crit_interval < max_noncrit_interval:

                    return TemporalConstraint(0, False, None)
            return TemporalConstraint(crit_interval, True, crit_linked)
        else:
            max_interval, max_linked = max(non_critical_intervals, key=lambda x: x[0])
            return TemporalConstraint(max_interval, False, max_linked)

    def get_feasible_subtasks(
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
        feasible_subtasks: List["Subtask"] = []
        not_yet_list: List[Tuple["Subtask", float, bool]] = []

        current_time = curr_node.state.current_time
        candidates = curr_node.state.remaining_subtasks
        constraints = curr_node.state.constraints

        for sub in candidates:
            earliest_start, is_exact = self._calc_earliest_start(
                curr_node, sub, constraints
            )
            if earliest_start is None:
                log.debug(f"Subtask '{sub.name}' 실행 불가: 선행 미완료\n")
                continue

            if is_exact:
                if abs(current_time - earliest_start) < 1e-9:
                    feasible_subtasks.append(Candidate(sub, earliest_start, True))
                elif current_time < earliest_start:
                    not_yet_list.append(Candidate(sub, earliest_start, True))
                else:
                    log.error(
                        f"Subtask '{sub.name}'의 시간 창을 놓쳤음 (현재 시간: {current_time})\n"
                    )
                    return [], []
            else:
                if current_time >= earliest_start - 1e-9:
                    feasible_subtasks.append(Candidate(sub, earliest_start, False))
                else:
                    not_yet_list.append(Candidate(sub, earliest_start, False))

        return feasible_subtasks, not_yet_list

    def _calc_earliest_start(
        self, curr_node: SimulationNode, sub: "Subtask", constraints: nx.DiGraph
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

        in_edges = list(constraints.in_edges(sub.name, data=True))

        if not in_edges:
            return (0.0, False)

        critical_times = []
        non_critical_earliest = 0.0

        for pred_name, _, edge_data in in_edges:
            info = edge_data["info"]
            interval = info["Interval"]
            is_crit = info["IsCritical"]

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

        if critical_times:
            unique_crit = set(critical_times)
            if len(unique_crit) != 1:
                log.error(
                    f"Conflict: multiple distinct critical times for '{sub.name}': {unique_crit}\n"
                )
                raise ValueError("Multiple distinct critical times found, conflict.")
            only_crit_time = unique_crit.pop()
            return (only_crit_time, True)
        else:
            return (non_critical_earliest, False)
