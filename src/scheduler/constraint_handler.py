from typing import List, Optional, Tuple

import networkx as nx

from core.task import Subtask
from scheduler.cost_manager import NavigationManager
from scheduler.dataclass import SimulationNode, TimeSlot
from utils import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=True)


class ConstraintHandler:
    def __init__(self, navigation_manager: NavigationManager):
        """
        constraints: nx.DiGraph
          - 각 edge(u->v)에 "info": {"Interval": float, "IsCritical": bool}가 존재
        """
        self.nav_manager = navigation_manager

    def get_temporal_constraints(
        self, subtask_name: str, constraints: nx.DiGraph, direction: str
    ) -> TimeSlot:
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
        log.debug(
            f"Entering get_temporal_constraints for subtask '{subtask_name}' with direction '{direction}'."
        )

        if direction == "out":
            edges = list(constraints.out_edges(subtask_name, data=True))
        else:  # direction == "in"
            edges = list(constraints.in_edges(subtask_name, data=True))

        log.debug(f"Found {len(edges)} {direction} edges for subtask '{subtask_name}'.")

        if not edges:
            log.debug(
                f"No {direction} edges found for {subtask_name}, returning default TimeSlot(0, False, None)."
            )
            return TimeSlot(0, False, None)

        critical_intervals = []
        non_critical_intervals = []

        # 1) Critical / Non-critical 엣지를 구분하여 수집
        for u, v, data in edges:
            interval = data["info"]["Interval"]
            is_crit = data["info"]["IsCritical"]
            # direction = 'out'이면 (subtask_name -> v), 'in'이면 (u -> subtask_name)
            linked_subtask = v if direction == "out" else u
            log.debug(
                f"Processing edge ({u} -> {v}) with interval {interval} and isCritical={is_crit}. Linked subtask: {linked_subtask}"
            )

            if is_crit:
                critical_intervals.append((interval, linked_subtask))
            else:
                non_critical_intervals.append((interval, linked_subtask))

        log.debug(
            f"Collected {len(critical_intervals)} critical and {len(non_critical_intervals)} non-critical intervals."
        )

        # 2) Critical 엣지 처리
        if critical_intervals:
            distinct_crit_vals = {t[0] for t in critical_intervals}
            log.debug(f"Distinct critical interval values: {distinct_crit_vals}")
            if len(distinct_crit_vals) > 1:
                log.debug(
                    f"[get_temporal_constraints] Multiple distinct critical intervals found "
                    f"for subtask {subtask_name}: {distinct_crit_vals}. "
                    "Returning TimeSlot(0, False, None)."
                )
                return TimeSlot(0, False, None)

            crit_interval, crit_linked = critical_intervals[0]
            log.debug(
                f"Using critical interval: {crit_interval} with linked subtask: {crit_linked}"
            )

            # 3) Non-critical 엣지도 있으면 최댓값 추출
            if non_critical_intervals:
                max_noncrit_interval, max_noncrit_linked = max(
                    non_critical_intervals, key=lambda x: x[0]
                )
                log.debug(
                    f"Max non-critical interval: {max_noncrit_interval} from subtask: {max_noncrit_linked}"
                )
                if crit_interval < max_noncrit_interval:
                    log.debug(
                        f"[get_temporal_constraints] Critical interval {crit_interval} < "
                        f"max non-critical {max_noncrit_interval}, conflict. "
                        "Returning TimeSlot(0, False, None)."
                    )
                    return TimeSlot(0, False, None)
                log.debug(f"Returning TimeSlot with critical interval: {crit_interval}")
                return TimeSlot(crit_interval, True, crit_linked)
            else:
                log.debug(
                    f"Returning TimeSlot with only critical interval: {crit_interval}"
                )
                return TimeSlot(crit_interval, True, crit_linked)

        # 4) Critical 엣지가 없는 경우 -> Non-critical 최댓값만 있으면 됨
        else:
            max_interval, max_linked = max(non_critical_intervals, key=lambda x: x[0])
            log.debug(
                f"Returning TimeSlot with non-critical max interval: {max_interval} from subtask: {max_linked}"
            )
            return TimeSlot(max_interval, False, max_linked)

    def get_feasible_subtasks(
        self,
        curr_node: SimulationNode,
    ) -> Tuple[List["Subtask"], List[Tuple["Subtask", float, bool]]]:
        """
        현재 스케줄 상태(state)에서,
        아직 실행 안 된 서브태스크들을 돌면서
        - 지금 당장(current_time) 실행 가능한 서브태스크들의 목록 (feasible)
        - 아직 시간이 안 되어 대기해야 하는 서브태스크들 목록 (not_yet)
            --> (Subtask, earliest_start, is_critical)

        return (feasible_subtasks, not_yet_list)
        """
        log.debug("Entering get_feasible_subtasks.")
        feasible_subtasks: List["Subtask"] = []
        not_yet_list: List[Tuple["Subtask", float, bool]] = []

        current_time = curr_node.state.current_time
        log.debug(f"Current simulation time: {current_time}")
        candidates = curr_node.state.remaining_subtasks
        constraints = curr_node.state.constraints
        log.debug(f"Number of remaining subtasks: {len(candidates)}")

        for sub in candidates:
            log.debug(f"Evaluating subtask '{sub.name}'.")
            earliest_start, is_exact = self._calc_earliest_start(
                curr_node, sub, constraints
            )
            log.debug(
                f"For subtask '{sub.name}', earliest_start: {earliest_start}, is_exact: {is_exact}"
            )

            if earliest_start is None:
                log.debug(
                    f"Subtask '{sub.name}' is not executable (missing predecessor completion or conflict)."
                )
                continue

            if is_exact:
                if abs(current_time - earliest_start) < 1e-9:
                    log.debug(
                        f"Subtask '{sub.name}' is feasible (exact match at current_time)."
                    )
                    feasible_subtasks.append(sub)
                elif current_time < earliest_start:
                    log.debug(
                        f"Subtask '{sub.name}' will be feasible at {earliest_start} (critical), waiting."
                    )
                    not_yet_list.append((sub, earliest_start, True))
                else:
                    log.debug(
                        f"Subtask '{sub.name}' missed its exact time window (current_time: {current_time})."
                    )
            else:
                if current_time >= earliest_start - 1e-9:
                    log.debug(
                        f"Subtask '{sub.name}' is feasible (non-critical, current_time >= earliest_start)."
                    )
                    feasible_subtasks.append(sub)
                else:
                    log.debug(
                        f"Subtask '{sub.name}' is not yet feasible (non-critical, waits until {earliest_start})."
                    )
                    not_yet_list.append((sub, earliest_start, False))

        log.debug(f"Feasible subtasks: {[s.name for s in feasible_subtasks]}")
        log.debug(
            f"Subtasks not yet ready: {[(s.name, t, c) for s, t, c in not_yet_list]}"
        )
        return feasible_subtasks, not_yet_list

    def _calc_earliest_start(
        self, curr_node: SimulationNode, sub: "Subtask", constraints: nx.DiGraph
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
        log.debug(f"Calculating earliest start for subtask '{sub.name}'.")
        in_edges = list(constraints.in_edges(sub.name, data=True))
        log.debug(f"Found {len(in_edges)} in-edges for subtask '{sub.name}'.")

        if not in_edges:
            log.debug(
                f"No prerequisites for subtask '{sub.name}', returning (0.0, False)."
            )
            return (0.0, False)

        critical_times = []
        non_critical_earliest = 0.0

        for pred_name, _, edge_data in in_edges:
            info = edge_data["info"]
            interval = info["Interval"]
            is_crit = info["IsCritical"]
            log.debug(
                f"Processing in-edge from '{pred_name}' with interval {interval} and isCritical={is_crit}."
            )

            # 선행 Subtask 완료 기록 탐색
            pred_entry = next(
                (
                    ce
                    for ce in curr_node.state.completed_subtasks
                    if ce.subtask.name == pred_name
                ),
                None,
            )
            if not pred_entry:
                log.debug(
                    f"Predecessor subtask '{pred_name}' has not been completed yet. Cannot execute '{sub.name}'."
                )
                return (None, False)

            candidate_start = pred_entry.end_time + interval
            log.debug(
                f"Predecessor '{pred_name}' completed at {pred_entry.end_time}; candidate start for '{sub.name}' is {candidate_start}."
            )

            if is_crit:
                critical_times.append(candidate_start)
            else:
                if candidate_start > non_critical_earliest:
                    non_critical_earliest = candidate_start

        log.debug(f"Critical times for subtask '{sub.name}': {critical_times}")
        log.debug(
            f"Non-critical earliest time for subtask '{sub.name}': {non_critical_earliest}"
        )

        if len(critical_times) > 1:
            unique_crit = set(critical_times)
            if len(unique_crit) != 1:
                log.debug(
                    f"Conflict detected: multiple distinct critical times for subtask '{sub.name}': {unique_crit}"
                )
                raise ValueError("Multiple distinct critical times found, conflict.")
            only_crit_time = next(iter(unique_crit))
            log.debug(
                f"All critical times match. Using critical time: {only_crit_time}"
            )
        elif len(critical_times) == 1:
            only_crit_time = critical_times[0]
            log.debug(f"Single critical time found: {only_crit_time}")
        else:
            only_crit_time = None

        if only_crit_time is not None:
            log.debug(
                f"Returning (earliest_start: {only_crit_time}, is_exact: True) for subtask '{sub.name}'."
            )
            return (only_crit_time, True)
        else:
            log.debug(
                f"Returning (earliest_start: {non_critical_earliest}, is_exact: False) for subtask '{sub.name}'."
            )
            return (non_critical_earliest, False)
