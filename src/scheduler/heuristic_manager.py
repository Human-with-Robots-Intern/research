from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from src.models.dataclass import Candidate, SimulationNode
from src.utils.common import create_module_logger
from src.utils.config import LARGE_NUMBER, constants
from src.utils.config.constants import (
    GRASP_ACTION_DURATION,
    NAV_STEP_DURATION,
    PLACE_ACTION_DURATION,
    TOGGLE_ACTION_DURATION,
)

if TYPE_CHECKING:
    from src.models.task import Subtask
    from src.scheduler.action_handler import ActionHandler

log = create_module_logger(__name__, True, logging.DEBUG)


class HeuristicManager:
    """
    Manages the calculation of heuristic costs for scheduling candidates.
    Evaluates immediate costs (navigation, urgency) and future costs (remaining workload).
    """

    def __init__(self, action_handler: "ActionHandler"):
        self.action_handler = action_handler
        self.alpha = constants.ALPHA_HEURISTIC
        self.beta = constants.BETA_HEURISTIC
        self.gamma = constants.GAMMA_HEURISTIC
        log.info(
            f"HeuristicManager initialized with weights: alpha={self.alpha}, beta={self.beta}, gamma={self.gamma}"
        )

    def calc_heuristic(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        all_candidates: List[Candidate],
    ) -> Tuple[int, float, float]:
        """
        Calculates the heuristic cost: g(n) + h(n)
        g(n): Current Time
        h(n): Remaining Work + Unstarted Debt
        """

        # 1. Risk 계산 (기존 로직 유지)
        # Urgency Cost는 Risk Level 산출용으로만 씁니다.
        risk_level, _ = self._calculate_candidate_risk_and_urgency(
            current_node, candidate
        )

        # 2. Remaining Work Cost 계산 (Unstarted Debt 포함)
        remaining_work_cost = self._calculate_remaining_work_cost(
            current_node, candidate
        )

        # 3. Total Cost = g(n) + h(n)
        # g(n): 현재까지 흐른 시간 (current_node.state.current_time)
        # h(n): 앞으로 남은 예상 비용 (remaining_work_cost)
        total_heuristic_cost = remaining_work_cost

        return risk_level, total_heuristic_cost

    # ========================================================================
    # Core Logic: Urgency & Risk Calculation
    # ========================================================================

    def _calculate_candidate_risk_and_urgency(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[int, float]:
        """
        Calculates risk and urgency
        """
        # critical subtask가 not_yet에 존재하지 않는 경우에 대햐여.
        if not candidate.scheduling_due or candidate.scheduling_due.due_date == float(
            "inf"
        ):
            log.debug(
                "[_calculate_candidate_risk_and_urgency] No Deadline -> risk: 0.0"
            )
            return 0, 0.0

        current_time = current_node.state.current_time
        deadline = candidate.scheduling_due.due_date

        # 1. Future Reservation Check
        # 내가 시작하는 타이머 작업이 미래에 예약된 윈도우와 충돌하는지 검사
        future_conflict_delay, victim_task_name = self._check_future_conflict(
            current_node, candidate
        )
        if future_conflict_delay > 0:
            # [Added] Critical Check: If the delay exceeds tolerance, it's a planned violation.
            # We strictly enforce that we cannot plan a schedule that knowingly violates the tolerance.
            # Also applied a safety margin (3.0s) to be conservative.
            if future_conflict_delay > max(0.0, constants.TIMING_TOLERANCE_ABS):
                log.warning(
                    f"[_calculate_candidate_risk_and_urgency] Future Conflict Delay ({future_conflict_delay:.2f}) "
                    f"exceeds safety tolerance ({constants.TIMING_TOLERANCE_ABS}). "
                    f"Victim: {victim_task_name}. Risk: 2.0"
                )
                return 2, 10000.0 + future_conflict_delay

            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Future Reservation Conflict for '{candidate.subtask.name}' "
                f"-> Delay: {future_conflict_delay:.2f}s (Will be added to needed time)"
            )
            return 2, 10000.0 + future_conflict_delay

        # 2. Calculate Slack
        total_time_needed = (
            self._estimate_total_time_needed_for_deadline_violation_check(
                current_node, candidate
            )
            + future_conflict_delay
        )
        time_available = deadline - current_time
        slack = time_available - total_time_needed

        log.debug(
            f"[_calculate_candidate_risk_and_urgency] Slack({slack:.2f}) = Deadline({deadline:.2f}) - Now({current_time:.2f}) - Needed({total_time_needed:.2f})"
        )

        # 3. Map Slack to Base Risk & Cost
        if slack >= 0:
            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Slack: {slack:.2f} -> Risk: 0.0"
            )
            return 0, slack
        elif slack >= -constants.TIMING_TOLERANCE_ABS:
            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Slack: {slack:.2f} -> Risk: 1.0"
            )
            return 0, slack
        else:
            # [Rescue Logic] 연속 작업인 경우, Deadline 위배가 발생해도 Risk를 낮춰줌
            if self._is_consecutive_task(current_node, candidate):
                log.warning(
                    f"[_calculate_candidate_risk_and_urgency] RESCUE: Consecutive task '{candidate.subtask.name}' "
                    f"violates deadline (slack={slack:.2f}) but is rescued to Risk 0."
                )
                return 0, 10000.0 + abs(slack)

            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Slack: {slack:.2f} -> Risk: 2.0"
            )
            return 2, 10000.0 + abs(slack)

    def _is_consecutive_task(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> bool:
        """
        Checks if the candidate is a consecutive task (Critical & Interval ~ 0)
        following the last executed task.
        """
        if not current_node.state.subtask:
            return False

        last_name = current_node.state.subtask.name
        curr_name = candidate.subtask.name
        graph = current_node.state.constraints

        if graph.has_edge(last_name, curr_name):
            data = graph.get_edge_data(last_name, curr_name)
            info = data.get("info", {})
            if (
                info.get("IsCritical")
                and info.get("Interval", 0.0) <= constants.EPSILON
            ):
                return True

        return False

    def _estimate_total_time_needed_for_deadline_violation_check(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """Estimates time needed for nav + interaction + lookahead return trip."""
        # 0,true로 묶인 A -> B가 있을 때 현재 지점에서 A까지 이동하는데 걸리는 시간
        nav_time = candidate.estimated_first_nav_duration or 0.0
        # A,B의 총 작업 소요 시간
        chain_duration, _, _ = self._get_chain_info(current_node, candidate.subtask)
#         해결책: "가장 급한 불(Most Urgent Task)"을 기준으로 추정
# 비록 다음 태스크가 확정되지 않았더라도, "우리가 반드시 지켜야 할 데드라인을 가진 태스크"는 이미 알고 있습니다.
# Urgency Check: 현재 remaining_subtasks 중에서 scheduling_due(데드라인)가 있는 태스크들을 찾습니다.
# Worst-Case Estimation: 만약 내가 지금 Wash Fork(비크리티컬)를 수행한다면, 그 직후에 "가장 급한 태스크(Place Bread)"를 수행하러 가야 한다고 가정해야 안전합니다.
# Cost Calculation:
# 비용 = (Wash Fork 수행 시간) + (Wash Fork 종료 위치 -> Place Bread 시작 위치 이동 시간)

        # [Fix] If the deadline is for the candidate itself (Start Time Constraint),
        # we only need to arrive (Nav) by the deadline, not finish.
        is_target_self = (
            candidate.scheduling_due
            and candidate.scheduling_due.due_related_sub_name == candidate.subtask.name
        )

        if is_target_self:
            total_time = nav_time
        else:
            total_time = nav_time + chain_duration

        # # Lookahead: Check if we need to return to a future critical task location
        # future_crit_name = candidate.scheduling_due.due_related_sub_name
        # if future_crit_name and future_crit_name != candidate.subtask.name:
        #     lookahead_time = self._calculate_lookahead_nav_time(
        #         current_node, candidate, future_crit_name
        #     )
        #     total_time += lookahead_time

        #     # [FIXED] Add duration of the future critical task chain (e.g., Turn Off + Retrieve)
        #     # Previously, we only added navigation time, ignoring the interaction time of the future task.
        #     future_subtask = next(
        #         (
        #             t
        #             for t in current_node.state.remaining_subtasks
        #             if t.name == future_crit_name
        #         ),
        #         None,
        #     )
        #     if future_subtask:
        #         future_chain_dur, _ = self._get_chain_info(current_node, future_subtask)
        #         total_time += future_chain_dur

        return total_time

    def _calculate_lookahead_nav_time(
        self, current_node: SimulationNode, candidate: Candidate, future_crit_name: str
    ) -> float:
        future_subtask = next(
            (
                t
                for t in current_node.state.remaining_subtasks
                if t.name == future_crit_name
            ),
            None,
        )
        if not future_subtask:
            return 0.0

        current_target_pos = self._get_task_interaction_location(
            candidate.subtask, current_node.state.scene_positions
        ) or tuple(current_node.state.scene_positions.get("agent", (0, 0, 0)))

        future_target_pos = self._get_task_interaction_location(
            future_subtask, current_node.state.scene_positions
        )

        return self._estimate_navigation_time_between_positions(
            current_target_pos, future_target_pos
        )

    # ========================================================================
    # Helper Functions - Future Workload (Volume, CP, MST)
    # ========================================================================

    def _get_chain_info(
        self, current_node: SimulationNode, start_subtask: Subtask
    ) -> Tuple[float, Set[str], str]:
        """
        Calculates total duration and members of a critical chain starting from start_subtask.
        A chain is defined by consecutive tasks with Interval <= EPSILON.
        """
        # 0,true로 묶인 A -> B가 있을 때 현재 지점에서 A 작업하는데 걸리는 시간
        total_duration = self._get_estimated_pure_interaction_time(start_subtask)
        curr_name = start_subtask.name
        chain_members = {curr_name}
        last_task_name = curr_name

        curr_pos = self._get_task_interaction_location(
            start_subtask, current_node.state.scene_positions
        )

        while True:
            # Find immediate critical successor with zero interval
            next_name = None
            out_edges = current_node.state.constraints.out_edges(curr_name, data=True)
            for _, target, data in out_edges:
                info = data.get("info", {})
                # 0, True로 엮인 연속 작업에 대하여.
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) <= constants.EPSILON
                ):
                    next_name = target
                    break
            # 연속 작업 B가 있는 경우에, chain member에 B를 추가
            if next_name and next_name not in chain_members:
                chain_members.add(next_name)
                # Find the subtask object to get duration
                next_sub = next(
                    (
                        t
                        for t in current_node.state.remaining_subtasks
                        if t.name == next_name
                    ),
                    None,
                )
                # 연속 작업 B의 duration을 추가
                if next_sub:
                    # 1. Add interaction duration
                    total_duration += self._get_estimated_pure_interaction_time(
                        next_sub
                    )

                    # 2. Add navigation duration (Chain internal travel)
                    next_pos = self._get_task_interaction_location(
                        next_sub, current_node.state.scene_positions
                    )
                    nav_time = self._estimate_navigation_time_between_positions(
                        curr_pos, next_pos
                    )
                    total_duration += nav_time

                    curr_name = next_name
                    last_task_name = curr_name
                    curr_pos = next_pos  # Update position for next hop
                    continue
            break

        return total_duration, chain_members, last_task_name

    def _calculate_remaining_work_cost(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """
        Estimates cost: Sum of Durations + MST + Unstarted Critical Intervals (Debt)
        """

        # 1. 이번 스텝에서 처리될 것으로 간주하는 체인 멤버 파악
        if candidate.subtask.subtask_type == "WAIT":
            # [Modified] WAIT는 연결된 작업들을 활성화(부채 탕감)하지 않아야 함.
            # 단순히 시간을 보내는 것이므로, 체인으로 묶인 후속 작업들의 부채를 탕감해주면 안 됨.
            chain_members = {candidate.subtask.name}
        else:
            _, chain_members, _ = self._get_chain_info(current_node, candidate.subtask)

        # 2. 남은 태스크 목록 (이번 후보 제외)
        remaining_tasks = [
            t
            for t in current_node.state.remaining_subtasks
            if t.name not in chain_members
        ]
        remaining_names = {t.name for t in remaining_tasks}

        # 3. Sum of Durations (작업 시간 총량 - 단순 합)
        sum_duration = sum(
            self._get_estimated_pure_interaction_time(t) for t in remaining_tasks
        )

        # 4. MST (이동 시간 추정)
        # 시뮬레이션 실행하여 다음 위치 파악
        exec_info = self.action_handler.get_actions_info(
            current_node, candidate.subtask.execution.primitive_actions
        )
        if exec_info:
            next_pos = tuple(exec_info.scene_positions.get("agent"))
            next_scene_pos = exec_info.scene_positions
        else:
            next_pos = None
            next_scene_pos = current_node.state.scene_positions

        mst_time = self._calculate_mst_navigation_time(
            next_pos, current_node.state.remaining_subtasks, next_scene_pos
        )

        # 5. [핵심] Unstarted Critical Interval Debt (부채)
        # 아직 시작 안 된 태스크가 시점(Source)인 Critical Edge들의 Interval 합
        debt = 0.0
        graph = current_node.state.constraints

        # [Improved] Find all descendants reachable from the current candidate.
        # If a task 'u' is a descendant of the candidate (or the candidate itself),
        # launching the candidate effectively "activates" the chain leading to 'u'.
        # Thus, we should NOT count the interval starting at 'u' as "Unstarted Debt".
        # This encourages starting long chains early.
        activated_tasks = {candidate.subtask.name}
        debt_infos = []
        # [Fix] Wait actions do NOT activate future tasks immediately.
        # They only delay time. We should NOT forgive debt for Wait actions.
        # Only actual task execution activates the chain.
        # [Modified] 모든 후손(descendants)을 활성화하면 미래의 부채까지 과도하게 탕감되어
        # 현재 실행하는 체인의 가치가 비정상적으로 높아지는 문제가 있습니다.
        # 따라서 현재 실행되는 체인((0, True) 연결 포함)만 탕감 대상으로 삼기 위해
        # descendants 확장 로직을 비활성화합니다.
        # (참고: 실행되는 체인 멤버들은 이미 remaining_names에서 제외되어 자동으로 탕감됩니다.)
        if candidate.subtask.subtask_type != "WAIT" and graph.has_node(
            candidate.subtask.name
        ):
            activated_tasks.update(nx.descendants(graph, candidate.subtask.name))

        for u, v, data in graph.edges(data=True):
            info = data.get("info", {})
            # Critical하면서 Interval이 있는 경우 (유효한 제약조건)
            if info.get("IsCritical") and info.get("Interval", 0.0) > constants.EPSILON:
                # 시작점 u가 아직 남은 작업 목록에 있다면 (= 아직 타이머가 안 켜졌다면)
                # 이 Interval은 우리가 짊어지고 있는 '잠재적 비용'입니다.
                if u in remaining_names:
                    # [Improved] If 'u' is activated by this candidate, skip adding debt.
                    if u in activated_tasks:
                        continue
                    debt += info["Interval"]
                    debt_infos.append(f"{u} -> {v} (Interval: {info['Interval']})")

        log.debug(
            f"[_calculate_remaining_work_cost] {sum_duration + mst_time + debt:.2f} = WorkSum({sum_duration:.2f}) + MST({mst_time:.2f}) + Debt({debt:.2f})"
        )
        for idx, debt_info in enumerate(debt_infos, 1):
            log.debug(f"    [Debt info {idx}] {debt_info}")
        return sum_duration + mst_time + debt

    # ========================================================================
    # Helper Functions - Estimation & Graph
    # ========================================================================

    def _get_estimated_pure_interaction_time(self, subtask: Subtask) -> float:
        if subtask.subtask_type in ["NAVIGATE", "WAIT", "MONITORING"]:
            return 0.0
        if subtask.duration and subtask.duration.interval is not None:
            return max(0.0, subtask.duration.interval)

        duration_sum = 0.0
        if subtask.execution and subtask.execution.primitive_actions:
            for action_str in subtask.execution.primitive_actions:
                action_type = action_str.split(" ", 1)[0].upper()
                if action_type not in ["NAVIGATE_TO", "WAIT", "MONITORING"]:
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
        return duration_sum

    def _get_task_interaction_location(
        self, subtask: Subtask, scene_positions: dict[str, any]
    ) -> Optional[Tuple[float, float, float]]:
        if not subtask.execution or not subtask.execution.primitive_actions:
            return None

        # Priority: NAVIGATE target -> First Action target
        for action_str in subtask.execution.primitive_actions:
            tokens = action_str.split(" ", 2)
            if len(tokens) > 1:
                target_id = tokens[1]
                if target_id in scene_positions:
                    return tuple(scene_positions[target_id])
        return None

    def _estimate_navigation_time_between_positions(
        self,
        pos1: Optional[Tuple[float, float, float]],
        pos2: Optional[Tuple[float, float, float]],
    ) -> float:
        if pos1 is None or pos2 is None or pos1 == pos2:
            return 0.0
        path = self.action_handler._find_shortest_path(pos1, pos2)
        return len(path) * NAV_STEP_DURATION if path else 0.0

    def _calculate_mst_navigation_time(
        self,
        current_agent_pos: Optional[Tuple[float, float, float]],
        remaining_tasks: Set[Subtask],
        scene_positions: dict[str, any],
    ) -> float:
        if not remaining_tasks:
            return 0.0

        locations = {current_agent_pos} if current_agent_pos else set()
        for t in remaining_tasks:
            loc = self._get_task_interaction_location(t, scene_positions)
            if loc:
                locations.add(loc)

        if len(locations) <= 1:
            return 0.0

        loc_list = list(locations)
        n = len(loc_list)
        dist_matrix = np.full((n, n), LARGE_NUMBER, dtype=float)

        for i in range(n):
            dist_matrix[i, i] = 0.0
            for j in range(i + 1, n):
                d = self._estimate_navigation_time_between_positions(
                    loc_list[i], loc_list[j]
                )
                dist_matrix[i, j] = dist_matrix[j, i] = d

        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import minimum_spanning_tree

        mst = minimum_spanning_tree(csr_matrix(dist_matrix))
        return mst.sum()

    def _get_reserved_windows(
        self, current_node: SimulationNode
    ) -> List[Tuple[float, float, str, str]]:
        """
        Calculates reserved time windows by future tasks that are already committed
        (i.e., tasks waiting for a timer to finish and their subsequent chains).
        Returns a list of (start_time, end_time, owner_task_name, last_task_name) tuples.
        """
        reserved_windows = []
        constraints = current_node.state.constraints
        completed_map = {
            ce.subtask.name: ce for ce in current_node.state.completed_entries
        }
        remaining_subtasks_map = {
            t.name: t for t in current_node.state.remaining_subtasks
        }

        # Check all critical edges where U is completed and V is remaining
        for u, v, data in constraints.edges(data=True):
            if u in completed_map and v in remaining_subtasks_map:
                info = data.get("info", {})
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) > constants.EPSILON
                ):
                    # Found a pending timer task (V)
                    # Calculate Expected Start Time of V
                    u_end_time = completed_map[u].schedule_end_time
                    interval = info["Interval"]
                    expected_start_time = u_end_time + interval

                    # Calculate Chain Duration starting from V
                    v_subtask = remaining_subtasks_map[v]
                    chain_duration, _, last_task_name = self._get_chain_info(
                        current_node, v_subtask
                    )

                    reserved_windows.append(
                        (
                            expected_start_time,
                            expected_start_time + chain_duration,
                            v,  # Owner task name (reservation holder)
                            last_task_name,  # Last task in the reserved chain
                        )
                    )

        return reserved_windows

    def _check_future_conflict(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[float, Optional[str]]:
        """
        Checks if the candidate (or any task in its inseparable chain) starts a timer
        that will complete in a time window already reserved by other tasks.
        Returns:
            - max_conflict (float): The maximum delay required to resolve the conflict.
            - victim_task_name (Optional[str]): The name of the future task that is impacted (delayed).
        """
        # 1. Identify all future timer tasks launched by the candidate's chain
        candidate_name = candidate.subtask.name
        graph = current_node.state.constraints

        future_tasks_info = (
            []
        )  # List of (target_name, relative_ready_time_from_chain_start)

        # We need to track the cumulative time from the start of the candidate execution
        # to the completion of each task in the chain.
        curr_name = candidate_name

        # Duration of the candidate task itself
        current_relative_time = self._get_estimated_pure_interaction_time(
            candidate.subtask
        )

        # Check candidate's outgoing timer edges
        for _, target, data in graph.out_edges(curr_name, data=True):
            info = data.get("info", {})
            if info.get("IsCritical") and info.get("Interval", 0.0) > constants.EPSILON:
                # Found a timer edge. The timer starts when curr_task ENDS.
                future_tasks_info.append(
                    (target, current_relative_time + info["Interval"])
                )

        # Traverse the rest of the chain
        while True:
            next_name = None
            for _, target, data in graph.out_edges(curr_name, data=True):
                info = data.get("info", {})
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) <= constants.EPSILON
                ):
                    next_name = target
                    break

            if next_name:
                # Found next link in chain. Find the subtask object.
                next_sub = next(
                    (
                        t
                        for t in current_node.state.remaining_subtasks
                        if t.name == next_name
                    ),
                    None,
                )
                if not next_sub:
                    break

                # Calculate Nav + Interaction to get to the end of next_sub
                # Current Pos is location of curr_name task
                if curr_name == candidate.subtask.name:
                    curr_sub = candidate.subtask
                else:
                    curr_sub = next(
                        (
                            t
                            for t in current_node.state.remaining_subtasks
                            if t.name == curr_name
                        ),
                        None,
                    )

                if curr_sub:
                    curr_pos = self._get_task_interaction_location(
                        curr_sub, current_node.state.scene_positions
                    )
                else:
                    curr_pos = None  # Should not happen

                next_pos = self._get_task_interaction_location(
                    next_sub, current_node.state.scene_positions
                )

                nav_time = self._estimate_navigation_time_between_positions(
                    curr_pos, next_pos
                )
                interaction_time = self._get_estimated_pure_interaction_time(next_sub)

                current_relative_time += nav_time + interaction_time

                # Check next task's outgoing timer edges
                for _, target, data in graph.out_edges(next_name, data=True):
                    info = data.get("info", {})
                    if (
                        info.get("IsCritical")
                        and info.get("Interval", 0.0) > constants.EPSILON
                    ):
                        future_tasks_info.append(
                            (target, current_relative_time + info["Interval"])
                        )

                curr_name = next_name
            else:
                break

        if not future_tasks_info:
            return 0.0, None

        # 2. Get and Merge Reserved Windows
        reserved_windows = self._get_reserved_windows(current_node)
        if not reserved_windows:
            return 0.0, None

        # Sort windows by start time
        reserved_windows.sort(key=lambda x: x[0])

        # Merge overlapping/adjacent windows
        merged_windows = []
        if reserved_windows:
            # Structure: (start, end, owners_set, last_task_name)
            curr_start, curr_end, curr_owner, curr_last_task = reserved_windows[0]
            curr_owners = {curr_owner}

            for i in range(1, len(reserved_windows)):
                r_start, r_end, r_owner, r_last_task = reserved_windows[i]
                # If current window overlaps or is adjacent to the merged window
                if r_start <= curr_end + constants.EPSILON:
                    if r_end > curr_end:
                        curr_end = r_end
                        curr_last_task = r_last_task
                    curr_owners.add(r_owner)
                else:
                    merged_windows.append(
                        (curr_start, curr_end, curr_owners, curr_last_task)
                    )
                    curr_start, curr_end = r_start, r_end
                    curr_owners = {r_owner}
                    curr_last_task = r_last_task
            merged_windows.append((curr_start, curr_end, curr_owners, curr_last_task))

        # 3. Check each future task against merged reserved windows
        max_conflict = 0.0
        victim_task_name = None

        # Chain Start Time (estimated)
        cand_nav = candidate.estimated_first_nav_duration or 0.0
        current_time = current_node.state.current_time
        chain_start_time = current_time + cand_nav

        for target_name, relative_ready_time in future_tasks_info:
            target_subtask = next(
                (
                    t
                    for t in current_node.state.remaining_subtasks
                    if t.name == target_name
                ),
                None,
            )
            if not target_subtask:
                continue

            # Expected Ready Time for Future Task
            ready_time = chain_start_time + relative_ready_time

            # Target Duration (Chain)
            target_dur, _, _ = self._get_chain_info(current_node, target_subtask)

            # Check overlap with merged reserved windows
            for (
                r_start,
                r_end,
                r_owners,
                r_last_task,
            ) in merged_windows:  # Iterate over merged windows
                # Ignore Self-Conflict: If the reservation belongs ONLY to the target task, skip it.
                if len(r_owners) == 1 and target_name in r_owners:
                    continue

                if target_name in r_owners:
                    # This block includes the reservation for the target task itself.
                    # We should trust that the reservation was made correctly and allow using it.
                    continue

                # Task Interval: [ready_time, ready_time + target_dur]
                # Merged Reserved Interval: [r_start, r_end]

                start_max = max(ready_time, r_start)
                end_min = min(ready_time + target_dur, r_end)

                if start_max < end_min:
                    # Overlap detected
                    # We strictly calculate delay required to wait out the block.
                    wait_delay = r_end - ready_time

                    if wait_delay <= constants.EPSILON:
                        continue

                    # [Added] Calculate Travel Time from Reserved Block End to Target Task
                    # If we wait for the reserved block, the agent is effectively at the location of r_last_task.
                    # We must travel to target_subtask.

                    # Find r_last_task object (it might be completed or remaining)
                    r_last_subtask = next(
                        (
                            t
                            for t in current_node.state.remaining_subtasks
                            if t.name == r_last_task
                        ),
                        None,
                    )
                    # If not in remaining, check completed
                    if not r_last_subtask:
                        ce = next(
                            (
                                c
                                for c in current_node.state.completed_entries
                                if c.subtask.name == r_last_task
                            ),
                            None,
                        )
                        if ce:
                            r_last_subtask = ce.subtask

                    travel_time = 0.0
                    if r_last_subtask:
                        r_last_pos = self._get_task_interaction_location(
                            r_last_subtask, current_node.state.scene_positions
                        )
                        target_pos = self._get_task_interaction_location(
                            target_subtask, current_node.state.scene_positions
                        )
                        travel_time = self._estimate_navigation_time_between_positions(
                            r_last_pos, target_pos
                        )

                    total_delay = wait_delay + travel_time

                    log.debug(
                        f"  [Future Conflict] Chain caused '{target_name}' (Start {ready_time:.2f}) "
                        f"overlaps with Merged Reserved Window [{r_start:.2f}, {r_end:.2f}] (Owners: {r_owners}). "
                        f"Wait: {wait_delay:.2f} + Travel({r_last_task}->{target_name}): {travel_time:.2f} = Total Delay: {total_delay:.2f}"
                    )
                    if total_delay > max_conflict:
                        max_conflict = total_delay
                        victim_task_name = target_name

        return max_conflict, victim_task_name
