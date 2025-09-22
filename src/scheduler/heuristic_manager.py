from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional, Set, Tuple

import networkx as nx
import numpy as np  # 거리 계산 등에 사용될 수 있음

from src.models.dataclass import Candidate, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config import (  # INIT_PRIOR_MEAN, # 더 이상 직접 사용하지 않거나, interaction 추정에 활용
    ALPHA_HEURISTIC,
    BETA_HEURISTIC,
    EPSILON,
    GAMMA_HEURISTIC,
    LARGE_NUMBER,
)
from src.utils.config.constants import (
    GRASP_ACTION_DURATION,
    MONITORING_RISK_WEIGHT,
    NAV_STEP_DURATION,
    NORMALIZATION_CAP_NAV,
    NORMALIZATION_CAP_REMAINING_WORK,
    NORMALIZATION_CAP_TARDINESS,
    PLACE_ACTION_DURATION,
    TARDINESS_WEIGHT,
    TOGGLE_ACTION_DURATION,
)

# Forward declarations for type hinting
if TYPE_CHECKING:
    from src.models.task import Subtask
    from src.scheduler.action_handler import ActionHandler


log = create_module_logger(__name__, True, logging.DEBUG)


class HeuristicManager:
    """
    개선된 휴리스틱 매니저: 가상 다음 상태 기반 CP + MST 전략 사용

    비용 = alpha * 후보_네비게이션_비용
        + beta * 후보_긴급도_비용
        + gamma * (미래_CP_상호작용_시간 + 미래_MST_이동_시간)
    """

    def __init__(
        self,
        action_handler: "ActionHandler",
    ):
        self.action_handler = action_handler

        self.alpha = ALPHA_HEURISTIC
        self.beta = BETA_HEURISTIC
        self.gamma = GAMMA_HEURISTIC
        log.info(
            f"HeuristicManager initialized with weights: alpha={self.alpha}, beta={self.beta}, gamma={self.gamma}"
        )

    # ========================================================================
    # Helper Functions - 시간 및 위치 추정
    # ========================================================================

    def _get_estimated_pure_interaction_time(self, subtask: Subtask) -> float:
        """
        Subtask의 순수 상호작용 시간(네비게이션 및 대기 제외)을 추정합니다.
        Subtask.duration.interval이 순수 상호작용 시간을 나타낸다고 가정합니다.
        """
        if subtask.subtask_type in ["NAVIGATE", "WAIT", "MONITORING"]:
            return 0.0

        if subtask.duration and subtask.duration.interval is not None:
            # 여기서 subtask.duration.interval은 네비게이션이 아닌 순수 상호작용 시간으로 간주.
            return max(0.0, subtask.duration.interval)  # 음수 방지
        else:
            # duration 정보가 없는 상호작용 subtask의 경우, 기본값 또는 액션 기반 추정 필요.
            # 더 정교하게는 primitive_actions를 분석해야 함.
            num_interaction_actions = 0
            duration_sum = 0.0
            if subtask.execution and subtask.execution.primitive_actions:
                for action_str in subtask.execution.primitive_actions:
                    action_type = action_str.split(" ", 1)[0].upper()
                    if action_type not in ["NAVIGATE_TO", "WAIT", "MONITORING"]:
                        num_interaction_actions += 1
                        duration_map = {
                            "GRASP": GRASP_ACTION_DURATION,
                            "PLACE_INSIDE": PLACE_ACTION_DURATION,
                            "PLACE_ON_TOP": PLACE_ACTION_DURATION,
                            "OPEN": TOGGLE_ACTION_DURATION,
                            "CLOSE": TOGGLE_ACTION_DURATION,
                            "TOGGLE_ON": TOGGLE_ACTION_DURATION,
                            "TOGGLE_OFF": TOGGLE_ACTION_DURATION,
                            "SLICE": TOGGLE_ACTION_DURATION,
                            "FILL": PLACE_ACTION_DURATION,
                        }
                        duration_sum += duration_map.get(
                            action_type, TOGGLE_ACTION_DURATION
                        )

            if num_interaction_actions > 0:
                return duration_sum
            else:
                # log.debug(f"Subtask '{subtask.name}' has no duration and no clear interaction primitives. Estimating interaction time as 0.")
                return 0.0

    def _get_task_interaction_location(
        self, subtask: Subtask, scene_positions: Dict[str, any]
    ) -> Optional[Tuple[float, float, float]]:
        """
        Subtask의 주요 상호작용이 발생하는 위치를 반환합니다.
        첫 번째 NAVIGATE_TO의 타겟 또는 첫 번째 상호작용 액션의 타겟 위치를 사용합니다.
        """
        if not subtask.execution or not subtask.execution.primitive_actions:
            # log.debug(f"Subtask '{subtask.name}' has no execution/actions, cannot determine location.")
            return None

        first_nav_target_loc = None
        first_interaction_target_loc = None

        for action_str in subtask.execution.primitive_actions:
            tokens = action_str.split(" ", 2)
            action_type = tokens[0].upper()
            target_obj_id = tokens[1] if len(tokens) > 1 else None

            if action_type == "NAVIGATE_TO":
                if target_obj_id and target_obj_id in scene_positions:
                    # 네비게이션 타겟 위치를 찾으면, 이 위치가 이후 상호작용 위치일 가능성이 높음
                    first_nav_target_loc = tuple(scene_positions[target_obj_id])
                    break  # 첫 네비게이션 타겟을 우선 사용
                else:
                    log.warning(
                        f"Nav target '{target_obj_id}' for '{subtask.name}' not in scene_positions."
                    )
            elif target_obj_id and target_obj_id in scene_positions:
                # 네비게이션이 아닌 상호작용 액션의 타겟
                if not first_interaction_target_loc:  # 첫 번째 상호작용 타겟만 저장
                    first_interaction_target_loc = tuple(scene_positions[target_obj_id])
                    if (
                        not first_nav_target_loc
                    ):  # 아직 네비 타겟 못찾았으면 이것이 유력한 위치
                        break

        if first_nav_target_loc:
            # log.debug(f"Interaction location for '{subtask.name}' based on NAV_TO: {first_nav_target_loc}")
            return first_nav_target_loc
        if first_interaction_target_loc:
            # log.debug(f"Interaction location for '{subtask.name}' based on first interaction: {first_interaction_target_loc}")
            return first_interaction_target_loc

        # log.debug(f"Could not determine a specific interaction location for '{subtask.name}'.")
        return None  # 특정 위치를 요구하지 않는 작업 (예: WAIT)

    def _estimate_navigation_time_between_positions(
        self,
        pos1: Optional[Tuple[float, float, float]],
        pos2: Optional[Tuple[float, float, float]],
    ) -> float:
        """두 지점 간의 예상 네비게이션 시간을 action_handler를 통해 계산합니다."""
        if pos1 is None or pos2 is None or pos1 == pos2:
            return 0.0
        try:
            # _find_shortest_path는 경로(위치 리스트)를 반환. len(path)는 스텝 수로 가정.
            path = self.action_handler._find_shortest_path(pos1, pos2)
            # 경로가 비어있다면 (이미 같은 위치거나 매우 가까움), _find_shortest_path가 빈 리스트 반환 가정
            return len(path) * NAV_STEP_DURATION if path else 0.0
        except ValueError:  # 경로 탐색 실패 (_find_shortest_path에서 발생)
            log.warning(
                f"Pathfinding failed between {pos1} and {pos2}. Returning LARGE_NUMBER nav time."
            )
            return LARGE_NUMBER
        except Exception as e:  # 기타 예외
            log.error(
                f"Unexpected error in _estimate_navigation_time_between_positions ({pos1} to {pos2}): {e}"
            )
            return LARGE_NUMBER

    # ========================================================================
    # Helper Functions - CP 및 MST 계산
    # ========================================================================

    def _calculate_critical_path_interaction_duration(
        self, remaining_tasks: Set[Subtask], constraints: nx.DiGraph
    ) -> float:
        """
        남은 작업들의 제약 조건을 고려하여 Critical Path의 총 "순수 상호작용 시간 + Interval 시간"을 계산합니다.
        (네비게이션 시간은 MST에서 별도 계산)
        """
        if not remaining_tasks:
            return 0.0

        task_names_set = {sub.name for sub in remaining_tasks}
        # 제약 그래프에서 현재 남은 작업들만으로 구성된 부분 그래프 생성
        subgraph = constraints.subgraph(task_names_set).copy()

        if not nx.is_directed_acyclic_graph(subgraph):
            log.error(
                "Cycle detected in remaining task constraint subgraph for CP calculation."
            )
            return LARGE_NUMBER

        # 각 작업의 순수 상호작용 시간 계산
        task_pure_interaction_times = {
            sub.name: self._get_estimated_pure_interaction_time(sub)
            for sub in remaining_tasks
        }

        earliest_finish_times = {task_name: 0.0 for task_name in task_names_set}
        try:
            for task_name in nx.topological_sort(subgraph):
                max_earliest_finish_of_predecessors = 0.0
                for pred_name, _, edge_data in subgraph.in_edges(task_name, data=True):
                    # pred_name이 earliest_finish_times에 있는지 (즉, remaining_tasks에 속하는지) 확인
                    if pred_name in earliest_finish_times:
                        interval = edge_data.get("info", {}).get("Interval", 0.0)
                        max_earliest_finish_of_predecessors = max(
                            max_earliest_finish_of_predecessors,
                            earliest_finish_times[pred_name] + interval,
                        )

                interaction_time = task_pure_interaction_times.get(task_name, 0.0)
                earliest_finish_times[task_name] = (
                    max_earliest_finish_of_predecessors + interaction_time
                )

            max_ef = (
                max(earliest_finish_times.values()) if earliest_finish_times else 0.0
            )
            # log.debug(f"  Calculated Critical Path (Interaction + Interval) Duration: {max_ef:.2f}")
            return max_ef

        except nx.NetworkXUnfeasible:  # Cycle
            log.error("Cycle detected during topological sort for CP calculation.")
            return LARGE_NUMBER
        except Exception as e:
            log.error(f"Error calculating critical path duration: {e}")
            return LARGE_NUMBER

    def _calculate_mst_navigation_time(
        self,
        current_agent_pos: Optional[Tuple[float, float, float]],
        remaining_tasks: Set[Subtask],
        scene_positions: Dict[str, any],
    ) -> float:
        """
        현재 에이전트 위치와 남은 작업들의 상호작용 위치들을 모두 방문하는
        예상 총 네비게이션 시간을 MST(Minimum Spanning Tree)를 사용하여 추정합니다.
        """
        if not remaining_tasks:
            return 0.0

        locations_to_visit = set()
        if current_agent_pos:
            locations_to_visit.add(current_agent_pos)

        task_interaction_locations = []
        for subtask in remaining_tasks:
            loc = self._get_task_interaction_location(subtask, scene_positions)
            if loc:
                locations_to_visit.add(loc)
                task_interaction_locations.append(
                    loc
                )  # MST 이후 에이전트 시작점 연결 위해

        if (
            len(locations_to_visit) <= 1
        ):  # 방문할 다른 위치가 없거나 하나뿐 (현재 위치 포함)
            return 0.0

        location_list = list(locations_to_visit)
        num_locations = len(location_list)

        # 거리 행렬 생성 (가중치: 예상 네비게이션 시간)
        # dist_matrix[i, j]는 location_list[i]에서 location_list[j]까지의 네비게이션 시간
        dist_matrix = np.full((num_locations, num_locations), LARGE_NUMBER, dtype=float)
        for i in range(num_locations):
            dist_matrix[i, i] = 0.0  # 자기 자신으로의 거리는 0
            for j in range(i + 1, num_locations):
                pos1 = location_list[i]
                pos2 = location_list[j]
                nav_time = self._estimate_navigation_time_between_positions(pos1, pos2)
                dist_matrix[i, j] = nav_time
                dist_matrix[j, i] = nav_time  # 대칭

        try:
            from scipy.sparse import csr_matrix
            from scipy.sparse.csgraph import minimum_spanning_tree

            graph_sparse = csr_matrix(dist_matrix)
            mst = minimum_spanning_tree(graph_sparse)
            mst_total_nav_time = mst.sum()

            if mst_total_nav_time >= LARGE_NUMBER:  # 일부 위치 도달 불가능 시
                log.warning(
                    "MST calculation resulted in LARGE_NUMBER, possibly due to unreachable locations."
                )
                return LARGE_NUMBER

            # log.debug(f"  Calculated MST Navigation Time: {mst_total_nav_time:.2f}")
            return mst_total_nav_time

        except ImportError:
            log.error(
                "SciPy not found. MST calculation via SciPy is unavailable. Consider installing SciPy."
            )
            # SciPy 없을 시 매우 단순한 Fallback (모든 작업 위치로 현재 에이전트가 순차 이동 가정 - 매우 부정확)
            fallback_nav_time = 0.0
            if current_agent_pos and task_interaction_locations:
                # (이 부분은 TSP에 가까우므로 MST보다 더 부정확, 간단히 첫 작업까지만 고려하거나 다른 방법)
                # 여기서는 가장 가까운 작업 하나만 가는 시간으로 단순화 또는 합계.
                # 우선은 모든 작업 위치까지의 개별 네비 합으로 (중복 경로 고려 안됨)
                for loc in task_interaction_locations:
                    fallback_nav_time += (
                        self._estimate_navigation_time_between_positions(
                            current_agent_pos, loc
                        )
                    )
                log.warning(
                    f"SciPy missing, falling back to sum of nav times from agent: {fallback_nav_time:.2f}"
                )
                return (
                    fallback_nav_time
                    if fallback_nav_time < LARGE_NUMBER
                    else LARGE_NUMBER
                )
            return LARGE_NUMBER
        except Exception as e:
            log.error(f"Error calculating MST navigation time: {e}")
            return LARGE_NUMBER

    # ========================================================================
    # Main Heuristic Calculation Method
    # ========================================================================

    def calc_heuristic(
        self,
        current_node: SimulationNode,  # 현재 스케줄링 상태 노드
        candidate: Candidate,  # 평가할 후보 Subtask 정보
    ) -> float:
        """
        주어진 후보(Candidate)에 대한 휴리스틱 비용을 계산합니다.
        비용 = alpha * 후보_네비게이션_비용 + beta * 후보_긴급도_비용 + gamma * 미래_작업_비용
        """
        if not candidate or not candidate.subtask:
            log.error(
                "Invalid candidate or candidate.subtask provided to calc_heuristic."
            )
            return LARGE_NUMBER

        # --- 1. 후보 자체의 비용 (Cost for the candidate itself) ---
        # (a) 후보 실행을 위한 네비게이션 비용
        nav_cost_for_candidate = candidate.estimated_first_nav_duration or 0.0
        if nav_cost_for_candidate >= LARGE_NUMBER:
            log.warning(
                f"Candidate {candidate.subtask.name} nav cost is already LARGE_NUMBER."
            )
            return LARGE_NUMBER

        # (b) 후보의 긴급도 비용 (Slack 기반) 및 지연 시간(Tardiness)
        urgency_cost_for_candidate, slack_time = self._calculate_candidate_urgency_cost(
            current_node, candidate
        )
        tardiness = max(0.0, -slack_time)

        # (c) 모니터링 위험도 계산
        monitoring_risk_factor = self._calculate_monitoring_risk_factor(
            current_node, candidate
        )

        if urgency_cost_for_candidate >= LARGE_NUMBER:
            log.warning(
                f"Candidate '{candidate.subtask.name}' infeasible due to urgency: UrgencyCost={urgency_cost_for_candidate:.2f} (Slack={slack_time:.2f})"
            )
            return LARGE_NUMBER

        # --- 2. 후보 실행 후 남은 작업들에 대한 예상 비용 (Future work cost) ---
        remaining_work_cost = self._estimate_remaining_work_cost(
            current_node, candidate
        )
        if remaining_work_cost >= LARGE_NUMBER:
            log.warning(
                f"Future work cost for candidate '{candidate.subtask.name}' is LARGE_NUMBER. Marking as infeasible."
            )
            return LARGE_NUMBER

        # --- 3. 비용 정규화 (Normalization) ---
        norm_nav = min(nav_cost_for_candidate / NORMALIZATION_CAP_NAV, 1.0)
        norm_urgency = urgency_cost_for_candidate  # Already in 0-1 range
        norm_remaining_work = min(
            remaining_work_cost / NORMALIZATION_CAP_REMAINING_WORK, 1.0
        )
        norm_tardiness = min(tardiness / NORMALIZATION_CAP_TARDINESS, 1.0)
        norm_monitoring_risk = (
            monitoring_risk_factor  # Already a small value risk factor
        )

        # --- 4. 최종 휴리스틱 비용 계산 ---
        total_heuristic_cost = (
            self.alpha * norm_nav
            + self.beta * norm_urgency
            + self.gamma * norm_remaining_work
            + TARDINESS_WEIGHT * norm_tardiness
            + MONITORING_RISK_WEIGHT * norm_monitoring_risk
        )

        log.debug(
            f"  Heuristic for '{candidate.subtask.name}':\n"
            f"    - Nav      (raw): {nav_cost_for_candidate:<7.2f} -> norm: {norm_nav:<5.2f} -> weighted: {self.alpha * norm_nav:<5.2f}\n"
            f"    - Urgency  (raw): {urgency_cost_for_candidate:<7.2f} -> norm: {norm_urgency:<5.2f} -> weighted: {self.beta * norm_urgency:<5.2f} (Slack: {slack_time:.2f})\n"
            f"    - RemWork  (raw): {remaining_work_cost:<7.2f} -> norm: {norm_remaining_work:<5.2f} -> weighted: {self.gamma * norm_remaining_work:<5.2f}\n"
            f"    - Tardiness(raw): {tardiness:<7.2f} -> norm: {norm_tardiness:<5.2f} -> weighted: {TARDINESS_WEIGHT * norm_tardiness:<5.2f}\n"
            f"    - MonRisk  (raw): {monitoring_risk_factor:<7.2f} -> norm: {norm_monitoring_risk:<5.2f} -> weighted: {MONITORING_RISK_WEIGHT * norm_monitoring_risk:<5.2f}"
        )
        log.info(
            f"  => Total Heuristic Cost for '{candidate.subtask.name}': {total_heuristic_cost:.3f}"
        )

        return total_heuristic_cost

    def _estimate_remaining_work_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """후보 실행 후 남은 작업들에 대한 예상 비용 (CP 상호작용 + MST 네비게이션)"""
        try:
            candidate_full_execution_info = self.action_handler.get_actions_info(
                current_node, candidate.subtask.execution.primitive_actions
            )
            if not (
                candidate_full_execution_info and candidate_full_execution_info.success
            ):
                log.warning(
                    f"Full execution simulation of candidate '{candidate.subtask.name}' failed. Assigning high remaining work cost."
                )
                return LARGE_NUMBER

            virtual_next_agent_pos = tuple(
                candidate_full_execution_info.scene_positions.get("agent")
            )
            virtual_next_remaining_tasks = {
                task
                for task in current_node.state.remaining_subtasks
                if task.name != candidate.subtask.name
            }
            virtual_next_constraints = current_node.state.constraints
            virtual_next_scene_positions = candidate_full_execution_info.scene_positions

            future_cp_interaction_duration = (
                self._calculate_critical_path_interaction_duration(
                    virtual_next_remaining_tasks, virtual_next_constraints
                )
            )

            future_mst_navigation_time = self._calculate_mst_navigation_time(
                virtual_next_agent_pos,
                virtual_next_remaining_tasks,
                virtual_next_scene_positions,
            )

            if (
                future_cp_interaction_duration >= LARGE_NUMBER
                or future_mst_navigation_time >= LARGE_NUMBER
            ):
                log.warning(
                    f"Estimated future work cost is LARGE: CP={future_cp_interaction_duration:.2f}, MST={future_mst_navigation_time:.2f}"
                )
                return LARGE_NUMBER

            return future_cp_interaction_duration + future_mst_navigation_time

        except ValueError as e:
            log.error(
                f"Error simulating candidate {candidate.subtask.name} for future cost: {e}"
            )
            return LARGE_NUMBER
        except Exception as e:
            log.error(
                f"Unexpected error during future cost estimation for {candidate.subtask.name}: {e}"
            )
            return LARGE_NUMBER

    def _calculate_candidate_urgency_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[float, float]:  # (urgency_cost, slack_value)
        """
        후보의 긴급도 비용을 계산합니다.
        Slack = (후보 완료 마감 시각 - 현재 시각) - (후보 실행에 필요한 총 시간)
        후보 실행 필요 총 시간 = 후보 네비게이션 시간 + 후보 순수 상호작용 시간
        """
        if not candidate.scheduling_due or candidate.scheduling_due.due_date == float(
            "inf"
        ):
            return 0.0, float("inf")

        current_time = current_node.state.current_time
        deadline_for_candidate_completion = candidate.scheduling_due.due_date

        time_needed_for_nav = candidate.estimated_first_nav_duration or 0.0
        if time_needed_for_nav >= LARGE_NUMBER:
            return LARGE_NUMBER, -float("inf")

        time_needed_for_interaction = self._get_estimated_pure_interaction_time(
            candidate.subtask
        )

        total_time_needed_for_candidate = (
            time_needed_for_nav + time_needed_for_interaction
        )

        time_available_until_deadline = deadline_for_candidate_completion - current_time
        slack = time_available_until_deadline - total_time_needed_for_candidate

        urgency_cost = 0.0
        if slack < 0:
            # Tardiness가 발생하면 긴급도는 최대. 페널티는 tardiness_cost에서 별도 부과.
            urgency_cost = 1.0
        else:
            # Slack이 0에 가까우면 1, 커질수록 0에 수렴.
            urgency_cost = 1.0 / (
                slack / 10.0 + 1.0
            )  # Slack 10초당 긴급도가 절반으로 줄도록 스케일링

        return urgency_cost, slack

    def _calculate_monitoring_risk_factor(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:

        if candidate.is_critical:
            return 0.0

        scheduling_due = candidate.scheduling_due
        if (
            scheduling_due is None
            or scheduling_due.due_date == float("inf")
            or scheduling_due.due_related_sub_name is None
        ):
            return 0.0

        constraints = current_node.state.constraints
        critical_end_sub_name = scheduling_due.due_related_sub_name
        if not constraints or not constraints.has_node(critical_end_sub_name):
            return 0.0

        has_monitoring_pred = False
        for pred_name, _, _ in constraints.in_edges(critical_end_sub_name, data=True):
            if pred_name.startswith("Monitoring for "):
                has_monitoring_pred = True
                break

        if has_monitoring_pred:
            return 0.0

        time_until_due = scheduling_due.due_date - current_node.state.current_time
        if time_until_due <= 0:
            return 1.0  # Already late, max risk

        # due까지 30초 남았을 때 risk=0.5가 되도록 스케일링
        risk_factor = 1.0 / (time_until_due / 30.0 + 1.0)

        return risk_factor
