from typing import Any, List, Optional, Tuple

import networkx as nx

from core.task import Subtask
from task_management.navigation_manager import NavigationManager
from utils.dataclass import SchedulerState, SimulationNode, TimeSlot
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class ConstraintHandler:
    def __init__(self, constraints: nx.DiGraph, navigation_manager: NavigationManager):
        """
        constraints: nx.DiGraph
          - 각 edge(u->v)에 "info": {"Interval": float, "IsCritical": bool}가 존재
        """
        self.constraints = constraints
        self.nav_manager = navigation_manager

    def get_temporal_constraints(self, subtask_name: str, direction: str) -> TimeSlot:
        """
        subtask_name 기준으로 in/out 방향의 모든 엣지 중,
        'Interval'이 가장 작은 엣지를 찾아 TimeSlot(NamedTuple)으로 반환.
        엣지가 없다면 TimeSlot(0, False, None)을 반환.
        """
        if direction == "out":
            edges = list(self.constraints.out_edges(subtask_name, data=True))
        elif direction == "in":
            edges = list(self.constraints.in_edges(subtask_name, data=True))
        else:
            raise ValueError("direction must be either 'in' or 'out'.")

        if not edges:
            log.debug(
                f"No {direction} edges found for subtask {subtask_name}. "
                "Returning default TimeSlot(0, False, None)."
            )
            return TimeSlot(0, False, None)

        # interval이 가장 작은 엣지를 선택
        min_edge = min(
            (
                (
                    data["info"]["Interval"],
                    data["info"]["IsCritical"],
                    (
                        v if direction == "out" else u
                    ),  # out이면 (subtask -> v), in이면 (u -> subtask)
                )
                for u, v, data in edges
            ),
            key=lambda x: x[0],  # interval 기준 최소값
        )
        return TimeSlot(*min_edge)

    from typing import Any, List, Optional, Tuple


import networkx as nx

