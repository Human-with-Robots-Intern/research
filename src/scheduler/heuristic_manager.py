from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

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

NON_INTERACTION_SUBTASK_TYPES = {"NAVIGATE", "WAIT"}
NON_INTERACTION_ACTION_TYPES = {"NAVIGATE_TO", "WAIT", "MONITORING"}


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
    ) -> Tuple[int, float]:
        """
        Calculates the heuristic cost and risk.

        [Heuristic Function h(n) Implementation]
        This implements the paper's heuristic cost function h(n) with practical extensions.
        - Risk Level: Maps to the paper's concept of 'temporal violation risk' (Slack Time Analysis).
          It explicitly assigns high penalties (Risk=2) for negative slack or future conflicts
          that exceed a small internal grace band.
        - Heuristic Cost: Corresponds to Eq (1) in the paper:
          h(n) = Sum(Duration_rem) + MST(Trem) + Sum(Unstarted_Critical_Intervals)
          (See _calculate_remaining_work_cost for details).

        Returns:
            - risk_level: The risk level of the candidate (0: Safe, 2: Deadline Violated/Conflict).
            - h(n): The estimated remaining cost (Remaining Work + Unstarted Debt).
              Note: This does NOT include g(n) (Current Time). The scheduler adds g(n) separately.
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
        future_conflict_delay, victim_task_name = self.check_future_conflict(
            current_node, candidate
        )
        if future_conflict_delay > constants.RISK_GRACE_SECONDS:
            log.warning(
                f"[_calculate_candidate_risk_and_urgency] Future Conflict Delay ({future_conflict_delay:.2f}) "
                f"exceeds grace ({constants.RISK_GRACE_SECONDS:.2f}s). "
                f"Victim: {victim_task_name}. Risk: 2.0"
            )
            return 2, 10000.0 + future_conflict_delay
        elif future_conflict_delay > constants.EPSILON:
            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Future Conflict Delay ({future_conflict_delay:.2f}) "
                f"within grace ({constants.RISK_GRACE_SECONDS:.2f}s). Keep Risk: 0.0"
            )

        # 2. Calculate Slack
        total_time_needed = (
            self._estimate_total_time_needed_for_deadline_violation_check(
                current_node, candidate
            )
        )
        time_available = deadline - current_time
        slack = time_available - total_time_needed

        log.debug(
            f"[_calculate_candidate_risk_and_urgency] Slack({slack:.2f}) = Deadline({deadline:.2f}) - Now({current_time:.2f}) - Needed({total_time_needed:.2f})"
        )

        # 3. Map Slack to Base Risk & Cost
        if slack >= -constants.RISK_GRACE_SECONDS:
            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Slack: {slack:.2f} within grace "
                f"({constants.RISK_GRACE_SECONDS:.2f}s) -> Risk: 0.0"
            )
            return 0, max(slack, 0.0)
        else:

            log.debug(
                f"[_calculate_candidate_risk_and_urgency] Slack: {slack:.2f} -> Risk: 2.0"
            )
            return 2, 10000.0 + abs(slack)

    def _estimate_total_time_needed_for_deadline_violation_check(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> float:
        """Estimates time needed for nav + interaction + lookahead return trip."""
        # 0,true로 묶인 A -> B가 있을 때 현재 지점에서 A까지 이동하는데 걸리는 시간
        nav_time = candidate.estimated_first_nav_duration or 0.0
        due_related_sub_name = (
            candidate.scheduling_due.due_related_sub_name
            if candidate.scheduling_due is not None
            else None
        )

        is_target_self = (
            candidate.scheduling_due and due_related_sub_name == candidate.subtask.name
        )

        simulated_profile = self._try_build_simulated_candidate_chain_profile(
            current_node, candidate
        )
        if is_target_self:
            total_time = nav_time
        elif simulated_profile is not None:
            chain_duration, chain_members, last_task_name, _, _ = simulated_profile
            total_time = nav_time + chain_duration
            if due_related_sub_name and due_related_sub_name not in chain_members:
                total_time += self._calculate_lookahead_nav_time(
                    current_node,
                    last_task_name,
                    due_related_sub_name,
                )
        else:
            # A,B의 총 작업 소요 시간
            chain_duration, chain_members, last_task_name = self._get_chain_info(
                current_node, candidate.subtask
            )
            total_time = (
                nav_time
                + chain_duration
                + self._get_candidate_due_check_duration_correction(
                    current_node,
                    candidate,
                    nav_time,
                )
            )
            if due_related_sub_name and due_related_sub_name not in chain_members:
                total_time += self._calculate_lookahead_nav_time(
                    current_node,
                    last_task_name,
                    due_related_sub_name,
                )

        return total_time

    def _try_build_simulated_candidate_chain_profile(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> Optional[Tuple[float, Set[str], str, float, Dict[str, float]]]:
        """Return a chain profile using actual simulated primitive runtimes.

        The returned tuple is:
            ``(chain_duration, chain_members, last_task_name, chain_end_delay,
            launch_profile)``

        ``chain_duration`` is measured from the candidate's interaction start,
        so the first subtask's initial navigation is excluded. ``chain_end_delay``
        is measured from ``current_time`` and therefore includes the candidate's
        first navigation.
        """

        graph = current_node.state.constraints
        chain_duration = 0.0
        chain_end_delay = 0.0
        chain_members: Set[str] = set()
        launch_profile: Dict[str, float] = {}
        last_task_name = candidate.subtask.name
        sim_node = current_node
        curr_subtask = candidate.subtask
        is_first_subtask = True

        def maybe_record_launch_source(
            subtask_name: str, source_end_delay: float
        ) -> None:
            if graph is None or not graph.has_node(subtask_name):
                return
            for _, _, data in graph.out_edges(subtask_name, data=True):
                info = data.get("info", {})
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) > constants.EPSILON
                ):
                    launch_profile[subtask_name] = source_end_delay
                    return

        while True:
            if curr_subtask.name in chain_members:
                break

            exec_info = self._simulate_subtask_from_node(sim_node, curr_subtask)
            if exec_info is None:
                return None

            step_total = float(exec_info.cumulative_time)
            first_nav = float(exec_info.first_nav_duration or 0.0)

            chain_end_delay += step_total
            if is_first_subtask:
                chain_duration += max(0.0, step_total - first_nav)
                is_first_subtask = False
            else:
                chain_duration += step_total

            chain_members.add(curr_subtask.name)
            last_task_name = curr_subtask.name
            maybe_record_launch_source(curr_subtask.name, chain_end_delay)
            sim_node = self._advance_simulated_node(sim_node, curr_subtask, exec_info)

            next_name = self._get_zero_interval_successor_name(graph, curr_subtask.name)
            if next_name is None:
                break

            next_subtask = self._get_remaining_subtask_by_name(current_node, next_name)
            if next_subtask is None:
                break
            curr_subtask = next_subtask

        return (
            chain_duration,
            chain_members,
            last_task_name,
            chain_end_delay,
            launch_profile,
        )

    def _build_candidate_chain_profile_static(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> Tuple[float, Set[str], str, float, Dict[str, float]]:
        """Return the legacy static chain profile used as a simulation fallback."""

        graph = current_node.state.constraints
        scene_positions = current_node.state.scene_positions
        initial_nav_delay = float(candidate.estimated_first_nav_duration or 0.0)
        chain_members: Set[str] = {candidate.subtask.name}
        launch_profile: Dict[str, float] = {}
        curr_name = candidate.subtask.name
        curr_subtask = candidate.subtask
        curr_pos = self._get_task_interaction_location(curr_subtask, scene_positions)
        last_task_name = curr_name
        chain_duration = self._get_estimated_pure_interaction_time(curr_subtask)
        chain_end_delay = initial_nav_delay + chain_duration

        def maybe_record_launch_source(
            subtask_name: str, source_end_delay: float
        ) -> None:
            if graph is None or not graph.has_node(subtask_name):
                return
            for _, _, data in graph.out_edges(subtask_name, data=True):
                info = data.get("info", {})
                if (
                    info.get("IsCritical")
                    and info.get("Interval", 0.0) > constants.EPSILON
                ):
                    launch_profile[subtask_name] = source_end_delay
                    return

        maybe_record_launch_source(curr_name, chain_end_delay)

        while True:
            next_name = self._get_zero_interval_successor_name(graph, curr_name)
            if next_name is None or next_name in chain_members:
                break

            next_subtask = self._get_remaining_subtask_by_name(current_node, next_name)
            if next_subtask is None:
                break

            next_pos = self._get_task_interaction_location(
                next_subtask, scene_positions
            )
            nav_delay = self._estimate_navigation_time_between_positions(
                curr_pos, next_pos
            )
            interaction_time = self._get_estimated_pure_interaction_time(next_subtask)
            chain_duration += nav_delay + interaction_time
            chain_end_delay += nav_delay + interaction_time
            chain_members.add(next_name)
            maybe_record_launch_source(next_name, chain_end_delay)

            curr_name = next_name
            last_task_name = curr_name
            curr_pos = next_pos

        return (
            chain_duration,
            chain_members,
            last_task_name,
            chain_end_delay,
            launch_profile,
        )

    def _get_candidate_chain_profile(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> Tuple[float, Set[str], str, float, Dict[str, float]]:
        """Return the best available chain timing profile for an active candidate."""

        simulated_profile = self._try_build_simulated_candidate_chain_profile(
            current_node, candidate
        )
        if simulated_profile is not None:
            return simulated_profile
        return self._build_candidate_chain_profile_static(current_node, candidate)

    def _simulate_subtask_from_node(
        self,
        current_node: SimulationNode,
        subtask: Subtask,
    ):
        """Simulate a subtask's primitive sequence from the provided node."""

        primitive_actions = (
            subtask.execution.primitive_actions if subtask.execution else None
        )
        if not primitive_actions:
            return None

        try:
            exec_info = self.action_handler.get_actions_info(
                current_node, primitive_actions
            )
        except ValueError:
            return None
        if exec_info is None or not exec_info.success:
            return None
        return exec_info

    @staticmethod
    def _advance_simulated_node(
        current_node: SimulationNode,
        subtask: Subtask,
        exec_info,
    ) -> SimulationNode:
        """Return a lightweight successor node after a simulated subtask run."""

        new_state = current_node.state._replace(
            subtask=subtask,
            current_time=float(current_node.state.current_time)
            + float(exec_info.cumulative_time),
            scene_positions=exec_info.scene_positions,
            held_object=exec_info.held_object,
        )
        return current_node._replace(state=new_state)

    @staticmethod
    def _get_zero_interval_successor_name(
        graph: Optional[nx.DiGraph],
        subtask_name: str,
    ) -> Optional[str]:
        """Return the immediate zero-interval critical successor, if any."""

        if graph is None or not graph.has_node(subtask_name):
            return None

        for _, target, data in graph.out_edges(subtask_name, data=True):
            info = data.get("info", {})
            if (
                info.get("IsCritical")
                and info.get("Interval", 0.0) <= constants.EPSILON
            ):
                return target
        return None

    @staticmethod
    def _get_remaining_subtask_by_name(
        current_node: SimulationNode,
        subtask_name: str,
    ) -> Optional[Subtask]:
        """Return a remaining subtask by name from the current search node."""

        return next(
            (
                subtask
                for subtask in current_node.state.remaining_subtasks
                if subtask.name == subtask_name
            ),
            None,
        )

    def _get_candidate_due_check_duration_correction(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
        nav_time: float,
    ) -> float:
        """Return the delta between simulated and static candidate duration.

        Deadline checks are sensitive to small timing errors. When the static
        subtask duration underestimates the simulated execution time, the slack
        calculation can incorrectly label a branch as safe. This correction keeps
        the inexpensive chain estimate but anchors the candidate's own duration to
        the action simulator whenever cached simulation data is available.
        """

        primitive_actions = (
            candidate.subtask.execution.primitive_actions
            if candidate.subtask.execution
            else None
        )
        if not primitive_actions:
            return 0.0

        exec_info = self.action_handler.get_actions_info(
            current_node, primitive_actions
        )
        if exec_info is None:
            return 0.0

        estimated_total = nav_time + self._get_estimated_pure_interaction_time(
            candidate.subtask
        )
        return float(exec_info.cumulative_time) - float(estimated_total)

    def _calculate_lookahead_nav_time(
        self,
        current_node: SimulationNode,
        origin_subtask_name: str,
        future_crit_name: str,
    ) -> float:
        origin_subtask = next(
            (
                t
                for t in current_node.state.remaining_subtasks
                if t.name == origin_subtask_name
            ),
            None,
        )
        future_subtask = next(
            (
                t
                for t in current_node.state.remaining_subtasks
                if t.name == future_crit_name
            ),
            None,
        )
        if origin_subtask is None or not future_subtask:
            return 0.0

        current_target_pos = self._get_task_interaction_location(
            origin_subtask, current_node.state.scene_positions
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

    def _build_chain_launch_profile(
        self,
        current_node: SimulationNode,
        candidate: Candidate,
    ) -> Tuple[float, Set[str], Dict[str, float]]:
        """Return timing-aware launch information for the candidate's zero-interval chain.

        Returns:
            chain_end_delay:
                Delay from ``current_time`` to the end of the candidate's committed
                zero-interval chain, including the candidate's initial navigation.
            chain_members:
                Names of subtasks executed as part of that zero-interval chain.
            launch_profile:
                Mapping from each chain subtask that launches a positive critical
                interval to the delay from ``current_time`` to the end of that
                source subtask.
        """

        _, chain_members, _, chain_end_delay, launch_profile = (
            self._get_candidate_chain_profile(current_node, candidate)
        )
        return chain_end_delay, chain_members, launch_profile

    def estimate_remaining_work_from_state(self, current_node: SimulationNode) -> float:
        """Estimate remaining work directly from an already-updated scheduler state.

        Monitoring branches sometimes rewrite the child node's remaining subtasks and
        constraint graph after the initial expansion cost has already been computed.
        In that case we want a fresh cost-to-go estimate from the rewritten state
        without giving launch/debt credit to any not-yet-dispatched successor chain.
        """

        remaining_tasks = list(current_node.state.remaining_subtasks)
        remaining_names = {task.name for task in remaining_tasks}

        sum_duration = sum(
            self._get_estimated_pure_interaction_time(task) for task in remaining_tasks
        )

        agent_position = current_node.state.scene_positions.get("agent")
        next_pos = tuple(agent_position) if agent_position is not None else None
        mst_time = self._calculate_mst_navigation_time(
            next_pos, remaining_tasks, current_node.state.scene_positions
        )

        debt = 0.0
        debt_infos = []
        for u, v, data in current_node.state.constraints.edges(data=True):
            info = data.get("info", {})
            interval = float(info.get("Interval", 0.0))
            if (
                info.get("IsCritical")
                and interval > constants.EPSILON
                and u in remaining_names
            ):
                debt += interval
                debt_infos.append(f"{u} -> {v} (Interval: {interval})")

        total_cost = sum_duration + mst_time + debt
        log.debug(
            "[estimate_remaining_work_from_state] %.2f = WorkSum(%.2f) + MST(%.2f) + Debt(%.2f)",
            total_cost,
            sum_duration,
            mst_time,
            debt,
        )
        for idx, debt_info in enumerate(debt_infos, 1):
            log.debug("    [State debt %d] %s", idx, debt_info)
        return total_cost

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
            chain_end_delay = 0.0
            launch_profile: Dict[str, float] = {}
        else:
            _, chain_members, _, chain_end_delay, launch_profile = (
                self._get_candidate_chain_profile(current_node, candidate)
            )

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
            next_pos, remaining_tasks, next_scene_pos
        )

        # 5. [핵심] Unstarted Critical Interval Debt (부채)
        # 아직 시작 안 된 태스크가 시점(Source)인 Critical Edge들의 Interval 합
        debt = 0.0
        graph = current_node.state.constraints

        use_residual_debt = (
            constants.MONITORING_ENABLED and candidate.subtask.subtask_type != "WAIT"
        )
        activated_tasks = {candidate.subtask.name}
        debt_infos = []

        # NONE_MONITORING keeps the legacy timing-blind debt credit so that the
        # existing baseline semantics remain unchanged.
        if (
            not use_residual_debt
            and candidate.subtask.subtask_type != "WAIT"
            and graph.has_node(candidate.subtask.name)
        ):
            activated_tasks.update(nx.descendants(graph, candidate.subtask.name))

        for u, v, data in graph.edges(data=True):
            info = data.get("info", {})
            # Critical하면서 Interval이 있는 경우 (유효한 제약조건)
            if info.get("IsCritical") and info.get("Interval", 0.0) > constants.EPSILON:
                interval = float(info["Interval"])
                if use_residual_debt and u in launch_profile:
                    source_end_delay = launch_profile[u]
                    elapsed_after_launch_by_child_completion = max(
                        0.0, chain_end_delay - source_end_delay
                    )
                    residual_debt = max(
                        0.0, interval - elapsed_after_launch_by_child_completion
                    )
                    debt += residual_debt
                    debt_infos.append(
                        f"{u} -> {v} (ResidualDebt: {residual_debt:.2f} / Interval: {interval:.2f}, "
                        f"chain_end_delay={chain_end_delay:.2f}, source_end_delay={source_end_delay:.2f})"
                    )
                    continue

                # 시작점 u가 아직 남은 작업 목록에 있다면 (= 아직 타이머가 안 켜졌다면)
                # 이 Interval은 우리가 짊어지고 있는 '잠재적 비용'입니다.
                if u in remaining_names:
                    # [Improved] If 'u' is activated by this candidate, skip adding debt.
                    if u in activated_tasks:
                        continue
                    debt += interval
                    debt_infos.append(f"{u} -> {v} (Interval: {interval})")

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
        """Estimate non-navigation execution time for a subtask.

        Args:
            subtask: Subtask whose execution footprint should be approximated.

        Returns:
            Estimated execution time excluding navigation. Monitoring subtasks keep
            their configured duration because the canonical subtask type is
            ``"Monitor"`` rather than the action token ``"MONITORING"``.
        """

        if subtask.subtask_type in NON_INTERACTION_SUBTASK_TYPES:
            return 0.0
        if subtask.duration and subtask.duration.interval is not None:
            return max(0.0, subtask.duration.interval)

        duration_sum = 0.0
        if subtask.execution and subtask.execution.primitive_actions:
            for action_str in subtask.execution.primitive_actions:
                action_type = action_str.split(" ", 1)[0].upper()
                if action_type not in NON_INTERACTION_ACTION_TYPES:
                    duration_map = {
                        "GRASP": GRASP_ACTION_DURATION,
                        "PLACE_INSIDE": PLACE_ACTION_DURATION,
                        "PLACE_ON_TOP": PLACE_ACTION_DURATION,
                        "OPEN": TOGGLE_ACTION_DURATION,
                        "CLOSE": TOGGLE_ACTION_DURATION,
                        "TOGGLE_ON": TOGGLE_ACTION_DURATION,
                        "TOGGLE_OFF": TOGGLE_ACTION_DURATION,
                        "SLICE": TOGGLE_ACTION_DURATION,
                        "FILL": TOGGLE_ACTION_DURATION,
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
        return max(len(path) - 1, 0) * NAV_STEP_DURATION if path else 0.0

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

    def check_future_conflict(
        self, current_node: SimulationNode, candidate: Candidate
    ) -> Tuple[float, Optional[str]]:
        """
        Checks if the candidate (or any task in its inseparable chain) starts a timer
        that will complete in a time window already reserved by other tasks.

        [Proactive Scheduling Implementation]
        This method implements the core 'Proactive' logic described in the research paper.
        Instead of reacting to conflicts when they occur, the scheduler looks ahead
        to identify if executing the current 'candidate' task will trigger a chain of events
        (e.g., starting a timer) that eventually collides with an existing reservation
        (e.g., another task's critical completion window).

        If a conflict is detected, it calculates the 'Conflict-Avoidance Wait' delay
        needed to shift the schedule safely, effectively 'waiting to prevent a future failure'.

        Returns:
            - max_conflict (float): The maximum delay required to resolve the conflict.
            - victim_task_name (Optional[str]): The name of the future task that is impacted (delayed).
        """
        graph = current_node.state.constraints
        _, _, _, _, launch_profile = self._get_candidate_chain_profile(
            current_node, candidate
        )
        future_tasks_info: List[Tuple[str, float]] = []
        if graph is not None:
            for source_name, source_end_delay in launch_profile.items():
                for _, target, data in graph.out_edges(source_name, data=True):
                    info = data.get("info", {})
                    if (
                        info.get("IsCritical")
                        and info.get("Interval", 0.0) > constants.EPSILON
                    ):
                        future_tasks_info.append(
                            (target, source_end_delay + float(info["Interval"]))
                        )

        if not future_tasks_info:
            return 0.0, None

        # 2. Get and Merge Reserved Windows
        # turn off 등 critical successor의 예정된 작업 block을 찾아옴.
        reserved_windows = self._get_reserved_windows(current_node)
        if not reserved_windows:
            return 0.0, None

        # Sort windows by start time
        # 가장 이른 timing 부터 load
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

        current_time = current_node.state.current_time

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
            ready_time = current_time + relative_ready_time

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

                    # DEFAULT runs should charge only the temporal blocking delay
                    # here. Adding travel from the reserved owner's tail task can
                    # overestimate conflict severity for productive interleavings.
                    total_delay = (
                        wait_delay
                        if constants.MONITORING_ENABLED
                        else wait_delay + travel_time
                    )

                    log.debug(
                        f"  [Future Conflict] Chain caused '{target_name}' (Start {ready_time:.2f}) "
                        f"overlaps with Merged Reserved Window [{r_start:.2f}, {r_end:.2f}] (Owners: {r_owners}). "
                        f"Wait: {wait_delay:.2f}, Travel: {travel_time:.2f} -> ConflictDelay: {total_delay:.2f}"
                    )
                    if total_delay > max_conflict:
                        max_conflict = total_delay
                        victim_task_name = target_name

        return max_conflict, victim_task_name
