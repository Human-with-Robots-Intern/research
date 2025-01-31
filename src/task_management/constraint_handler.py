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
        subtask_name 기준으로 in/out 방향의 모든 엣지를 확인하여,
        Critical/Non-critical 간 '압축' 로직으로 Interval을 계산한 뒤,
        TimeSlot(NamedTuple: (Interval, IsCritical, LinkedSubtask)) 형태로 반환.

        - Critical 엣지가 여러 개 있으면 모두 같은 Interval이어야 함
        (서로 다르면 충돌로 간주 -> TimeSlot(0, False, None) 반환)
        - Non-critical 엣지는 Interval 중 최댓값을 취함
        - Critical과 Non-critical이 동시에 존재한다면,
        Critical interval >= Non-critical 최댓값 이어야 함
        (그렇지 않으면 충돌로 간주 -> TimeSlot(0, False, None) 반환)
        - 반환 시, LinkedSubtask(세 번째 필드)는
        실제 어느 엣지를 기준으로 할지 애매할 수 있으므로
        여기서는 (critical이 있으면 그 첫 번째, non-critical이면 최댓값 가진 것)만 예시로 취함.
        - 엣지가 전혀 없으면 TimeSlot(0, False, None)을 반환.
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

        critical_intervals = []
        non_critical_intervals = []

        # 1) Critical / Non-critical 엣지를 구분하여 수집
        for u, v, data in edges:
            interval = data["info"]["Interval"]
            is_crit = data["info"]["IsCritical"]
            # direction = 'out' 이면 (subtask_name -> v), 'in'이면 (u -> subtask_name)이므로
            linked_subtask = v if direction == "out" else u

            if is_crit:
                critical_intervals.append((interval, linked_subtask))
            else:
                non_critical_intervals.append((interval, linked_subtask))

        # 2) Critical 엣지 처리
        if critical_intervals:
            # 여러 Critical Interval이 있으면 모두 같아야 함
            distinct_crit_vals = {t[0] for t in critical_intervals}
            if len(distinct_crit_vals) > 1:
                # 서로 다른 값이 존재 -> 충돌
                log.debug(
                    f"[get_temporal_constraints] Multiple distinct critical intervals found "
                    f"for subtask {subtask_name}: {distinct_crit_vals}. "
                    "Returning TimeSlot(0, False, None)."
                )
                return TimeSlot(0, False, None)

            # critical_intervals는 모두 같은 interval이므로 아무거나 취함
            crit_interval, crit_linked = critical_intervals[0]

            # 3) Non-critical 엣지도 있으면 최댓값 추출
            if non_critical_intervals:
                max_noncrit_interval, max_noncrit_linked = max(
                    non_critical_intervals, key=lambda x: x[0]
                )
                # Critical interval >= Non-critical의 최댓값이어야 모순 없음
                if crit_interval < max_noncrit_interval:
                    log.debug(
                        f"[get_temporal_constraints] Critical interval {crit_interval} < "
                        f"max non-critical {max_noncrit_interval}, conflict. "
                        "Returning TimeSlot(0, False, None)."
                    )
                    return TimeSlot(0, False, None)
                # 정상이라면, critical interval 그대로 사용
                return TimeSlot(crit_interval, True, crit_linked)
            else:
                # Non-critical 엣지가 없으면, critical interval 그대로 반환
                return TimeSlot(crit_interval, True, crit_linked)

        # 4) Critical 엣지가 없는 경우 -> Non-critical 최댓값만 있으면 됨
        else:
            # Non-critical만 있으므로, Interval 중 최댓값을 취한다
            max_interval, max_linked = max(non_critical_intervals, key=lambda x: x[0])
            return TimeSlot(max_interval, False, max_linked)

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

            return (only_crit_time, True)
        else:
            # critical 없음 -> noncrit_earliest 이후면 언제든
            return (non_critical_earliest, False)