from core.task import Subtask
from task_management.navigation_manager import NavigationManager
from utils.dataclass import SchedulerState, SimulationNode, TimeSlot
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class ConstraintHandler:
    def __init__(self, constraints: nx.DiGraph, navigation_manager: NavigationManager):
        """
        constraints: nx.DiGraph
          - 각 edge(u->v)에 "info": {"Interval": float, "IsCritical": bool}가 존재
        """
        self.constraints = constraints
        self.nav_manager = navigation_manager

    def get_temporal_constraints(self, subtask_name: str, direction: str) -> TimeSlot:
        """
        subtask_name 기준으로 in/out 방향의 모든 엣지 중,
        'Interval'이 가장 작은 엣지를 찾아 TimeSlot(NamedTuple)으로 반환.
        엣지가 없다면 TimeSlot(0, False, None)을 반환.
        """
        if direction == "out":
            edges = list(self.constraints.out_edges(subtask_name, data=True))
        elif direction == "in":
            edges = list(self.constraints.in_edges(subtask_name, data=True))
        else:
            raise ValueError("direction must be either 'in' or 'out'.")

        if not edges:
            log.debug(
                f"No {direction} edges found for subtask {subtask_name}. "
                "Returning default TimeSlot(0, False, None)."
            )
            return TimeSlot(0, False, None)

        # interval이 가장 작은 엣지를 선택
        min_edge = min(
            (
                (
                    data["info"]["Interval"],
                    data["info"]["IsCritical"],
                    (
                        v if direction == "out" else u
                    ),  # out이면 (subtask -> v), in이면 (u -> subtask)
                )
                for u, v, data in edges
            ),
            key=lambda x: x[0],  # interval 기준 최소값
        )
        return TimeSlot(*min_edge)

    def get_feasible_subtasks(
        self,
        node: SimulationNode,
    ) -> Tuple[List["Subtask"], List[Tuple["Subtask", float, bool]]]:
        """
        현재 스케줄 상태(state)에서,
        아직 실행 안 된 서브태스크들을 돌면서
        - 지금 당장(current_time) 실행 가능한 서브태스크들의 목록 (feasible)
        - 아직 시간이 안 되어 대기해야 하는 서브태스크들 목록 (not_yet)
          --> (Subtask, earliest_start, is_critical)

        return (feasible_subtasks, not_yet_list)
        """
        feasible_subtasks: List["Subtask"] = []
        not_yet_list: List[Tuple["Subtask", float, bool]] = []

        current_time = node.state.current_time
        candidates = node.state.remaining_subtasks

        for sub in candidates:
            earliest_start, is_exact = self._calc_earliest_start(node, sub)
            if earliest_start is None:
                # 전혀 실행 불가능(=선행 미완료 or Critical 충돌 등)
                continue

            if is_exact:
                nav_time, _ = self.nav_manager.compute_navigation_time(node, sub)
                earliest_start -= nav_time
                # Critical => current_time == earliest_start일 때만 지금 실행 가능
                if abs(current_time - earliest_start) < 1e-9:
                    feasible_subtasks.append(sub)
                elif current_time < earliest_start:
                    # 대기 필요
                    not_yet_list.append((sub, earliest_start, True))
                else:
                    # 이미 시간을 넘겼다면 실행 불가
                    pass
            else:
                # Non-critical => current_time >= earliest_start이면 바로 실행 가능
                if current_time >= earliest_start - 1e-9:
                    feasible_subtasks.append(sub)
                else:
                    # 아직 시간을 만족 못함
                    not_yet_list.append((sub, earliest_start, False))

        return feasible_subtasks, not_yet_list

    def _calc_earliest_start(
        self, node: SimulationNode, sub: "Subtask"
    ) -> Tuple[Optional[float], bool]:
        """
        sub(후행 서브태스크)에 대한
         - 모든 선행(in-edge) 확인 -> interval, is_critical
         - 선행이 아직 완료 안 됐으면 (None, False)
         - Critical 여러 개면 모두 같은 시점이어야 -> 하나로 확정, 다르면 불가
         - Non-critical은 '선행종료+interval' 중 가장 큰 값
         - Critical과 Non-critical이 동시에 있으면
           critical_time >= max(non_critical_times) 이어야
         - 최종 (earliest_start, is_exact)을 반환:
           -> earliest_start가 None이면 '전혀 불가능'
           -> is_exact=True이면 '정확히 earliest_start'에만 가능
              False면 'earliest_start 이후' 언제든 가능
        """

        in_edges = list(self.constraints.in_edges(sub.name, data=True))
        if not in_edges:
            # 선행이 전혀 없는 경우 -> 아무때나 가능
            return (0.0, False)

        critical_times = []
        non_critical_earliest = 0.0

        for pred_name, _, edge_data in in_edges:
            info = edge_data["info"]
            interval = info["Interval"]
            is_crit = info["IsCritical"]

            # 선행 Subtask 완료 기록 탐색
            pred_entry = next(
                (
                    ce
                    for ce in node.state.completed_subtasks
                    if ce.subtask.name == pred_name
                ),
                None,
            )
            if not pred_entry:
                # 아직 선행이 완료 안 됨 => 현재로선 실행 불가
                return (None, False)

            candidate_start = pred_entry.end_time + interval
            if is_crit:
                critical_times.append(candidate_start)
            else:
                # Non-critical이면 최대값을 기록
                if candidate_start > non_critical_earliest:
                    non_critical_earliest = candidate_start

        # Critical 여러 개 -> 모두 같은 시점이어야
        if len(critical_times) > 1:
            # unique set으로 비교
            unique_crit = set(critical_times)
            if len(unique_crit) != 1:
                # 서로 다른 시점을 요구 = 모순
                return (None, False)
            only_crit_time = next(iter(unique_crit))  # 그 하나
        elif len(critical_times) == 1:
            only_crit_time = critical_times[0]
        else:
            only_crit_time = None

        # 종합
        if only_crit_time is not None:
            # critical
            # 만약 critical 시점이 noncrit_earliest보다 작으면 모순
            # 왜냐면, noncrit_earliest 이후에는 언제든 가능해야 하는데
            if only_crit_time < non_critical_earliest:
                return (None, False)
            return (only_crit_time, True)
        else:
            # critical 없음 -> noncrit_earliest 이후면 언제든
            return (non_critical_earliest, False)
