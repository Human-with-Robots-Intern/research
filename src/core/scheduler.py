from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, TypeAlias

from src.core.monitoring import (
    BeliefStore,
    MonitoringPolicy,
    MonitoringTriggerContext,
    create_monitoring_policy,
)
from src.models.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SchedulingDue,
    SimulationNode,
)
from src.models.task import Duration, Execution, Subtask
from src.scheduler.deadline_utils import get_candidate_effective_due, has_finite_due
from src.utils.common import create_module_logger, extract_monitoring_target_name
from src.utils.common.decorators import time_logger
from src.utils.config import (
    EPSILON,
    MONITORING_DURATION,
    RED,
    RESET,
    constants,
)
from src.utils.config.constants import BEAM_WIDTH, SIMULATION_DEPTH
from src.utils.task import TaskUtil

if TYPE_CHECKING:
    from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager

log = create_module_logger(module_name=__name__, module_log=True)

INTERACTION_READINESS_NUMERIC_EPSILON = 1e-6

ActiveIntervalCacheKey: TypeAlias = Tuple[int, Tuple[Tuple[str, float], ...]]
MonitoringTriggerCacheKey: TypeAlias = Tuple[str, Optional[str], float, float, float]
ActionInfoCache: TypeAlias = Dict[object, Optional[ActionResult]]
TimeSlotCache: TypeAlias = Dict[object, Tuple[object, ...]]


@dataclass
class SchedulerSearchCache:
    """Caches repeated calculations during a single scheduler search call."""

    action_results: ActionInfoCache = field(default_factory=dict)
    time_slots: TimeSlotCache = field(default_factory=dict)
    active_intervals: Dict[
        ActiveIntervalCacheKey, List[Tuple[float, SchedulingDue]]
    ] = field(default_factory=dict)
    monitoring_triggers: Dict[MonitoringTriggerCacheKey, float] = field(
        default_factory=dict
    )
    action_cache_hits: int = 0
    action_cache_misses: int = 0
    time_slot_cache_hits: int = 0
    time_slot_cache_misses: int = 0
    active_interval_cache_hits: int = 0
    active_interval_cache_misses: int = 0
    trigger_cache_hits: int = 0
    trigger_cache_misses: int = 0


@dataclass(frozen=True)
class TriggeredMonitoringObligation:
    """Describe one active critical interval whose monitoring trigger has matured."""

    critical_start_sub_name: str
    critical_start_sub_end_time: float
    critical_end_sub_name: str
    critical_interval_duration: float
    variance: float
    trigger_time: float
    monitoring_target_obj: str
    target_candidate: Optional[Candidate]
    ready_now: bool


class Scheduler:
    """
    Beam Search based Scheduler with n-step lookahead.
    Given a current state, it attempts to find the best next subtask to execute
    by simulating expansions of feasible (or soon-to-be-feasible) subtasks.

    Attributes:
        search_width (int): Beam width (number of top expansions to keep).
        simulation_depth (int): Maximum search depth for lookahead.
        nav_graph (dict): Navigation graph for path planning.

        action_handler (ActionHandler): Handles action duration calculations.
        constraint_handler (ConstraintHandler): Checks subtask feasibility.
        cost_calculator (HeuristicManager): Calculates heuristic cost of expansions.
        _counter (itertools.count): A counter to break ties in the priority queue.
    """

    def __init__(
        self,
        action_handler: ActionHandler,
        constraint_handler: ConstraintHandler,
        heuristic_manager: HeuristicManager,
        monitoring_policy: Optional[MonitoringPolicy] = None,
        beam_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
        max_monitoring_per_critical_interval: int | None = None,
    ) -> None:
        """Initialize the scheduler and its expansion policies.

        Args:
            action_handler: Simulates primitive action durations.
            constraint_handler: Evaluates temporal feasibility.
            heuristic_manager: Scores expanded nodes.
            monitoring_policy: Optional backend-specific monitoring trigger policy.
            beam_width: Layer-wise beam width.
            simulation_depth: Lookahead depth for beam search.
            max_monitoring_per_critical_interval: Optional cap for how many
                monitoring actions may execute within one critical interval.
                Negative values represent an explicit unbounded budget.
        """

        self.search_width = beam_width
        self.simulation_depth = simulation_depth
        log.info(
            f"{RED}[Scheduler Init] search_width={beam_width}, simulation_depth={simulation_depth}{RESET}"
        )
        self.constraint_handler = constraint_handler
        self.action_handler = action_handler
        self.cost_calculator = heuristic_manager
        self.monitoring_policy = monitoring_policy or create_monitoring_policy(
            "bayesian",
            BeliefStore(),
        )
        self.max_monitoring_per_critical_interval = (
            max_monitoring_per_critical_interval
        )
        self._counter = itertools.count()
        self._search_cache: Optional[SchedulerSearchCache] = None

    def _begin_search_session(self) -> None:
        """Create and attach search-scoped caches for the current beam search."""

        self._search_cache = SchedulerSearchCache()
        if hasattr(self.action_handler, "begin_search_session"):
            self.action_handler.begin_search_session(self._search_cache.action_results)
        if hasattr(self.constraint_handler, "begin_search_session"):
            self.constraint_handler.begin_search_session(self._search_cache.time_slots)

    def _end_search_session(self) -> None:
        """Detach search-scoped caches and emit debug statistics."""

        if self._search_cache is None:
            return

        action_hits, action_misses = (0, 0)
        time_slot_hits, time_slot_misses = (0, 0)
        if hasattr(self.action_handler, "end_search_session"):
            action_hits, action_misses = self.action_handler.end_search_session()
        if hasattr(self.constraint_handler, "end_search_session"):
            time_slot_hits, time_slot_misses = (
                self.constraint_handler.end_search_session()
            )
        self._search_cache.action_cache_hits = action_hits
        self._search_cache.action_cache_misses = action_misses
        self._search_cache.time_slot_cache_hits = time_slot_hits
        self._search_cache.time_slot_cache_misses = time_slot_misses
        log.debug(
            "[Scheduler Cache] action hits=%d misses=%d, time_slot hits=%d misses=%d, "
            "active_interval hits=%d misses=%d, trigger hits=%d misses=%d",
            self._search_cache.action_cache_hits,
            self._search_cache.action_cache_misses,
            self._search_cache.time_slot_cache_hits,
            self._search_cache.time_slot_cache_misses,
            self._search_cache.active_interval_cache_hits,
            self._search_cache.active_interval_cache_misses,
            self._search_cache.trigger_cache_hits,
            self._search_cache.trigger_cache_misses,
        )
        self._search_cache = None

    @staticmethod
    def _build_completed_entries_signature(
        completed_entries: List[CompletedEntry],
    ) -> Tuple[Tuple[str, float], ...]:
        """Create a hashable signature for completed entries relevant to monitoring."""

        return tuple(
            (entry.subtask.name, entry.schedule_end_time) for entry in completed_entries
        )

    def _get_active_monitoring_intervals(
        self, curr_node: SimulationNode
    ) -> List[Tuple[float, SchedulingDue]]:
        """Return active critical intervals for the current node with memoization.

        Args:
            curr_node: Node whose completed tasks and constraints define active intervals.

        Returns:
            Active intervals as `(variance, due)` tuples.
        """

        graph = curr_node.state.constraints
        cache_key = (
            id(graph),
            self._build_completed_entries_signature(curr_node.state.completed_entries),
        )
        if self._search_cache is not None:
            cached_intervals = self._search_cache.active_intervals.get(cache_key)
            if cached_intervals is not None:
                self._search_cache.active_interval_cache_hits += 1
                return cached_intervals

        completed_entries_map = {
            ce.subtask.name: ce for ce in curr_node.state.completed_entries
        }
        active_intervals: List[Tuple[float, SchedulingDue]] = []
        for start_name, end_name, data in graph.edges(data=True):
            info = data.get("info", {})
            if info.get("IsCritical") and info.get("Interval") > EPSILON:
                if (
                    start_name in completed_entries_map
                    and end_name not in completed_entries_map
                ):
                    start_entry = completed_entries_map[start_name]
                    if start_entry.subtask.subtask_type != "Monitor":
                        interval = info.get("Interval", 0.0)
                        variance = info.get("Variance", constants.INIT_PRIOR_VARIANCE)
                        due_date = start_entry.schedule_end_time + interval
                        active_intervals.append(
                            (
                                variance,
                                SchedulingDue(
                                    due_date=due_date, due_related_sub_name=end_name
                                ),
                            )
                        )

        if self._search_cache is not None:
            self._search_cache.active_interval_cache_misses += 1
            self._search_cache.active_intervals[cache_key] = active_intervals
        return active_intervals

    # ======================
    # Public method
    # ======================
    @time_logger
    def get_next_state(self, parent_state: SchedulerState) -> Optional[SchedulerState]:
        """
        Public method to retrieve the immediate next state (1-step ahead in time)
        from the given parent_state.

        Args:
            parent_state (SchedulerState): The current scheduling state.

        Returns:
            Optional[SchedulerState]: The next state after scheduling one subtask,
            or None if no feasible solution is found.
        """
        child_node = self._simulate_search(parent_state)
        if child_node is None:
            log.error("[get_next_state] No child_state found => No feasible solution.")
            return None

        new_state = self._extract_state(child_node)
        if new_state is None:
            log.error("[get_next_state] child_state found, but state is None.")
            return None

        log.debug(
            f"[get_next_state] => subtask={new_state.subtask.name}, "
            f"time={round(new_state.current_time,2)}"
        )
        return new_state

    # ======================
    # Core beam search
    # ======================
    def _simulate_search(self, init_state: SchedulerState) -> Optional[SimulationNode]:
        """
        Conducts a Layer-wise Beam Search up to self.simulation_depth.
        At each depth, we keep only the top `search_width` nodes (Layer-wise Pruning).

        Args:
            init_state (SchedulerState): The root state to start the simulation.

        Returns:
            Optional[SimulationNode]: The best goal node (lowest cost) among expansions.
        """
        self._begin_search_session()
        try:
            # 1. Initialize Beam
            init_node = SimulationNode(
                parent_node=None,
                heuristic_cost=0.0,
                depth=0,
                tie_breaker=next(self._counter),
                state=init_state,
                risk_level=0,
            )
            current_beam: List[SimulationNode] = [init_node]
            complete_solutions: List[SimulationNode] = []

            log.debug(
                f"[_simulate_search] Starting Layer-wise Beam Search (Width={self.search_width}, Depth={self.simulation_depth})"
            )

            # 2. Layer-wise Loop
            for d in range(self.simulation_depth):
                if not current_beam:
                    log.debug(
                        f"[_simulate_search] Beam is empty at depth {d}. Stopping."
                    )
                    break

                next_beam_candidates: List[SimulationNode] = []

                # Expand all nodes in the current beam
                for curr_node in current_beam:
                    curr_state = curr_node.state

                    # (A) Check Termination (All tasks done?)
                    if not curr_state.remaining_subtasks:
                        log.debug(
                            f"  [Solution Found] Node depth {curr_node.depth} finished all tasks."
                        )
                        complete_solutions.append(curr_node)
                        continue
                    log.debug(
                        f"\n=== [Beam Step] Depth {d} -> {d+1} | Beam Size: {len(current_beam)} | Current Time: {curr_state.current_time:.2f} ==="
                    )
                    # (B) Get Feasible Candidates
                    feasible_candidates, not_yet_candidates = (
                        self.constraint_handler.get_feasible_candidates(curr_node)
                    )

                    if not feasible_candidates and not not_yet_candidates:
                        # Dead end
                        continue

                    # (C) Expand
                    log.debug(
                        f"\n  • Completed : {[ce.subtask.name for ce in curr_state.completed_entries]}\n"
                        f"  • Remaining : {[r.name for r in curr_state.remaining_subtasks]}\n"
                        f"  • Feasible  : {[c.subtask.name for c in feasible_candidates]}\n"
                        f"  • Not Yet   : {[c.subtask.name for c in not_yet_candidates]}\n"
                        f"============================================================"
                    )
                    expanded_nodes = self._expand_candidates(
                        curr_node, feasible_candidates, not_yet_candidates
                    )

                    # (D) Collect Valid Expansions
                    # [Modified 251229] Risk 2 이상이라도, 대안이 없으면 채택하기 위해 별도로 수집합니다.
                    valid_expansions = []
                    high_risk_expansions = []

                    for nd in expanded_nodes:
                        if nd.risk_level < 2:
                            valid_expansions.append(nd)
                        else:
                            high_risk_expansions.append(nd)

                    if valid_expansions:
                        next_beam_candidates.extend(valid_expansions)
                    elif high_risk_expansions:
                        # 정상적인(Risk < 2) 후보가 하나도 없을 때만 Risk 높은 후보를 고려합니다.
                        log.warning(
                            f"[_simulate_search] Depth {d}: No valid expansions found. "
                            f"Fallback to {len(high_risk_expansions)} High-Risk candidates."
                        )
                        next_beam_candidates.extend(high_risk_expansions)

                # 3. Pruning (Layer-wise)
                if not next_beam_candidates:
                    log.debug(
                        f"[_simulate_search] No valid expansions at depth {d} (including high-risk)."
                    )
                    break

                # Sort by (Risk, Cost) to pick top K
                # Risk is primary, Cost (Heuristic) is secondary.
                next_beam_candidates.sort(
                    key=lambda nd: (nd.risk_level, nd.heuristic_cost)
                )

                # Keep top K
                current_beam = next_beam_candidates[: self.search_width]
                log.debug(
                    "============================================================"
                )
                log.debug(f"Layer-wise Beam Search: Depth {d} -> {d+1}")
                # Log the survivors
                log.debug(
                    f"  -> Pruning: Kept top {len(current_beam)} out of {len(next_beam_candidates)} candidates."
                )
                for i, node in enumerate(current_beam):
                    # Trace back path
                    path_names = []
                    curr = node
                    while curr:
                        if curr.state and curr.state.subtask:
                            path_names.append(curr.state.subtask.name)
                        curr = curr.parent_node
                    path_str = " -> ".join(reversed(path_names))

                    log.debug(
                        f"     [{i+1}] {path_str} (Risk={node.risk_level}, Cost={node.heuristic_cost:.2f})"
                    )
                log.debug(
                    "============================================================"
                )

            # 4. Final Collection
            # Roll back to the mixed winner-selection policy so complete and
            # frontier candidates compete in the same pool.
            best_solutions = list(complete_solutions)
            if current_beam:
                best_solutions.extend(current_beam)

            if not best_solutions:
                log.error("[_simulate_search] best_solutions empty => no feasible path")
                return None

            def get_depth1_node(node: SimulationNode) -> SimulationNode:
                """Backtrack to the depth-1 node that would actually be committed."""
                curr = node
                while curr.depth > 1:
                    if curr.parent_node:
                        curr = curr.parent_node
                    else:
                        break
                return curr

            depth1_node_by_node = {
                id(node): get_depth1_node(node) for node in best_solutions
            }
            depth1_cost_by_node = {
                id(node): depth1_node_by_node[id(node)].heuristic_cost
                for node in best_solutions
            }
            depth1_risk_by_node = {
                id(node): depth1_node_by_node[id(node)].risk_level
                for node in best_solutions
            }

            # 5. Select Winner
            # ``heuristic_cost`` stored on each frontier/complete node is already
            # the node's total ``g + h`` estimate. Re-adding the committed
            # depth-1 cost here would double-count the path prefix and can bias
            # the final immediate action toward a cheaper first step even when
            # its best reachable leaf is worse. Keep depth-1 cost only as a
            # stable tie-breaker.
            best_solutions.sort(
                key=lambda nd: (
                    nd.risk_level,
                    nd.heuristic_cost,
                    depth1_cost_by_node[id(nd)],
                    nd.tie_breaker,
                )
            )
            log.debug(
                "[_simulate_search] rollback best_solution "
                f"(leaf={best_solutions[0].state.subtask.name}, "
                f"leaf_risk={best_solutions[0].risk_level}, "
                f"depth1_risk={depth1_risk_by_node[id(best_solutions[0])]}, "
                f"leaf_cost={best_solutions[0].heuristic_cost:.2f}, "
                f"depth1_cost={depth1_cost_by_node[id(best_solutions[0])]:.2f})"
            )

            winner = best_solutions[0]

            # Trace back to find the immediate next action (Depth 1)
            immediate_node = depth1_node_by_node[id(winner)]

            log.debug(
                f"\n[_simulate_search] Final Decision: Path selected (Leaf: '{winner.state.subtask.name}').\n"
                f"  -> Immediate Action: '{immediate_node.state.subtask.name}'\n"
                f"  (LeafRisk={winner.risk_level}, "
                f"Depth1Risk={depth1_risk_by_node[id(winner)]}, "
                f"Depth1_Cost={depth1_cost_by_node[id(winner)]:.2f}, "
                f"Leaf_Cost={winner.heuristic_cost:.2f}, Depth={winner.depth})"
            )
            return winner
        finally:
            self._end_search_session()

    def _extract_state(
        self, child_node: Optional[SimulationNode]
    ) -> Optional[SchedulerState]:
        """
        Traces from a terminal node (child_node) back to the root (init_state),
        and returns the **state at depth=1** in that path. This effectively
        picks the next immediate step in the best path found.

        Args:
            child_node (SimulationNode): The best solution node from the beam search.

        Returns:
            Optional[SchedulerState]: The state corresponding to the next step
            (depth=1). If only the root is found, returns the root state.
        """
        if child_node is None:
            log.error("[_extract_state] child_node is None")
            return None

        path = self._trace_solution_path(child_node)

        # If only the root (depth=0) is present
        if len(path) < 2:
            log.debug("[_extract_state] Only root node in path. No feasible next step.")
            return None

        # Return the state at the first step beyond root (depth=1)
        log.debug("[_extract_state] Returning state at depth=1 in the best path.")
        return path[1].state

    def _trace_solution_path(self, child_node: SimulationNode) -> List[SimulationNode]:
        """Trace a winner leaf back to the root and return the forward path."""

        path: List[SimulationNode] = []
        current_node: Optional[SimulationNode] = child_node
        while current_node:
            path.append(current_node)
            current_node = current_node.parent_node
        path.reverse()
        return path

    def _expand_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """
        Expands candidates based on a unified policy to prioritize critical tasks.

        Policy Hierarchy:
        0. Ready-Now Critical Ends:
           - If any critical end can begin interacting right now, expand ONLY
             those direct execution branches. Monitoring no longer preempts an
             already-executable critical handoff.
        1. Trigger-Matured Monitoring Obligations:
           - If no ready-now critical end exists, expand ONLY explicit monitor
             branches for intervals whose monitoring trigger has matured.
        2. Urgent Critical Tasks (Unified):
           - If any critical task is ready to start (within tolerance) or overdue,
             expand ONLY these tasks. This combines On-time, Closing, and Missed policies.
        3. Standard Expansion:
           - If no urgent tasks, expand all feasible tasks and valid 'WAIT' options.
        """
        expansions: List[SimulationNode] = []
        ready_now_critical_candidates = (
            self._collect_ready_now_critical_end_candidates(
                curr_node,
                feasible_candidates,
            )
        )
        if ready_now_critical_candidates:
            log.debug(
                "Policy 0 (Ready-Now Critical): expanding %d ready-now critical candidate(s).",
                len(ready_now_critical_candidates),
            )
            for candidate in ready_now_critical_candidates:
                direct_execution_node = self._expand_subtask_wo_monitoring(
                    curr_node,
                    candidate,
                    not_yet_candidates,
                    feasible_candidates,
                )
                if direct_execution_node is not None:
                    expansions.append(direct_execution_node)
            if expansions:
                return expansions
            log.debug(
                "Ready-now critical ends exist, but no direct-execution branch survived."
            )
            return expansions

        triggered_obligations = self._collect_trigger_matured_monitoring_obligations(
            curr_node,
            feasible_candidates,
            not_yet_candidates,
        )
        if triggered_obligations:
            log.debug(
                "Policy 1 (Triggered Monitoring): expanding %d triggered obligation(s).",
                len(triggered_obligations),
            )
            expansions.extend(
                self._expand_triggered_monitoring_obligations(
                    curr_node,
                    triggered_obligations,
                    feasible_candidates,
                    not_yet_candidates,
                )
            )
            if expansions:
                return expansions
            log.debug(
                "Triggered monitoring obligations exist, but no admissible monitor/direct-execution branch survived."
            )
            return expansions

        feasible_candidates, not_yet_candidates = (
            self._apply_reserved_prenavigation_filter(
                curr_node,
                feasible_candidates,
                not_yet_candidates,
            )
        )

        # --- Policy 1 (Unified): Urgent Critical Tasks ---
        urgent_candidates = self._get_urgent_critical_candidates(
            curr_node, feasible_candidates, not_yet_candidates
        )

        if urgent_candidates:
            log.debug(
                f"Policy 1 (Urgent): Expanding {len(urgent_candidates)} urgent candidate(s)."
            )
            for candidate in urgent_candidates:
                # [Added 250202] Conflict-Avoidance Wait for Urgent Tasks
                # Check if immediate execution causes future conflicts.
                # Even for urgent tasks, if execution leads to a future deadline violation,
                # we should consider waiting (which might violate the current urgent interval,
                # but allows the scheduler to weigh the costs).
                conflict_delay, _ = self.cost_calculator.check_future_conflict(
                    curr_node, candidate
                )

                if conflict_delay > constants.EPSILON:
                    nav_time = self._estimate_candidate_navigation_duration(
                        curr_node, candidate
                    )
                    wait_node = self._expand_wait_wo_monitoring(
                        curr_node,
                        candidate,
                        not_yet_candidates,
                        nav_duration=nav_time,
                        feasible_candidates=feasible_candidates,
                        additional_delay=conflict_delay,
                    )

                    if wait_node:
                        log.debug(
                            f"[Conflict-Avoidance] Generated Wait Node for URGENT {candidate.subtask.name} "
                            f"(Delay: {conflict_delay:.2f}s) to avoid future conflict."
                        )
                        expansions.append(wait_node)

                child_node = self._expand_single_subtask(
                    curr_node, candidate, not_yet_candidates, feasible_candidates
                )
                if child_node:
                    expansions.append(child_node)

            if expansions:
                return expansions
            else:
                log.debug(
                    "All urgent candidates failed to expand. Falling back to standard expansion."
                )

        # --- Policy 2: Standard Expansion (other feasible + all waits) ---
        log.debug("Policy 2: No urgent criticals. Performing standard expansion.")
        for candidate in feasible_candidates:

            # 2. [Added 250130] Conflict-Avoidance Wait
            # Check if immediate execution causes future conflicts.
            # If so, generate an alternative 'Wait' node that delays execution just enough to avoid the conflict.
            conflict_delay, _ = self.cost_calculator.check_future_conflict(
                curr_node, candidate
            )

            if conflict_delay > constants.EPSILON:
                nav_time = self._estimate_candidate_navigation_duration(
                    curr_node, candidate
                )
                wait_node = self._expand_wait_wo_monitoring(
                    curr_node,
                    candidate,
                    not_yet_candidates,
                    nav_duration=nav_time,
                    feasible_candidates=feasible_candidates,
                    additional_delay=conflict_delay,
                )

                if wait_node:
                    log.debug(
                        f"[Conflict-Avoidance] Generated Wait Node for {candidate.subtask.name} "
                        f"(Delay: {conflict_delay:.2f}s) to avoid future conflict."
                    )
                    expansions.append(wait_node)

            # 1. Expand Action (Immediate Execution)
            child_node = self._expand_single_subtask(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
            if child_node:
                expansions.append(child_node)

        expansions.extend(
            self._expand_blocked_frontier_candidates(
                curr_node,
                feasible_candidates,
                not_yet_candidates,
            )
            )

        return expansions

    def _collect_ready_now_critical_end_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
    ) -> List[Candidate]:
        """Return critical feasible candidates that can interact immediately."""

        ready_now_candidates = [
            candidate
            for candidate in feasible_candidates
            if candidate.is_critical
            and self._can_candidate_start_interaction_now(curr_node, candidate)
        ]
        if ready_now_candidates:
            log.debug(
                "[_collect_ready_now_critical_end_candidates] ready-now critical candidates: %s",
                [candidate.subtask.name for candidate in ready_now_candidates],
            )
        return ready_now_candidates

    def _collect_trigger_matured_monitoring_obligations(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[TriggeredMonitoringObligation]:
        """Return active critical intervals whose monitoring trigger has matured."""

        current_time = curr_node.state.current_time
        feasible_by_name = {
            candidate.subtask.name: candidate for candidate in feasible_candidates
        }
        candidate_by_name = {
            candidate.subtask.name: candidate
            for candidate in feasible_candidates + not_yet_candidates
        }
        completed_entries_map = {
            completed_entry.subtask.name: completed_entry
            for completed_entry in curr_node.state.completed_entries
        }
        remaining_by_name = {
            remaining_subtask.name: remaining_subtask
            for remaining_subtask in curr_node.state.remaining_subtasks
        }
        obligations_by_target: Dict[str, TriggeredMonitoringObligation] = {}

        for start_name, end_name, data in curr_node.state.constraints.edges(data=True):
            info = data.get("info", {})
            interval = float(info.get("Interval", 0.0))
            if not info.get("IsCritical") or interval <= EPSILON:
                continue

            start_entry = completed_entries_map.get(start_name)
            if start_entry is None or start_entry.subtask.subtask_type == "Monitor":
                continue

            remaining_subtask = remaining_by_name.get(end_name)
            if remaining_subtask is None:
                continue

            if self._monitoring_budget_reached(
                curr_node.state,
                critical_start_sub_end_time=start_entry.schedule_end_time,
                critical_end_sub_name=end_name,
            ):
                continue

            monitoring_target_obj = self._get_monitoring_target_object_from_subtask(
                remaining_subtask
            )
            if monitoring_target_obj is None:
                continue

            trigger_time = self._compute_monitoring_trigger_time(
                raw_object_name=monitoring_target_obj,
                critical_start_sub_end_time=start_entry.schedule_end_time,
                mean_duration=interval,
                variance=float(
                    info.get("Variance", constants.INIT_PRIOR_VARIANCE)
                ),
            )
            if current_time < (trigger_time - EPSILON):
                continue

            target_candidate = candidate_by_name.get(end_name)
            ready_now = False
            if target_candidate is not None and end_name in feasible_by_name:
                ready_now = self._can_candidate_start_interaction_now(
                    curr_node,
                    target_candidate,
                )

            obligation = TriggeredMonitoringObligation(
                critical_start_sub_name=start_name,
                critical_start_sub_end_time=start_entry.schedule_end_time,
                critical_end_sub_name=end_name,
                critical_interval_duration=interval,
                variance=float(info.get("Variance", constants.INIT_PRIOR_VARIANCE)),
                trigger_time=trigger_time,
                monitoring_target_obj=monitoring_target_obj,
                target_candidate=target_candidate,
                ready_now=ready_now,
            )

            existing_obligation = obligations_by_target.get(end_name)
            if existing_obligation is None or trigger_time < (
                existing_obligation.trigger_time - EPSILON
            ):
                obligations_by_target[end_name] = obligation

        ordered_obligations = sorted(
            obligations_by_target.values(),
            key=lambda obligation: (
                0 if obligation.ready_now else 1,
                obligation.trigger_time,
                obligation.critical_end_sub_name,
            ),
        )
        for obligation in ordered_obligations:
            log.debug(
                "[_collect_trigger_matured_monitoring_obligations] target='%s' trigger=%.2f current=%.2f ready_now=%s",
                obligation.critical_end_sub_name,
                obligation.trigger_time,
                current_time,
                obligation.ready_now,
            )
        return ordered_obligations

    def _expand_triggered_monitoring_obligations(
        self,
        curr_node: SimulationNode,
        obligations: List[TriggeredMonitoringObligation],
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """Expand only explicit monitor or direct-execution branches for matured triggers."""

        expansions: List[SimulationNode] = []
        for obligation in obligations:
            if obligation.ready_now:
                target_candidate = obligation.target_candidate or self._find_candidate_by_name(
                    feasible_candidates,
                    obligation.critical_end_sub_name,
                )
                if target_candidate is None:
                    log.debug(
                        "[_expand_triggered_monitoring_obligations] ready target '%s' was not reconstructable as a feasible candidate.",
                        obligation.critical_end_sub_name,
                    )
                    continue
                direct_execution_node = self._expand_subtask_wo_monitoring(
                    curr_node,
                    target_candidate,
                    not_yet_candidates,
                    feasible_candidates,
                )
                if direct_execution_node is not None:
                    expansions.append(direct_execution_node)
                continue

            explicit_monitor_node = self._expand_explicit_triggered_monitoring_obligation(
                curr_node,
                obligation,
                not_yet_candidates,
                feasible_candidates,
            )
            if explicit_monitor_node is not None:
                expansions.append(explicit_monitor_node)

        return expansions

    def _expand_blocked_frontier_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[SimulationNode]:
        """Expand wait/prenav alternatives for the earliest blocked frontier."""

        expansions: List[SimulationNode] = []
        if not not_yet_candidates:
            return expansions

        blocked_frontier = self._get_blocked_candidate_frontier(not_yet_candidates)
        for blocked_candidate in blocked_frontier:
            log.debug(
                "[_expand_candidates] blocked frontier candidate: %s",
                blocked_candidate,
            )
            wait_node = self._expand_single_wait(
                curr_node,
                blocked_candidate,
                not_yet_candidates,
                feasible_candidates=feasible_candidates,
            )
            if wait_node:
                expansions.append(wait_node)

            if self._has_productive_filler_preserving_blocked_frontier(
                curr_node,
                blocked_candidate,
                feasible_candidates,
                not_yet_candidates,
            ):
                log.debug(
                    "[_expand_blocked_frontier_candidates] skipped pre-nav for '%s' because a productive filler preserves its frontier.",
                    blocked_candidate.subtask.name,
                )
            else:
                prenavigation_node = self._expand_blocked_prenavigation(
                    curr_node,
                    blocked_candidate,
                    not_yet_candidates,
                    feasible_candidates=feasible_candidates,
                )
                if prenavigation_node:
                    expansions.append(prenavigation_node)

        return expansions

    def _get_urgent_critical_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> List[Candidate]:
        """
        Identifies critical candidates that are 'Urgent'.

        Urgent means the task has entered the same near-deadline window that makes it
        feasible for immediate handling. This keeps Policy 1 aligned with the
        feasibility gate used for critical tasks that are inside the monitoring horizon.
        Also checks not_yet_candidates for urgent but blocked tasks, prioritizing their feasible predecessors.
        """

        urgent_list = []
        for candidate in feasible_candidates:
            if not candidate.is_critical:
                continue

            if candidate.logical_interaction_start_time is None:
                continue

            physical_earliest_start = (
                curr_node.state.current_time + candidate.estimated_first_nav_duration
            )
            log.debug(
                f"[_get_urgent_critical_candidates] diff: {candidate.logical_interaction_start_time - physical_earliest_start}"
            )

            # Check urgency: Are we at or past the horizon where this critical
            # candidate deserves attention? Exact interaction-start readiness is
            # enforced separately by ``_can_candidate_start_interaction_now``.
            log.debug(
                f"[_get_urgent_critical_candidates] candidate.logical_interaction_start_time: {candidate.logical_interaction_start_time}, physical_earliest_start: {physical_earliest_start}"
            )

            if (
                candidate.logical_interaction_start_time - physical_earliest_start
            ) <= (MONITORING_DURATION + EPSILON):
                if not self._can_candidate_start_interaction_now(curr_node, candidate):
                    log.debug(
                        "Found horizon-urgent critical candidate '%s', but interaction cannot start exactly yet "
                        "(Physical: %.2f, Logical: %.2f). Keeping it blocked for wait/prenav expansion.",
                        candidate.subtask.name,
                        physical_earliest_start,
                        candidate.logical_interaction_start_time,
                    )
                    continue
                slack_to_logical = (
                    candidate.logical_interaction_start_time - physical_earliest_start
                )
                # 시작 시점이 logical start보다 얼마나 이른지/늦은지 구분하는 로그
                if slack_to_logical > 0:
                    log.debug(
                        f"[_get_urgent_critical_candidates] monitoring horizon inside: {slack_to_logical}"
                    )
                else:
                    log.debug(
                        f"[_get_urgent_critical_candidates] 늦어서 작업을 함: {slack_to_logical}"
                    )
                # Update actual interaction start time
                # We start as soon as physically possible (ASAP)
                candidate.actual_interaction_start_time = physical_earliest_start

                log.debug(
                    f"Found URGENT CRITICAL candidate: {candidate.subtask.name} "
                    f"(Physical: {physical_earliest_start:.2f}, Logical: {candidate.logical_interaction_start_time:.2f}, Horizon: {MONITORING_DURATION:.2f})"
                )
                urgent_list.append(candidate)

        # [Added 251215] Check blocked urgent tasks and prioritize predecessors
        feasible_map = {c.subtask.name: c for c in feasible_candidates}
        constraints = curr_node.state.constraints
        visited = set()

        def find_feasible_ancestor(target_name: str) -> None:
            """Recursively trace predecessors to find feasible ancestors."""
            if target_name in visited:
                return
            visited.add(target_name)

            if not constraints.has_node(target_name):
                return

            preds = list(constraints.predecessors(target_name))
            for pred_name in preds:
                if pred_name in feasible_map:
                    pred_cand = feasible_map[pred_name]
                    if pred_cand not in urgent_list:
                        log.debug(
                            f"Prioritizing feasible ancestor '{pred_name}' to unblock urgent task chain targeting '{candidate.subtask.name}'."
                        )
                        urgent_list.append(pred_cand)
                else:
                    # Recursive search for ancestors
                    find_feasible_ancestor(pred_name)

        for candidate in not_yet_candidates:
            # [TODO] candidate가 logical start time이 없으면 무시해야 함
            if (
                not candidate.is_critical
                or candidate.subtask.decomposed
                or candidate.logical_interaction_start_time is None
            ):
                continue

            incoming_slots = self.constraint_handler.get_time_slots(
                candidate.subtask.name, curr_node.state.constraints, "in"
            )
            critical_slots = [s for s in incoming_slots if s.is_critical]

            if critical_slots:
                target_slot = max(critical_slots, key=lambda s: s.interval)
                critical_start_sub_name = target_slot.related_subtask_name
                critical_interval_duration = target_slot.interval

                # 선행 작업 완료 시간 조회
                pred_entry = next(
                    (
                        ce
                        for ce in curr_node.state.completed_entries
                        if ce.subtask.name == critical_start_sub_name
                    ),
                    None,
                )
                if pred_entry:
                    critical_start_sub_end_time = pred_entry.schedule_end_time

                    logical_start = (
                        critical_start_sub_end_time + critical_interval_duration
                    )
                    physical_start = (
                        curr_node.state.current_time
                        + candidate.estimated_first_nav_duration
                    )

                    if (
                        logical_start - physical_start
                    ) <= (MONITORING_DURATION + EPSILON):
                        # Urgent but blocked! Find feasible predecessors recursively.
                        log.debug(
                            f"Found BLOCKED URGENT task: {candidate.subtask.name} "
                            f"(Physical: {physical_start:.2f}, Logical: {logical_start:.2f}, Horizon: {MONITORING_DURATION:.2f}). Tracing ancestors."
                        )

                        len_before = len(urgent_list)
                        find_feasible_ancestor(candidate.subtask.name)

                        if len(urgent_list) == len_before:
                            if self._can_candidate_start_interaction_now(
                                curr_node, candidate
                            ):
                                log.debug(
                                    f"No feasible ancestors found for {candidate.subtask.name}. "
                                    f"Adding the task itself as it is time-ready/urgent."
                                )
                                candidate.actual_interaction_start_time = physical_start
                                urgent_list.append(candidate)
                            else:
                                log.debug(
                                    "Blocked urgent task '%s' is inside the monitoring horizon but still early "
                                    "(Physical: %.2f, Logical: %.2f). Leaving it to blocked wait/prenav expansion.",
                                    candidate.subtask.name,
                                    physical_start,
                                    logical_start,
                                )

        return urgent_list

    def _extract_monitoring_target(self, candidate: Candidate) -> Optional[str]:
        if (
            candidate.subtask.execution
            and candidate.subtask.execution.primitive_actions
        ):
            # Typically, the target of the first action is what we monitor.
            return candidate.subtask.execution.primitive_actions[0].split()[1]
        return None

    @staticmethod
    def _get_monitoring_target_object_from_subtask(
        subtask: Subtask,
    ) -> Optional[str]:
        """Return the raw target object id used for monitoring one critical end."""

        primitive_actions = (
            subtask.execution.primitive_actions if subtask.execution else None
        )
        if not primitive_actions:
            return None
        first_action_parts = primitive_actions[0].split()
        if len(first_action_parts) < 2:
            return None
        return first_action_parts[1]

    def _resolve_effective_monitoring_budget(self) -> int | None:
        """Return the active per-critical-interval monitoring cap."""

        if self.max_monitoring_per_critical_interval is None:
            return None
        if int(self.max_monitoring_per_critical_interval) < 0:
            return None
        return int(self.max_monitoring_per_critical_interval)

    def _count_monitoring_events_for_interval(
        self,
        curr_state: SchedulerState,
        *,
        critical_start_sub_end_time: float,
        critical_end_sub_name: str,
    ) -> int:
        """Return how many monitors have already executed for one interval."""

        monitor_count = 0
        for completed_entry in curr_state.completed_entries:
            if completed_entry.subtask.subtask_type != "Monitor":
                continue
            if completed_entry.schedule_start_time < critical_start_sub_end_time:
                continue
            try:
                monitored_target_name = extract_monitoring_target_name(
                    completed_entry.subtask.name
                )
            except ValueError:
                continue
            if monitored_target_name == critical_end_sub_name:
                monitor_count += 1
        return monitor_count

    def _monitoring_budget_reached(
        self,
        curr_state: SchedulerState,
        *,
        critical_start_sub_end_time: float,
        critical_end_sub_name: str,
    ) -> bool:
        """Return whether monitoring is exhausted for the current interval."""

        effective_budget = self._resolve_effective_monitoring_budget()
        if effective_budget is None:
            return False
        completed_monitors = self._count_monitoring_events_for_interval(
            curr_state,
            critical_start_sub_end_time=critical_start_sub_end_time,
            critical_end_sub_name=critical_end_sub_name,
        )
        return completed_monitors >= effective_budget

    @staticmethod
    def _resolve_monitoring_target_start_time(
        candidate: Optional[Candidate],
        *,
        critical_start_sub_end_time: float,
        critical_interval_duration: float,
    ) -> float:
        """Resolve the current target interaction start used after monitoring."""

        if candidate is not None:
            target_start_time = (
                candidate.actual_interaction_start_time
                if candidate.actual_interaction_start_time is not None
                else candidate.logical_interaction_start_time
            )
            if target_start_time is not None and target_start_time != float("inf"):
                return float(target_start_time)
        return float(critical_start_sub_end_time + critical_interval_duration)

    def _estimate_candidate_navigation_duration(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> float:
        """Estimate how much navigation remains before the candidate can interact."""

        primitive_actions = (
            candidate.subtask.execution.primitive_actions
            if candidate.subtask.execution
            else None
        )
        if not primitive_actions:
            return 0.0
        first_action = primitive_actions[0]
        if not first_action.startswith("NAVIGATE_TO"):
            return float(candidate.estimated_first_nav_duration or 0.0)
        target_obj_id = first_action.split()[1]
        nav_time = self._estimate_navigation_duration(
            curr_node,
            target_obj_id,
            candidate_name=candidate.subtask.name,
        )
        return 0.0 if nav_time is None else float(nav_time)

    def _estimate_subtask_navigation_buffer(
        self,
        curr_node: SimulationNode,
        subtask_name: str,
        *,
        feasible_candidates: List[Candidate] | None = None,
        not_yet_candidates: List[Candidate] | None = None,
    ) -> float:
        """Estimate navigation still required before a subtask can interact."""

        all_candidates = list(feasible_candidates or []) + list(not_yet_candidates or [])
        for queued_candidate in all_candidates:
            if queued_candidate.subtask.name == subtask_name:
                return self._estimate_candidate_navigation_duration(
                    curr_node, queued_candidate
                )

        for remaining_subtask in curr_node.state.remaining_subtasks:
            if remaining_subtask.name != subtask_name:
                continue
            primitive_actions = (
                remaining_subtask.execution.primitive_actions
                if remaining_subtask.execution
                else None
            )
            if not primitive_actions:
                return 0.0
            full_action_info = self.action_handler.get_actions_info(
                curr_node, primitive_actions
            )
            if full_action_info is None or not full_action_info.success:
                return 0.0
            return float(full_action_info.first_nav_duration or 0.0)
        return 0.0

    def _should_explicitly_prenavigate(self, candidate: Candidate) -> bool:
        """Return whether a non-monitoring candidate should emit an explicit NAV step."""

        primitive_actions = (
            candidate.subtask.execution.primitive_actions
            if candidate.subtask.execution
            else None
        )
        if not primitive_actions or len(primitive_actions) <= 1:
            return False
        return primitive_actions[0].startswith("NAVIGATE_TO") and (
            float(candidate.estimated_first_nav_duration or 0.0) > EPSILON
        )

    def _get_candidate_target_start_time(
        self,
        candidate: Candidate,
    ) -> Optional[float]:
        """Return the earliest target interaction time for a candidate."""

        if candidate.actual_interaction_start_time is not None:
            return float(candidate.actual_interaction_start_time)
        if candidate.logical_interaction_start_time is not None:
            return float(candidate.logical_interaction_start_time)
        return None

    def _get_reserved_prenavigation_candidate_name(
        self,
        curr_node: SimulationNode,
    ) -> Optional[str]:
        """Return the blocked candidate reserved by an earlier pre-navigation step."""

        for remaining_subtask in curr_node.state.remaining_subtasks:
            if getattr(remaining_subtask, "pre_navigation_reserved", False):
                return remaining_subtask.name
        return None

    @staticmethod
    def _is_productive_candidate(candidate: Candidate) -> bool:
        """Return whether a candidate is real work rather than wait/nav/monitor."""

        subtask_type = (candidate.subtask.subtask_type or "").strip()
        return subtask_type not in {"WAIT", "NAVIGATE", "Monitor", "MONITORING"}

    @staticmethod
    def _find_candidate_by_name(
        candidates: List[Candidate],
        subtask_name: str,
    ) -> Optional[Candidate]:
        """Return the candidate matching ``subtask_name`` if present."""

        return next(
            (candidate for candidate in candidates if candidate.subtask.name == subtask_name),
            None,
        )

    def _reserved_prenavigation_preserves_target(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        reserved_candidate: Candidate,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> bool:
        """Return whether one feasible step keeps the reserved pre-nav target intact.

        Early pre-navigation should keep the blocked frontier available, but it
        should not freeze the whole rollout when unrelated productive work can
        still finish before the reserved interaction time.
        """

        if not self._is_productive_candidate(candidate):
            return False

        reserved_target_time = self._get_candidate_target_start_time(reserved_candidate)
        if (
            reserved_target_time is None
            or reserved_target_time == float("inf")
            or curr_node.state.current_time >= (reserved_target_time - EPSILON)
        ):
            return False

        simulated_child = self._expand_single_subtask(
            curr_node,
            copy.deepcopy(candidate),
            not_yet_candidates,
            feasible_candidates,
        )
        if simulated_child is None:
            return False
        if simulated_child.state.current_time > (reserved_target_time + EPSILON):
            return False

        child_feasible, child_not_yet = self.constraint_handler.get_feasible_candidates(
            simulated_child
        )
        child_reserved_candidate = self._find_candidate_by_name(
            child_feasible + child_not_yet,
            reserved_candidate.subtask.name,
        )
        if child_reserved_candidate is None:
            return False

        updated_target_time = self._get_candidate_target_start_time(
            child_reserved_candidate
        )
        if updated_target_time is None or updated_target_time == float("inf"):
            return False

        preserves_target = updated_target_time <= (reserved_target_time + EPSILON)
        if preserves_target:
            log.debug(
                "[_reserved_prenavigation_preserves_target] '%s' keeps reserved target '%s' on time "
                "(target %.2f -> %.2f).",
                candidate.subtask.name,
                reserved_candidate.subtask.name,
                reserved_target_time,
                updated_target_time,
            )
        return preserves_target

    def _apply_reserved_prenavigation_filter(
        self,
        curr_node: SimulationNode,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> tuple[List[Candidate], List[Candidate]]:
        """Filter candidates when a prior pre-navigation reserved one blocked task.

        The reserved target remains the only blocked frontier candidate, but we
        still allow productive feasible work that demonstrably preserves that
        reserved interaction frontier.
        """

        reserved_candidate_name = self._get_reserved_prenavigation_candidate_name(
            curr_node
        )
        if reserved_candidate_name is None:
            return feasible_candidates, not_yet_candidates

        reserved_candidate = self._find_candidate_by_name(
            feasible_candidates + not_yet_candidates,
            reserved_candidate_name,
        )
        filtered_not_yet = [
            candidate
            for candidate in not_yet_candidates
            if candidate.subtask.name == reserved_candidate_name
        ]

        if reserved_candidate is None:
            log.debug(
                "[_apply_reserved_prenavigation_filter] reserved target '%s' not found among candidates. "
                "Falling back to strict target-only filter.",
                reserved_candidate_name,
            )
            return (
                [
                    candidate
                    for candidate in feasible_candidates
                    if candidate.subtask.name == reserved_candidate_name
                ],
                filtered_not_yet,
            )

        filtered_feasible: List[Candidate] = []
        allowed_filler_names: List[str] = []
        for candidate in feasible_candidates:
            if candidate.subtask.name == reserved_candidate_name:
                filtered_feasible.append(candidate)
                continue
            if self._reserved_prenavigation_preserves_target(
                curr_node,
                candidate,
                reserved_candidate,
                feasible_candidates,
                not_yet_candidates,
            ):
                filtered_feasible.append(candidate)
                allowed_filler_names.append(candidate.subtask.name)

        log.debug(
            "[_apply_reserved_prenavigation_filter] reserved target '%s'; allowed fillers=%s",
            reserved_candidate_name,
            allowed_filler_names,
        )
        return filtered_feasible, filtered_not_yet

    def _has_productive_filler_preserving_blocked_frontier(
        self,
        curr_node: SimulationNode,
        blocked_candidate: Candidate,
        feasible_candidates: List[Candidate],
        not_yet_candidates: List[Candidate],
    ) -> bool:
        """Return whether a feasible productive step dominates early pre-navigation."""

        for candidate in feasible_candidates:
            if self._reserved_prenavigation_preserves_target(
                curr_node,
                candidate,
                blocked_candidate,
                feasible_candidates,
                not_yet_candidates,
            ):
                return True
        return False

    @staticmethod
    def _can_candidate_start_interaction_now(
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> bool:
        """Return whether the candidate can begin interacting now or is already late.

        Dispatch remains anchored on interaction start time, but a small planner
        buffer is allowed so tiny timing-estimation mismatch does not force the
        task to stay blocked.
        """

        if candidate.logical_interaction_start_time is None:
            return True
        physical_earliest_start = (
            curr_node.state.current_time + candidate.estimated_first_nav_duration
        )
        readiness_tolerance = Scheduler._get_interaction_readiness_tolerance()
        return physical_earliest_start >= (
            float(candidate.logical_interaction_start_time)
            - readiness_tolerance
        )

    def _get_blocked_candidate_frontier(
        self,
        not_yet_candidates: List[Candidate],
    ) -> List[Candidate]:
        """Return blocked candidates on the earliest timing frontier."""

        sorted_candidates = sorted(
            not_yet_candidates,
            key=lambda candidate: (
                (
                    self._get_candidate_target_start_time(candidate)
                    if self._get_candidate_target_start_time(candidate) is not None
                    else float("inf")
                ),
                candidate.subtask.name,
            ),
        )
        finite_candidates = [
            candidate
            for candidate in sorted_candidates
            if self._get_candidate_target_start_time(candidate) is not None
            and self._get_candidate_target_start_time(candidate) != float("inf")
        ]
        if not finite_candidates:
            return []

        earliest_target_time = self._get_candidate_target_start_time(
            finite_candidates[0]
        )
        if earliest_target_time is None:
            return []
        return [
            candidate
            for candidate in finite_candidates
            if abs(
                float(self._get_candidate_target_start_time(candidate))
                - earliest_target_time
            )
            <= EPSILON
        ]

    def _build_post_navigation_candidate(
        self,
        candidate: Candidate,
        *,
        reserve_blocked_candidate: bool = False,
    ) -> Candidate:
        """Create the remaining interaction candidate after pre-navigation.

        The original primitive_actions are preserved intact so that the subtask
        object recorded in CompletedEntry is consistent with EDF/CPM baselines.
        Re-simulation from the already-navigated position yields nav ≈ 0, so
        timing is unaffected.
        """

        remaining_subtask = copy.deepcopy(candidate.subtask)
        if reserve_blocked_candidate:
            setattr(remaining_subtask, "pre_navigation_reserved", True)
        return Candidate(
            subtask=remaining_subtask,
            is_critical=candidate.is_critical,
            actual_interaction_start_time=candidate.actual_interaction_start_time,
            logical_interaction_start_time=candidate.logical_interaction_start_time,
            estimated_first_nav_duration=0.0,
            scheduling_due=candidate.scheduling_due,
            critical_context=candidate.critical_context,
        )

    def _expand_prenavigation_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] | None = None,
        reserve_blocked_candidate: bool = False,
    ) -> Optional[SimulationNode]:
        """Execute only the first navigation action as an explicit step."""

        primitive_actions = (
            candidate.subtask.execution.primitive_actions
            if candidate.subtask.execution
            else None
        )
        if not primitive_actions or len(primitive_actions) <= 1:
            return None

        first_action = primitive_actions[0]
        if not first_action.startswith("NAVIGATE_TO"):
            return None

        navigation_info = self.action_handler.get_actions_info(
            curr_node, [first_action]
        )
        if navigation_info is None or not navigation_info.success:
            log.warning(
                "Action simulation failed for explicit pre-navigation of '%s'.",
                candidate.subtask.name,
            )
            return None

        nav_target = first_action.split()[1]
        nav_duration = float(navigation_info.cumulative_time)
        nav_subtask = Subtask(
            task_name=candidate.subtask.task_name,
            name=f"NAVIGATE_TO_{nav_target}",
            duration=Duration(
                interval=nav_duration,
                type="NAVIGATE",
                total_time=nav_duration,
            ),
            repetition=1,
            subtask_type="NAVIGATE",
            execution=Execution(objects={}, primitive_actions=[first_action]),
            temporal_constraints=[],
            decomposed=True,
        )
        nav_entry = CompletedEntry(
            subtask=nav_subtask,
            schedule_start_time=curr_node.state.current_time,
            schedule_end_time=curr_node.state.current_time + nav_duration,
            schedule_nav_time=nav_duration,
            execution_status=bool(navigation_info.success),
        )

        post_nav_candidate = self._build_post_navigation_candidate(
            candidate,
            reserve_blocked_candidate=reserve_blocked_candidate,
        )
        new_remaining_subtasks: List[Subtask] = []
        for remaining_subtask in curr_node.state.remaining_subtasks:
            if remaining_subtask.name == candidate.subtask.name:
                new_remaining_subtasks.append(post_nav_candidate.subtask)
            else:
                new_remaining_subtasks.append(remaining_subtask)

        new_state = SchedulerState(
            subtask=nav_subtask,
            completed_entries=curr_node.state.completed_entries + [nav_entry],
            remaining_subtasks=new_remaining_subtasks,
            constraints=curr_node.state.constraints,
            current_time=curr_node.state.current_time + nav_duration,
            scene_positions=navigation_info.scene_positions,
            held_object=(
                navigation_info.held_object
                if navigation_info.held_object is not None
                else curr_node.state.held_object
            ),
        )

        temp_node = SimulationNode(
            parent_node=curr_node,
            heuristic_cost=0.0,
            depth=curr_node.depth + 1,
            tie_breaker=curr_node.tie_breaker,
            state=new_state,
            risk_level=curr_node.risk_level,
        )
        all_candidates = list(feasible_candidates or []) + list(not_yet_candidates)
        updated_candidates: List[Candidate] = []
        replaced = False
        for queued_candidate in all_candidates:
            if queued_candidate.subtask.name == candidate.subtask.name:
                updated_candidates.append(post_nav_candidate)
                replaced = True
            else:
                updated_candidates.append(queued_candidate)
        if not replaced:
            updated_candidates.append(post_nav_candidate)

        step_risk, total_heuristic_cost = self.cost_calculator.calc_heuristic(
            temp_node,
            post_nav_candidate,
            updated_candidates,
        )
        new_cost = new_state.current_time + total_heuristic_cost
        new_risk = max(curr_node.risk_level, step_risk)
        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_node.depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
            risk_level=new_risk,
        )

    def _should_expand_blocked_prenavigation(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
    ) -> bool:
        """Return whether a blocked candidate should branch into early NAV."""

        if not self._should_explicitly_prenavigate(candidate):
            return False
        target_start_time = self._get_candidate_target_start_time(candidate)
        if target_start_time is None or target_start_time == float("inf"):
            return False
        nav_duration = self._estimate_candidate_navigation_duration(
            curr_node, candidate
        )
        if nav_duration <= EPSILON:
            return False
        if (curr_node.state.current_time + nav_duration) >= (
            target_start_time - EPSILON
        ):
            return False
        if constants.MONITORING_ENABLED:
            need_monitor, _ = self._should_split_with_monitoring(curr_node, candidate)
            if need_monitor:
                return False
        return True

    def _expand_blocked_prenavigation(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] | None = None,
    ) -> Optional[SimulationNode]:
        """Expand a blocked candidate by navigating early to its target."""

        if not self._should_expand_blocked_prenavigation(curr_node, candidate):
            return None
        return self._expand_prenavigation_wo_monitoring(
            curr_node,
            candidate,
            not_yet_candidates,
            feasible_candidates,
            reserve_blocked_candidate=True,
        )

    @staticmethod
    def _get_interaction_readiness_tolerance() -> float:
        """Return the scheduler-side grace used for critical-start readiness."""

        return max(
            constants.RISK_GRACE_SECONDS,
            INTERACTION_READINESS_NUMERIC_EPSILON,
        )

    @staticmethod
    def _normalize_monitoring_object_name(
        raw_object_name: Optional[str],
    ) -> Optional[str]:
        """Normalize an object identifier to its object type.

        Args:
            raw_object_name: Raw object identifier or type string.

        Returns:
            Object type without instance suffix.
        """

        if not raw_object_name:
            return None
        return raw_object_name.split("|")[0]

    def _estimate_navigation_duration(
        self,
        curr_node: SimulationNode,
        target_obj_id: str,
        *,
        candidate_name: str,
    ) -> Optional[float]:
        """Estimate navigation time for a single target object.

        Args:
            curr_node: Current simulation node used as the starting state.
            target_obj_id: Target object identifier for navigation.
            candidate_name: Human-readable subtask name for diagnostics.

        Returns:
            Navigation duration when simulation succeeds, otherwise ``None``.
        """

        navigation_info = self.action_handler.get_actions_info(
            curr_node, [f"NAVIGATE_TO {target_obj_id}"]
        )
        if navigation_info is None or not navigation_info.success:
            log.warning(
                "Navigation simulation failed while expanding '%s' toward '%s'.",
                candidate_name,
                target_obj_id,
            )
            return None
        return navigation_info.action_duration

    def _compute_monitoring_trigger_time(
        self,
        *,
        raw_object_name: Optional[str],
        critical_start_sub_end_time: float,
        mean_duration: float,
        variance: float,
    ) -> float:
        """Delegate monitoring timing to the configured backend policy.

        Args:
            raw_object_name: Raw object identifier associated with the interval.
            critical_start_sub_end_time: End time of the critical start subtask.
            mean_duration: Current expected interval duration.
            variance: Current interval variance.

        Returns:
            Absolute trigger time for inserting monitoring.
        """

        object_name = self._normalize_monitoring_object_name(raw_object_name)
        trigger_cache_key = (
            self.monitoring_policy.method,
            object_name,
            critical_start_sub_end_time,
            mean_duration,
            variance,
        )
        if self._search_cache is not None:
            cached_trigger = self._search_cache.monitoring_triggers.get(
                trigger_cache_key
            )
            if cached_trigger is not None:
                self._search_cache.trigger_cache_hits += 1
                return cached_trigger

        trigger_time = self.monitoring_policy.compute_trigger_time(
            MonitoringTriggerContext(
                object_name=object_name,
                critical_start_end_time=critical_start_sub_end_time,
                mean_duration=mean_duration,
                variance=variance,
            )
        )
        log.debug(
            "Monitoring trigger (%s): object=%s, mean=%.2f, variance=%.2f -> %.2f",
            self.monitoring_policy.method,
            object_name,
            mean_duration,
            variance,
            trigger_time,
        )
        if self._search_cache is not None:
            self._search_cache.trigger_cache_misses += 1
            self._search_cache.monitoring_triggers[trigger_cache_key] = trigger_time
        return trigger_time

    @staticmethod
    def _compute_critical_deadline(
        *,
        critical_start_sub_end_time: float,
        critical_interval_duration: float,
    ) -> float:
        """Return the absolute deadline of one critical interval."""

        return critical_start_sub_end_time + critical_interval_duration

    def _refresh_node_heuristic_cost(
        self,
        node: SimulationNode,
        *,
        context: str,
    ) -> SimulationNode:
        """Recompute ``g+h`` after a branch rewrites the child state in-place."""

        refreshed_remaining_cost = self.cost_calculator.estimate_remaining_work_from_state(
            node
        )
        refreshed_total_cost = node.state.current_time + refreshed_remaining_cost
        log.debug(
            "[_refresh_node_heuristic_cost] %s: refreshed total cost %.2f = current_time %.2f + remaining %.2f (previous %.2f)",
            context,
            refreshed_total_cost,
            node.state.current_time,
            refreshed_remaining_cost,
            node.heuristic_cost,
        )
        return node._replace(heuristic_cost=refreshed_total_cost)

    def _monitoring_can_finish_before_deadline(
        self,
        *,
        monitoring_start_time: float,
        critical_start_sub_end_time: float,
        critical_interval_duration: float,
        post_monitor_buffer: float = 0.0,
    ) -> bool:
        """Return whether monitoring can complete before the critical deadline.

        Args:
            monitoring_start_time: Planned absolute monitoring start time.
            critical_start_sub_end_time: Absolute end time of the critical start.
            critical_interval_duration: Allowed duration until the critical end.
            post_monitor_buffer: Extra time that must remain after monitoring
                (for example navigation before the critical-end interaction).
        """

        critical_deadline = self._compute_critical_deadline(
            critical_start_sub_end_time=critical_start_sub_end_time,
            critical_interval_duration=critical_interval_duration,
        )
        required_completion_time = (
            monitoring_start_time
            + MONITORING_DURATION
            + max(0.0, float(post_monitor_buffer))
        )
        feasible = required_completion_time <= (critical_deadline + EPSILON)
        if not feasible:
            log.debug(
                "[_monitoring_can_finish_before_deadline] infeasible: "
                "monitor_start=%.2f monitor_end+buffer=%.2f deadline=%.2f buffer=%.2f",
                monitoring_start_time,
                required_completion_time,
                critical_deadline,
                float(post_monitor_buffer),
            )
        return feasible

    def _is_monitoring_step_admissible(
        self,
        pre_monitor_node: SimulationNode,
        *,
        monitor_start_time: float,
        monitor_finish_time: float,
        protected_target_name: Optional[str],
    ) -> bool:
        """Return whether a monitoring prefix preserves active critical-end slack.

        The admissibility gate reasons only up to ``monitor_finish_time`` using the
        current belief and current constraint graph. It does not speculate about
        posterior updates after the monitoring step.
        """

        remaining_names = {
            subtask.name for subtask in pre_monitor_node.state.remaining_subtasks
        }
        protected_end_names = {
            due.due_related_sub_name
            for _, due in self._get_active_monitoring_intervals(pre_monitor_node)
            if due.due_related_sub_name in remaining_names
        }
        if protected_target_name and protected_target_name in remaining_names:
            protected_end_names.add(protected_target_name)
        if not protected_end_names:
            return True

        projected_state = pre_monitor_node.state._replace(current_time=monitor_finish_time)
        projected_node = pre_monitor_node._replace(state=projected_state)
        feasible_candidates, not_yet_candidates = (
            self.constraint_handler.get_feasible_candidates(projected_node)
        )
        projected_candidates = {
            candidate.subtask.name: candidate
            for candidate in feasible_candidates + not_yet_candidates
        }
        readiness_tolerance = self._get_interaction_readiness_tolerance()

        for target_name in sorted(protected_end_names):
            projected_candidate = projected_candidates.get(target_name)
            if projected_candidate is None:
                log.debug(
                    "[_is_monitoring_step_admissible] could not reconstruct projected readiness for protected critical end '%s' "
                    "(monitor target '%s'). Skipping gate check for this interval.",
                    target_name,
                    protected_target_name,
                )
                continue

            logical_start = projected_candidate.logical_interaction_start_time
            actual_start = projected_candidate.actual_interaction_start_time
            if logical_start is None or actual_start is None:
                log.debug(
                    "[_is_monitoring_step_admissible] projected candidate '%s' has unresolved readiness "
                    "(logical=%s, actual=%s) after monitoring '%s'. Skipping gate check for this interval.",
                    target_name,
                    logical_start,
                    actual_start,
                    protected_target_name,
                )
                continue

            lateness = float(actual_start) - float(logical_start)
            if lateness > (readiness_tolerance + EPSILON):
                protection_label = (
                    "self-target"
                    if target_name == protected_target_name
                    else "competing-target"
                )
                log.debug(
                    "[_is_monitoring_step_admissible] rejected monitoring for '%s': %s critical end '%s' would be late by %.2fs "
                    "(logical=%.2f, earliest=%.2f, tol=%.2f, monitor_start=%.2f, monitor_finish=%.2f).",
                    protected_target_name,
                    protection_label,
                    target_name,
                    lateness,
                    float(logical_start),
                    float(actual_start),
                    readiness_tolerance,
                    monitor_start_time,
                    monitor_finish_time,
                )
                return False

        return True

    # ==========================================================================
    #           SUBTASK EXPANSION: Single Subtask or Wait
    # ==========================================================================
    def _expand_single_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """
        Expands the given candidate subtask by deciding whether to split it
        into a monitoring subtask or not.

        Args:
            curr_node (SimulationNode): The current node in the search tree.
            candidate (Candidate): The subtask candidate to expand.

        Returns:
            Optional[SimulationNode]: The resulting child node if successful,
            otherwise None.
        """
        log.debug(
            f"[_expand_single_subtask] Checking expansion for subtask: {candidate.subtask.name}."
        )

        # 모니터링 필요?
        need_monitor, due_info = self._should_split_with_monitoring(
            curr_node, candidate
        )
        if need_monitor and constants.MONITORING_ENABLED:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} requires monitoring-based splitting."
            )
            # 왜 덮어씌우지?
            candidate.scheduling_due = due_info
            return self._expand_subtask_with_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        else:
            log.debug(
                f"[_expand_single_subtask] Subtask {candidate.subtask.name} will be executed without monitoring."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

    def _expand_single_wait(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """
        Expands the wait subtask by deciding whether to split it
        into a monitoring subtask or not.

        Args:
            curr_node (SimulationNode): The current node in the search tree.
            candidate (Candidate): The subtask candidate will be expand.

        Returns:
            Optional[SimulationNode]: The resulting child node if successful,
            otherwise None.
        """

        nav_time = self._estimate_candidate_navigation_duration(curr_node, candidate)

        # Check if monitoring is needed before waiting, using the same Bayesian logic as standard subtasks.
        need_monitor, due_info = self._should_split_with_monitoring(
            curr_node, candidate
        )

        if need_monitor and constants.MONITORING_ENABLED:
            return self._expand_wait_with_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_time,
                feasible_candidates=feasible_candidates,
            )
        else:
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_time,
                feasible_candidates=feasible_candidates,
            )

    # ======================
    # Helper: 모니터링 필요한지
    # ======================
    def _should_split_with_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ) -> tuple[bool, Optional[SchedulingDue]]:
        """
        Determines if a task should be split for monitoring based on three rules.
        Args:
            curr_node: The current simulation node.
            candidate: The candidate subtask to evaluate.

        Returns:
            True if the candidate should be split for monitoring, False otherwise.
        """

        # curr_node의 subtask가 wait였고, wait의 대상이 candidate라면, monitoring 필요 없음
        if (
            curr_node.state.subtask
            and curr_node.state.subtask.subtask_type == "WAIT"
            and curr_node.state.subtask.name == f"Wait for {candidate.subtask.name}"
        ):
            log.debug(
                f"[_should_split_with_monitoring] Just finished waiting for {candidate.subtask.name}. Skip monitoring."
            )
            return False, None

        # Rule 1: Don't re-split tasks.
        if candidate.subtask.decomposed:
            log.debug(
                f"[_should_split_with_monitoring] Subtask {candidate.subtask.name} is already handled/decomposed. No split."
            )
            return False, None

        # Rule 2: Don't split if an immediate critical predecessor exists.
        in_slots = self.constraint_handler.get_time_slots(
            candidate.subtask.name, curr_node.state.constraints, direction="in"
        )
        for slot in in_slots:
            if slot.is_critical and slot.interval < EPSILON:
                log.debug(
                    f"[_should_split_with_monitoring] Subtask {candidate.subtask.name} has an immediate critical predecessor ({slot.related_subtask_name}). Monitoring is disallowed."
                )
                return False, None

        # Rule 3: Split only if an active critical interval exists.
        active_intervals = self._get_active_monitoring_intervals(curr_node)

        if not active_intervals:
            log.debug(
                f"[_should_split_with_monitoring] No active critical intervals found. No monitoring for {candidate.subtask.name}."
            )
            return False, None

        # If an active interval exists, a split is necessary.
        # Assign the most urgent due date based on VARIANCE (Uncertainty).
        # We prioritize the interval with the HIGHEST variance to reduce uncertainty first.
        # Tie-breaker: If variances are equal, prioritize the one with the EARLIEST due date (smallest due_date).
        urgent_var, urgent_due = max(
            active_intervals, key=lambda item: (item[0], -item[1].due_date)
        )

        # [Safety Latch 251215]
        # We want to monitor the high-variance task, BUT if the candidate already has a TIGHTER deadline,
        # we cannot afford to go monitoring something else that is less urgent.

        final_due = urgent_due
        # if final_due.due_related_sub_name == candidate.subtask.name:
        #     log.debug(
        #         f"[_should_split_with_monitoring] Final due related subtask is the same as the candidate. Skip monitoring."
        #     )
        #     return False, None

        candidate_due = get_candidate_effective_due(candidate)

        # critical end subtask가 아닐 때.
        if has_finite_due(candidate_due) and candidate_due.due_date < urgent_due.due_date:
            # The candidate is MORE URGENT than the monitoring target.
            # Check if there is an active interval for the urgent task itself.
            urgent_interval_pair = next(
                (
                    item
                    for item in active_intervals
                    if item[1].due_related_sub_name
                    == candidate_due.due_related_sub_name
                ),
                None,
            )

            if urgent_interval_pair:
                # If the urgent task itself can be monitored, do that instead.
                final_due = urgent_interval_pair[1]
                urgent_var = urgent_interval_pair[0]
                log.debug(
                    f"[_should_split_with_monitoring] Overriding high variance target with URGENT target '{final_due.due_related_sub_name}' "
                    f"(due: {final_due.due_date:.2f})."
                )
            else:
                # The urgent task is not monitorable (or not in active list).
                # Skipping monitoring completely to focus on the deadline.
                log.debug(
                    f"[_should_split_with_monitoring] Skipping monitoring. Candidate has urgent deadline ({candidate_due.due_date:.2f}) "
                    f"which is tighter than high variance target ({urgent_due.due_date:.2f})."
                )
                return False, None

        candidate.scheduling_due = final_due
        log.debug(
            f"[_should_split_with_monitoring] Active interval found targeting '{final_due.due_related_sub_name}' "
            f"(due: {final_due.due_date:.2f}, var: {urgent_var:.2f})."
        )

        return True, final_due

    # -----------------------------------------------------
    # (A) 서브태스크 (no monitoring)
    # -----------------------------------------------------
    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        """
        Expands a non-monitoring subtask. The subtask is executed fully at once.
        Navigation (if any, as first_nav_duration) + Interaction are performed.
        """
        log.debug(f"[_expand_subtask_wo_monitoring] {candidate.subtask.name}")
        curr_state = curr_node.state

        curr_depth = curr_node.depth
        original_task_name = candidate.subtask.name

        planned_nav_start_time = curr_state.current_time

        sub_actions = candidate.subtask.execution.primitive_actions

        if not sub_actions:
            return None

        try:
            executed_action_info: Optional[ActionResult] = (
                self.action_handler.get_actions_info(curr_node, sub_actions)
            )
            if executed_action_info is None or not executed_action_info.success:
                log.warning(
                    f"Action simulation failed for {original_task_name}. Cannot expand."
                )
                return None
        except ValueError as e:
            log.error(f"Error during action simulation for {original_task_name}: {e}")
            return None

        total_subtask_duration_from_sim = executed_action_info.cumulative_time
        planned_subtask_completion_time = (
            planned_nav_start_time + total_subtask_duration_from_sim
        )

        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.total_time = total_subtask_duration_from_sim

        sim_success_status = (
            executed_action_info.success if executed_action_info else False
        )

        completed_entry = CompletedEntry(
            subtask=copied_sub,
            schedule_start_time=planned_nav_start_time,
            schedule_end_time=planned_subtask_completion_time,
            schedule_nav_time=executed_action_info.first_nav_duration,
            execution_status=sim_success_status,
        )
        new_completed = curr_state.completed_entries + [completed_entry]
        new_remain = [
            r for r in curr_state.remaining_subtasks if r.name != original_task_name
        ]

        new_scene_positions = executed_action_info.scene_positions
        new_held_obj = executed_action_info.held_object

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_entries=new_completed,
            remaining_subtasks=new_remain,
            constraints=curr_state.constraints,
            current_time=planned_subtask_completion_time,
            scene_positions=new_scene_positions,
            held_object=new_held_obj,
        )

        # Global Risk Check을 위해 feasible_candidates도 포함하여 전달
        all_candidates = not_yet_candidates
        if feasible_candidates:
            all_candidates = feasible_candidates + not_yet_candidates

        step_risk, total_heuristic_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, all_candidates
        )

        # [Modified] HeuristicManager returns h(n) (Remaining Work + Debt).
        # We add planned_subtask_completion_time (g(n)) here to get the total cost f(n) = g(n) + h(n).
        new_cost = planned_subtask_completion_time + total_heuristic_cost

        # Accumulate max risk level along the path
        new_risk = max(curr_node.risk_level, step_risk)

        log.info(
            f"[_expand_subtask_wo_monitoring] {candidate.subtask.name}: current_time({planned_subtask_completion_time:.2f}) = from_time({curr_state.current_time:.2f}) + total_subtask_duration({total_subtask_duration_from_sim:.2f})"
        )
        log.info(
            f"cost({new_cost:.2f}) = planned_subtask_completion_time({planned_subtask_completion_time:.2f}) + total_heuristic_cost({total_heuristic_cost:.2f})\n"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
            risk_level=new_risk,
        )

    def _expand_explicit_triggered_monitoring_obligation(
        self,
        curr_node: SimulationNode,
        obligation: TriggeredMonitoringObligation,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] | None = None,
    ) -> Optional[SimulationNode]:
        """Expand a standalone monitoring branch for a trigger-matured interval."""

        target_candidate = obligation.target_candidate
        if target_candidate is None:
            remaining_subtask = next(
                (
                    subtask
                    for subtask in curr_node.state.remaining_subtasks
                    if subtask.name == obligation.critical_end_sub_name
                ),
                None,
            )
            if remaining_subtask is None:
                log.debug(
                    "[_expand_explicit_triggered_monitoring_obligation] target '%s' disappeared before expansion.",
                    obligation.critical_end_sub_name,
                )
                return None
            target_candidate = Candidate(
                subtask=remaining_subtask,
                is_critical=True,
                logical_interaction_start_time=(
                    obligation.critical_start_sub_end_time
                    + obligation.critical_interval_duration
                ),
                actual_interaction_start_time=(
                    obligation.critical_start_sub_end_time
                    + obligation.critical_interval_duration
                ),
            )

        target_start_time = self._resolve_monitoring_target_start_time(
            target_candidate,
            critical_start_sub_end_time=obligation.critical_start_sub_end_time,
            critical_interval_duration=obligation.critical_interval_duration,
        )
        critical_end_nav_buffer = self._estimate_subtask_navigation_buffer(
            curr_node,
            obligation.critical_end_sub_name,
            feasible_candidates=feasible_candidates,
            not_yet_candidates=not_yet_candidates,
        )
        predecessor_name = (
            curr_node.state.subtask.name
            if curr_node.state.subtask is not None
            else obligation.critical_start_sub_name
        )
        log.debug(
            "[_expand_explicit_triggered_monitoring_obligation] inserting explicit monitor for '%s' "
            "(trigger=%.2f current=%.2f ready_now=%s).",
            obligation.critical_end_sub_name,
            obligation.trigger_time,
            curr_node.state.current_time,
            obligation.ready_now,
        )
        return self._insert_monitoring_step(
            curr_node=curr_node,
            candidate=target_candidate,
            monitoring_target_obj=obligation.monitoring_target_obj,
            predecessor_name=predecessor_name,
            target_actual_start_time=target_start_time,
            not_yet_candidates=not_yet_candidates,
            critical_start_sub_name=obligation.critical_start_sub_name,
            critical_start_sub_end_time=obligation.critical_start_sub_end_time,
            critical_end_sub_name=obligation.critical_end_sub_name,
            critical_interval_duration=obligation.critical_interval_duration,
            monitoring_target_sub_name=obligation.critical_end_sub_name,
            is_critical_link=True,
            critical_end_post_monitor_buffer=critical_end_nav_buffer,
        )

    def _insert_monitoring_step(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        monitoring_target_obj: Optional[str],
        predecessor_name: str,
        target_actual_start_time: Optional[float],
        not_yet_candidates: List[Candidate],
        *,
        critical_start_sub_name: Optional[str] = None,
        critical_start_sub_end_time: Optional[float] = None,
        critical_end_sub_name: Optional[str] = None,
        critical_interval_duration: Optional[float] = None,
        monitoring_target_sub_name: Optional[str] = None,
        is_critical_link: bool = True,
        critical_end_post_monitor_buffer: float = 0.0,
    ) -> Optional[SimulationNode]:
        """Execute monitoring immediately and update state/constraints for a follow-up `candidate`."""

        if not monitoring_target_obj:
            log.debug(
                "[_insert_monitoring] target_obj is None. Cannot insert monitoring step."
            )
            return None

        if target_actual_start_time is None:
            log.debug(
                "[_insert_monitoring] target_actual_start_time is None. Cannot insert monitoring step."
            )
            return None

        monitor_base_name = (
            monitoring_target_sub_name
            if monitoring_target_sub_name
            else candidate.subtask.name
        )
        monitor_sub = TaskUtil.create_monitoring_subtask(
            name=monitor_base_name, obj=monitoring_target_obj
        )
        monitor_sub.decomposed = True

        monitor_candidate = Candidate(
            subtask=monitor_sub,
            is_critical=True,
            actual_interaction_start_time=curr_node.state.current_time,
            logical_interaction_start_time=curr_node.state.current_time,
        )
        # 모니터링 작업을 수행하고, 그 결과를 모니터링 노드로 반환합니다.
        monitor_node = self._expand_subtask_wo_monitoring(
            curr_node, monitor_candidate, not_yet_candidates
        )
        if monitor_node is None:
            return None

        monitor_state = monitor_node.state
        monitor_start_time = curr_node.state.current_time
        monitor_finish_time = monitor_state.current_time
        protected_monitor_target_name = (
            critical_end_sub_name
            if critical_end_sub_name
            else monitoring_target_sub_name or candidate.subtask.name
        )

        if not self._is_monitoring_step_admissible(
            curr_node,
            monitor_start_time=monitor_start_time,
            monitor_finish_time=monitor_finish_time,
            protected_target_name=protected_monitor_target_name,
        ):
            return None

        final_remaining_subtasks = list(monitor_state.remaining_subtasks)
        # Ensure candidate is in remaining (if it wasn't already)
        if candidate.subtask.name not in [r.name for r in final_remaining_subtasks]:
            final_remaining_subtasks.append(copy.deepcopy(candidate.subtask))

        new_constraints = copy.deepcopy(monitor_state.constraints)
        if not new_constraints.has_node(monitor_sub.name):
            new_constraints.add_node(monitor_sub.name)
        if not new_constraints.has_node(candidate.subtask.name):
            new_constraints.add_node(candidate.subtask.name)

        pred_to_mon_edge = {"Interval": 0.0, "IsCritical": True}
        if not new_constraints.has_edge(predecessor_name, monitor_sub.name):
            new_constraints.add_edge(
                predecessor_name,
                monitor_sub.name,
                info=pred_to_mon_edge,
            )
        else:
            new_constraints.edges[predecessor_name, monitor_sub.name][
                "info"
            ] = pred_to_mon_edge

        remaining_slack = max(
            0.0, target_actual_start_time - monitor_state.current_time
        )
        mon_to_candidate_edge = {
            "Interval": remaining_slack,
            "IsCritical": is_critical_link,
        }

        if not new_constraints.has_edge(monitor_sub.name, candidate.subtask.name):
            new_constraints.add_edge(
                monitor_sub.name,
                candidate.subtask.name,
                info=mon_to_candidate_edge,
            )
        else:
            new_constraints.edges[monitor_sub.name, candidate.subtask.name][
                "info"
            ] = mon_to_candidate_edge

        updated_state = SchedulerState(
            subtask=monitor_state.subtask,
            completed_entries=monitor_state.completed_entries,
            remaining_subtasks=final_remaining_subtasks,
            constraints=new_constraints,
            current_time=monitor_state.current_time,
            scene_positions=monitor_state.scene_positions,
            held_object=monitor_state.held_object,
        )

        if (
            critical_start_sub_name
            and critical_end_sub_name
            and critical_start_sub_end_time is not None
            and critical_interval_duration is not None
        ):
            constraints_with_critical = copy.deepcopy(updated_state.constraints)

            for node_name in (
                critical_start_sub_name,
                critical_end_sub_name,
                monitor_sub.name,
            ):
                if not constraints_with_critical.has_node(node_name):
                    constraints_with_critical.add_node(node_name)

            interval_start_to_mon = max(
                0.0, monitor_start_time - critical_start_sub_end_time
            )
            edge_info_start = {"Interval": interval_start_to_mon, "IsCritical": True}
            if not constraints_with_critical.has_edge(
                critical_start_sub_name, monitor_sub.name
            ):
                constraints_with_critical.add_edge(
                    critical_start_sub_name, monitor_sub.name, info=edge_info_start
                )
            else:
                constraints_with_critical.edges[
                    critical_start_sub_name, monitor_sub.name
                ]["info"] = edge_info_start

            critical_deadline = self._compute_critical_deadline(
                critical_start_sub_end_time=critical_start_sub_end_time,
                critical_interval_duration=critical_interval_duration,
            )
            if not self._monitoring_can_finish_before_deadline(
                monitoring_start_time=monitor_start_time,
                critical_start_sub_end_time=critical_start_sub_end_time,
                critical_interval_duration=critical_interval_duration,
                post_monitor_buffer=critical_end_post_monitor_buffer,
            ):
                log.debug(
                    "[_insert_monitoring_step] immediate monitoring for '%s' would miss critical deadline %.2f with post-monitor buffer %.2f. Rejecting monitoring branch.",
                    critical_end_sub_name,
                    critical_deadline,
                    critical_end_post_monitor_buffer,
                )
                return None

            # [Restored] '정확한 타이밍' 준수를 위해 Critical Deadline 기준으로 Interval을 재계산하여 적용합니다.
            # Fallback 상황(target_start=current)이라도 Critical Constraint가 있다면 그 시간을 지켜야 합니다.
            interval_mon_to_end = (
                critical_deadline
                - monitor_finish_time
                - critical_end_post_monitor_buffer
            )
            if interval_mon_to_end < -EPSILON:
                log.debug(
                    "[_insert_monitoring_step] monitoring for '%s' leaves negative slack %.2f after reserving post-monitor buffer %.2f. Rejecting monitoring branch.",
                    critical_end_sub_name,
                    interval_mon_to_end,
                    critical_end_post_monitor_buffer,
                )
                return None
            edge_info_end = {
                "Interval": max(0.0, interval_mon_to_end),
                "IsCritical": True,
            }

            log.debug(
                f"[_insert_monitoring_step] Updating Edge '{monitor_sub.name}' -> '{critical_end_sub_name}'\n"
                f"  - CriticalDeadline: {critical_deadline:.2f} (StartEnd: {critical_start_sub_end_time:.2f} + Interval: {critical_interval_duration:.2f})\n"
                f"  - MonitorFinish: {monitor_finish_time:.2f}\n"
                f"  - PostMonitorBuffer: {critical_end_post_monitor_buffer:.2f}\n"
                f"  - 모니터링 끝난 시간 부터, 다음 critical subtask 시작 시간까지의 시간: {interval_mon_to_end:.2f} "
            )

            if not constraints_with_critical.has_edge(
                monitor_sub.name, critical_end_sub_name
            ):
                constraints_with_critical.add_edge(
                    monitor_sub.name, critical_end_sub_name, info=edge_info_end
                )
            else:
                constraints_with_critical.edges[
                    monitor_sub.name, critical_end_sub_name
                ]["info"] = edge_info_end

            updated_state = updated_state._replace(
                constraints=constraints_with_critical
            )

        refreshed_node = monitor_node._replace(state=updated_state)
        return self._refresh_node_heuristic_cost(
            refreshed_node,
            context=f"monitor-insert:{candidate.subtask.name}",
        )

    # -----------------------------------------------------
    # (B) 서브태스크 (with monitoring) - 정책 2 적용
    # -----------------------------------------------------
    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        feasible_candidates: List[Candidate] = None,
    ) -> Optional[SimulationNode]:
        curr_state = curr_node.state
        original_task_name = candidate.subtask.name

        # Determine the critical interval that triggers this monitoring split
        scheduling_due = candidate.scheduling_due
        # 모니터링으로 쪼갤 때, critical end subtask를 가장 빠르게 deadline을 갖는 것으로 관찰하게 함. (분산 높은 것 보다...)
        if not (
            scheduling_due
            and scheduling_due.due_date != float("inf")
            and scheduling_due.due_related_sub_name
        ):
            log.debug(
                f"Candidate {original_task_name} has no valid scheduling_due. Fallback to non-monitoring."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        critical_end_sub_name = scheduling_due.due_related_sub_name

        # Find the start of the critical interval
        incoming_constraints_to_crit_end = self.constraint_handler.get_time_slots(
            critical_end_sub_name, curr_state.constraints, "in"
        )
        critical_incoming_slots = [
            s for s in incoming_constraints_to_crit_end if s.is_critical
        ]
        if not critical_incoming_slots:
            log.debug(
                f"No incoming critical constraints for '{critical_end_sub_name}'. Fallback for {original_task_name}."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        target_critical_slot = max(critical_incoming_slots, key=lambda s: s.interval)
        original_critical_interval_duration = target_critical_slot.interval
        critical_start_sub_name = target_critical_slot.related_subtask_name

        critical_start_completed_entry = next(
            (
                ce
                for ce in curr_state.completed_entries
                if ce.subtask.name == critical_start_sub_name
            ),
            None,
        )
        if not critical_start_completed_entry:
            log.error(
                f"CRITICAL LOGIC ERROR: start_subtask '{critical_start_sub_name}' not found. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        critical_start_sub_actual_end_time = (
            critical_start_completed_entry.schedule_end_time
        )

        if self._monitoring_budget_reached(
            curr_state,
            critical_start_sub_end_time=critical_start_sub_actual_end_time,
            critical_end_sub_name=critical_end_sub_name,
        ):
            log.debug(
                "Monitoring budget reached for '%s'. Falling back to non-monitoring expansion.",
                critical_end_sub_name,
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        monitoring_target_obj = next(
            (
                (remain_sub.execution.primitive_actions[0].split()[1])
                for remain_sub in curr_node.state.remaining_subtasks
                if remain_sub.name == critical_end_sub_name
                and remain_sub.execution
                and remain_sub.execution.primitive_actions
            ),
            None,
        )
        if not monitoring_target_obj:
            log.warning(
                f"Could not determine monitoring target for '{critical_end_sub_name}'. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        log.debug(
            f"CritStart='{critical_start_sub_name}' -> CritEnd='{critical_end_sub_name+original_task_name}' (ends {critical_start_sub_actual_end_time:.2f}: {critical_start_completed_entry.schedule_end_time}+{original_critical_interval_duration:.2f})",
        )

        # --- Refined Splitting Logic ---
        # Retrieve variance from the edge info
        edge_data = curr_state.constraints.get_edge_data(
            critical_start_sub_name, critical_end_sub_name
        )
        variance_val = constants.INIT_PRIOR_VARIANCE
        if edge_data and "info" in edge_data:
            variance_val = edge_data["info"].get("Variance", constants.INIT_PRIOR_VARIANCE)

        original_absolute_monitoring_trigger_time = (
            self._compute_monitoring_trigger_time(
                raw_object_name=monitoring_target_obj,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                mean_duration=original_critical_interval_duration,
                variance=variance_val,
            )
        )
        critical_end_nav_buffer = self._estimate_subtask_navigation_buffer(
            curr_node,
            critical_end_sub_name,
            feasible_candidates=feasible_candidates,
            not_yet_candidates=not_yet_candidates,
        )

        full_candidate_action_info_check = self.action_handler.get_actions_info(
            curr_node, candidate.subtask.execution.primitive_actions
        )
        if not (
            full_candidate_action_info_check
            and full_candidate_action_info_check.success
        ):
            log.warning(
                f"Full action sim failed for candidate {original_task_name} during check.."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        candidate_expected_completion_time_wo_split = (
            curr_state.current_time + full_candidate_action_info_check.cumulative_time
        )

        # Scenario 1: Task is "safe" and finishes before monitoring is needed.
        if (
            candidate_expected_completion_time_wo_split
            <= original_absolute_monitoring_trigger_time
        ):
            log.debug(
                f"Candidate {original_task_name} finishes before monitoring trigger ({original_absolute_monitoring_trigger_time:.2f}). Executing without split.\n"
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        if not self._monitoring_can_finish_before_deadline(
            monitoring_start_time=original_absolute_monitoring_trigger_time,
            critical_start_sub_end_time=critical_start_sub_actual_end_time,
            critical_interval_duration=original_critical_interval_duration,
            post_monitor_buffer=critical_end_nav_buffer,
        ):
            log.debug(
                "Monitoring trigger for '%s' would finish after the critical deadline once nav buffer %.2f is reserved. Falling back to non-monitoring expansion.",
                critical_end_sub_name,
                critical_end_nav_buffer,
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        # Scenario 3: Monitoring trigger falls during the task. Splitting is necessary.
        duration_for_early_sub_target = (
            original_absolute_monitoring_trigger_time - curr_state.current_time
        )

        pre_actions_log, post_actions_log, split_successful, pre_ends_holding_object = (
            self.action_handler.split_subtask_by_cutoff_time(
                curr_node,
                candidate.subtask.execution.primitive_actions,
                duration_for_early_sub_target,
            )
        )

        if not split_successful or pre_ends_holding_object:
            log.debug(
                f"Failed to split {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. "
                f"Switching to Pre-Monitoring (Check-Before-Act) strategy as a fallback."
            )
            # [Safety Check 250130] Prevent redundant monitoring
            # If the immediately preceding task was ALREADY a monitoring action for the SAME object,
            # we should NOT insert another monitoring step. This prevents infinite monitoring loops.
            predecessor_monitor_target_obj = None
            predecessor_monitor_target_name = None
            if (
                curr_node.state.subtask
                and curr_node.state.subtask.subtask_type == "Monitor"
            ):
                predecessor_execution = curr_node.state.subtask.execution
                if (
                    predecessor_execution
                    and predecessor_execution.objects
                    and predecessor_execution.objects[0] is not None
                ):
                    predecessor_monitor_target_obj = predecessor_execution.objects[0]
                try:
                    predecessor_monitor_target_name = extract_monitoring_target_name(
                        curr_node.state.subtask.name
                    )
                except ValueError:
                    predecessor_monitor_target_name = None
            if (
                curr_node.state.subtask
                and curr_node.state.subtask.subtask_type == "Monitor"
                and (
                    predecessor_monitor_target_obj == monitoring_target_obj
                    or predecessor_monitor_target_name == critical_end_sub_name
                )
            ):
                log.warning(
                    f"[_expand_subtask_with_monitoring] Redundant monitoring detected! "
                    f"Predecessor '{curr_node.state.subtask.name}' already monitored "
                    f"target_obj='{monitoring_target_obj}' / target_sub='{critical_end_sub_name}'. "
                    f"Skipping monitoring insertion and proceeding with original task."
                )
                return self._expand_subtask_wo_monitoring(
                    curr_node, candidate, not_yet_candidates, feasible_candidates
                )
            # [Fallback] 분할 실패 시, 작업을 시작하기 '전'에 미리 모니터링을 수행하는 경로를 탐색에 추가합니다.
            # 모니터링 시간만큼 작업 착수가 지연되지만, 불확실성을 해소할 수 있는 안전한 선택지입니다.
            inserted_monitor_node = self._insert_monitoring_step(
                curr_node=curr_node,
                candidate=candidate,
                monitoring_target_obj=monitoring_target_obj,
                predecessor_name=curr_node.state.subtask.name,
                target_actual_start_time=curr_state.current_time,  # 즉시 수행
                not_yet_candidates=not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
                is_critical_link=False,
                critical_end_post_monitor_buffer=critical_end_nav_buffer,
            )
            if inserted_monitor_node is not None:
                return inserted_monitor_node
            log.debug(
                "Immediate monitoring fallback for '%s' could not satisfy the critical deadline. Executing without monitoring.",
                critical_end_sub_name,
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        log.info(f"{pre_actions_log.total_time_used()},{pre_actions_log=}")
        log.info(f"{post_actions_log.total_time_used()},{post_actions_log=}")

        early_sub_actions = []
        actual_early_sub_duration = 0.0

        if (
            pre_actions_log
            and pre_actions_log.results
            and pre_actions_log.get_actions()
        ):
            early_sub_actions = pre_actions_log.get_actions()
            actual_early_sub_duration = pre_actions_log.total_time_used()
            log.debug(
                f"Split {original_task_name}: Initial early_actions ({len(early_sub_actions)}), actual_duration={actual_early_sub_duration:.2f}, target_duration={duration_for_early_sub_target:.2f}"
            )
        else:
            log.warning(
                f"Failed to get valid early_actions from split for {original_task_name} with cutoff {duration_for_early_sub_target:.2f}. "
                f"Executing the task without splitting as a fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        # --- Phase 3: early_sub 확장 및 실제 모니터링 시점 결정 ---
        early_sub_task = copy.deepcopy(candidate.subtask)
        early_sub_task.name = (
            f"EARLY_{original_task_name}"
            if len(post_actions_log.results) != 0
            else original_task_name
        )
        early_sub_task.execution.primitive_actions = early_sub_actions
        early_sub_task.decomposed = True

        early_candidate = Candidate(
            subtask=early_sub_task,
            scheduling_due=None,
            is_critical=candidate.is_critical,
            logical_interaction_start_time=candidate.logical_interaction_start_time,
            actual_interaction_start_time=candidate.actual_interaction_start_time,
            estimated_first_nav_duration=candidate.estimated_first_nav_duration,
        )

        log.info(
            f"  Expanding adjusted EARLY subtask: {early_sub_task.name} (actions: {len(early_sub_actions)}, initial_est_duration: {actual_early_sub_duration:.2f})"
        )
        node_after_early_sub = self._expand_subtask_wo_monitoring(
            curr_node, early_candidate, not_yet_candidates
        )

        if node_after_early_sub is None:
            log.warning(
                f"Expansion of EARLY subtask {early_sub_task.name} failed. "
                f"Executing the original task without splitting as a fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        actual_monitoring_trigger_time = node_after_early_sub.state.current_time

        log.info(
            f"  EARLY subtask {early_sub_task.name} expanded. Actual Monitoring Trigger Time: {actual_monitoring_trigger_time:.2f} "
            f"(Original trigger was: {original_absolute_monitoring_trigger_time:.2f})"
        )

        if not self._monitoring_can_finish_before_deadline(
            monitoring_start_time=actual_monitoring_trigger_time,
            critical_start_sub_end_time=critical_start_sub_actual_end_time,
            critical_interval_duration=original_critical_interval_duration,
            post_monitor_buffer=self._estimate_subtask_navigation_buffer(
                node_after_early_sub,
                critical_end_sub_name,
            ),
        ):
            log.debug(
                "Actual monitoring timing drifted past the feasible deadline for '%s'. Falling back to non-monitoring expansion.",
                critical_end_sub_name,
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        state_after_early_expansion = node_after_early_sub.state

        if not self._is_monitoring_step_admissible(
            node_after_early_sub,
            monitor_start_time=actual_monitoring_trigger_time,
            monitor_finish_time=actual_monitoring_trigger_time + MONITORING_DURATION,
            protected_target_name=critical_end_sub_name,
        ):
            log.debug(
                "Split-monitor branch for '%s' was rejected by monitoring admissibility. Falling back to non-monitoring expansion.",
                critical_end_sub_name,
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        # --- Phase 4: mon_sub (주요 인터벌용) 및 remain_sub 생성 ---
        mon_sub_task_for_main_interval = TaskUtil.create_monitoring_subtask(
            name=f"{critical_end_sub_name}",
            obj=monitoring_target_obj,
        )
        log.debug(f"mon_sub_task_for_main_interval: {mon_sub_task_for_main_interval}")
        mon_sub_task_for_main_interval.decomposed = True

        remain_sub_actions = (
            post_actions_log.get_actions()
            if post_actions_log and post_actions_log.results
            else []
        )
        if remain_sub_actions:
            first_action = remain_sub_actions[0]
            if not first_action.startswith("NAVIGATE_TO"):
                # Try to infer a reasonable target object id from actions
                def _extract_target_id(actions: List[str]) -> Optional[str]:
                    for act in actions:
                        parts = act.split()
                        if len(parts) > 1:
                            return parts[1]
                    return None

                target_id = _extract_target_id(remain_sub_actions)
                if target_id and target_id in curr_state.scene_positions:
                    remain_sub_actions = [
                        f"NAVIGATE_TO {target_id}"
                    ] + remain_sub_actions

        if remain_sub_actions:
            remain_subtask = copy.deepcopy(candidate.subtask)
            remain_subtask.name = f"REMAIN_{original_task_name}"
            remain_subtask.execution.primitive_actions = remain_sub_actions
            remain_subtask.decomposed = True
            log.debug(
                f"Prepared REMAIN subtask: {remain_subtask.name} with {len(remain_sub_actions)} actions."
            )

        # --- Phase 5: 제약 조건 그래프 및 remaining_subtasks 업데이트 ---
        new_constraints_graph = copy.deepcopy(state_after_early_expansion.constraints)

        original_task_in_edges_data = []
        original_task_out_edges_data = []
        if new_constraints_graph.has_node(original_task_name):
            original_task_in_edges_data = list(
                new_constraints_graph.in_edges(original_task_name, data=True)
            )
            original_task_out_edges_data = list(
                new_constraints_graph.out_edges(original_task_name, data=True)
            )
            new_constraints_graph.remove_node(original_task_name)
            log.debug(f"Removed node '{original_task_name}' from constraints graph.")

        if not new_constraints_graph.has_node(early_sub_task.name):
            new_constraints_graph.add_node(early_sub_task.name)
            log.debug(f"Node for EARLY subtask '{early_sub_task.name}' added to graph.")
        if not new_constraints_graph.has_node(mon_sub_task_for_main_interval.name):
            new_constraints_graph.add_node(mon_sub_task_for_main_interval.name)
        if remain_subtask and not new_constraints_graph.has_node(remain_subtask.name):
            new_constraints_graph.add_node(remain_subtask.name)

        for pred_name, _, data in original_task_in_edges_data:
            if pred_name not in [
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                (remain_subtask.name if remain_subtask else ""),
                original_task_name,
                # critical_start_sub_name,
            ]:
                edge_info = copy.deepcopy(data.get("info", {}))
                if not new_constraints_graph.has_edge(pred_name, early_sub_task.name):
                    new_constraints_graph.add_edge(
                        pred_name, early_sub_task.name, info=edge_info
                    )
                    log.debug(
                        f"Rerouted incoming constraint from '{pred_name}' to '{early_sub_task.name}'."
                    )

        source_for_outgoing_edges = (
            remain_subtask.name
            if remain_subtask
            else mon_sub_task_for_main_interval.name
        )
        for _, succ_name, data in original_task_out_edges_data:
            if succ_name not in [
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                (remain_subtask.name if remain_subtask else ""),
                original_task_name,
                # critical_end_sub_name,
            ]:
                edge_info = copy.deepcopy(data.get("info", {}))
                if not new_constraints_graph.has_edge(
                    source_for_outgoing_edges, succ_name
                ):
                    new_constraints_graph.add_edge(
                        source_for_outgoing_edges, succ_name, info=edge_info
                    )
                    log.debug(
                        f"Rerouted outgoing constraint from '{source_for_outgoing_edges}' to '{succ_name}'."
                    )

        info_early_to_mon = {"Interval": 0.0, "IsCritical": True}
        if not new_constraints_graph.has_edge(
            early_sub_task.name, mon_sub_task_for_main_interval.name
        ):
            new_constraints_graph.add_edge(
                early_sub_task.name,
                mon_sub_task_for_main_interval.name,
                info=info_early_to_mon,
            )
            log.debug(
                f"Added internal constraint: '{early_sub_task.name}' -> '{mon_sub_task_for_main_interval.name}'."
            )

        critical_end_sub_original_deadline = self._compute_critical_deadline(
            critical_start_sub_end_time=critical_start_sub_actual_end_time,
            critical_interval_duration=original_critical_interval_duration,
        )
        mon_sub_expected_completion_time = (
            actual_monitoring_trigger_time + MONITORING_DURATION
        )
        remain_sub_total_duration = (
            float(post_actions_log.total_time_used())
            if remain_subtask and post_actions_log and post_actions_log.results
            else 0.0
        )
        must_finish_critical_end_before_remain = bool(
            remain_subtask
            and (
                mon_sub_expected_completion_time + remain_sub_total_duration
                > (critical_end_sub_original_deadline + EPSILON)
            )
        )
        if remain_subtask:
            if must_finish_critical_end_before_remain:
                info_crit_end_to_remain = {"Interval": 0.0, "IsCritical": False}
                if not new_constraints_graph.has_edge(
                    critical_end_sub_name, remain_subtask.name
                ):
                    new_constraints_graph.add_edge(
                        critical_end_sub_name,
                        remain_subtask.name,
                        info=info_crit_end_to_remain,
                    )
                log.debug(
                    "Forced '%s' before '%s' because the remain segment (%.2fs) cannot finish before critical deadline %.2f once monitoring completes at %.2f.",
                    critical_end_sub_name,
                    remain_subtask.name,
                    remain_sub_total_duration,
                    critical_end_sub_original_deadline,
                    mon_sub_expected_completion_time,
                )
            else:
                info_mon_to_remain = {"Interval": 0.0, "IsCritical": False}
                if not new_constraints_graph.has_edge(
                    mon_sub_task_for_main_interval.name, remain_subtask.name
                ):
                    new_constraints_graph.add_edge(
                        mon_sub_task_for_main_interval.name,
                        remain_subtask.name,
                        info=info_mon_to_remain,
                    )
                    log.debug(
                        f"Added internal constraint: '{mon_sub_task_for_main_interval.name}' -> '{remain_subtask.name}'."
                    )

        interval_crit_start_to_mon = (
            actual_monitoring_trigger_time - critical_start_sub_actual_end_time
        )
        info_crit_start_to_mon = {
            "Interval": max(0.0, interval_crit_start_to_mon),
            "IsCritical": True,
        }
        if not new_constraints_graph.has_edge(
            critical_start_sub_name, mon_sub_task_for_main_interval.name
        ):
            new_constraints_graph.add_edge(
                critical_start_sub_name,
                mon_sub_task_for_main_interval.name,
                info=info_crit_start_to_mon,
            )
        else:
            new_constraints_graph.edges[
                critical_start_sub_name, mon_sub_task_for_main_interval.name
            ]["info"].update(info_crit_start_to_mon)
        log.debug(
            f"Added/Updated main monitoring constraint: '{critical_start_sub_name}' -> '{mon_sub_task_for_main_interval.name}', Interval: {info_crit_start_to_mon['Interval']:.2f}."
        )

        critical_end_nav_buffer_after_monitor = self._estimate_subtask_navigation_buffer(
            node_after_early_sub,
            critical_end_sub_name,
        )

        interval_mon_to_crit_end = (
            critical_end_sub_original_deadline
            - mon_sub_expected_completion_time
            - critical_end_nav_buffer_after_monitor
        )
        if interval_mon_to_crit_end < -EPSILON:
            log.debug(
                "Monitoring branch for '%s' produced negative slack %.2f after reserving nav buffer %.2f. Falling back to non-monitoring expansion.",
                critical_end_sub_name,
                interval_mon_to_crit_end,
                critical_end_nav_buffer_after_monitor,
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        info_mon_to_crit_end = {
            "Interval": max(0.0, interval_mon_to_crit_end),
            "IsCritical": True,
        }

        # [DEBUG LOG] Check Interval Update in _expand_subtask_with_monitoring
        prev_interval_sub = "N/A"
        if new_constraints_graph.has_edge(
            mon_sub_task_for_main_interval.name, critical_end_sub_name
        ):
            prev_interval_sub = (
                new_constraints_graph.edges[
                    mon_sub_task_for_main_interval.name, critical_end_sub_name
                ]
                .get("info", {})
                .get("Interval", "N/A")
            )

        log.debug(
            f"[DEBUG _expand_subtask_with_monitoring] Updating Edge '{mon_sub_task_for_main_interval.name}' -> '{critical_end_sub_name}'\n"
            f"  - CritEndDeadline: {critical_end_sub_original_deadline:.2f}\n"
            f"  - MonitorFinish: {mon_sub_expected_completion_time:.2f}\n"
            f"  - NavBufferAfterMonitor: {critical_end_nav_buffer_after_monitor:.2f}\n"
            f"  - Calc Interval: {interval_mon_to_crit_end:.2f} (Prev: {prev_interval_sub})"
        )

        if not new_constraints_graph.has_edge(
            mon_sub_task_for_main_interval.name, critical_end_sub_name
        ):
            new_constraints_graph.add_edge(
                mon_sub_task_for_main_interval.name,
                critical_end_sub_name,
                info=info_mon_to_crit_end,
            )
        else:
            new_constraints_graph.edges[
                mon_sub_task_for_main_interval.name, critical_end_sub_name
            ]["info"].update(info_mon_to_crit_end)

        # Verify update
        check_interval_sub = new_constraints_graph.edges[
            mon_sub_task_for_main_interval.name, critical_end_sub_name
        ]["info"]["Interval"]
        log.debug(f"  -> Update Verified: {check_interval_sub:.2f}")
        log.debug(
            f"Added/Updated main monitoring constraint: '{mon_sub_task_for_main_interval.name}' -> '{critical_end_sub_name}', Interval: {info_mon_to_crit_end['Interval']:.2f}."
        )

        remaining_after_early_executed = list(
            state_after_early_expansion.remaining_subtasks
        )
        final_remaining_subtasks_list = [
            r for r in remaining_after_early_executed if r.name != original_task_name
        ]

        if mon_sub_task_for_main_interval.name not in {
            r.name for r in final_remaining_subtasks_list
        }:
            final_remaining_subtasks_list.append(mon_sub_task_for_main_interval)
        if remain_subtask and remain_subtask.name not in {
            r.name for r in final_remaining_subtasks_list
        }:
            final_remaining_subtasks_list.append(remain_subtask)

        log.debug(
            f"Updated remaining subtasks. Added mon: {mon_sub_task_for_main_interval.name}, remain: {remain_subtask.name if remain_subtask else 'None'}"
        )
        log.debug(
            f"  Final remaining: {[r.name for r in final_remaining_subtasks_list]}"
        )

        updated_final_state = SchedulerState(
            subtask=state_after_early_expansion.subtask,
            completed_entries=state_after_early_expansion.completed_entries,
            remaining_subtasks=final_remaining_subtasks_list,
            constraints=new_constraints_graph,
            current_time=actual_monitoring_trigger_time,
            scene_positions=state_after_early_expansion.scene_positions,
            held_object=state_after_early_expansion.held_object,
        )

        refreshed_node = node_after_early_sub._replace(state=updated_final_state)
        return self._refresh_node_heuristic_cost(
            refreshed_node,
            context=f"monitor-split:{candidate.subtask.name}",
        )

    # -----------------------------------------------------
    # (C) Wait expansions
    # -----------------------------------------------------

    def _expand_wait_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        nav_duration: float = 0.0,
        feasible_candidates: List[Candidate] = None,
    ) -> SimulationNode:
        """
        Performs monitoring and, if needed, a follow-up wait until the
        candidate's actual_interaction_start_time.
        """
        # candidate는 wait for의 대상 subtask임.
        # wait candidate는 global due와 self due(logical start)를 모두 보존한다.
        log.debug(
            f"[_expand_wait_with_monitoring] Waiting for {candidate.subtask.name}"
        )

        curr_state = curr_node.state

        critical_end_sub_name = candidate.subtask.name

        # Find the start of the critical interval
        incoming_constraints_to_crit_end = self.constraint_handler.get_time_slots(
            critical_end_sub_name, curr_state.constraints, "in"
        )
        critical_incoming_slots = [
            s for s in incoming_constraints_to_crit_end if s.is_critical
        ]
        if not critical_incoming_slots:
            log.debug(
                f"No incoming critical constraints for '{critical_end_sub_name}'. Fallback for {candidate.subtask.name}."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )

        target_critical_slot = max(critical_incoming_slots, key=lambda s: s.interval)
        original_critical_interval_duration = target_critical_slot.interval
        critical_start_sub_name = target_critical_slot.related_subtask_name

        critical_start_completed_entry = next(
            (
                ce
                for ce in curr_state.completed_entries
                if ce.subtask.name == critical_start_sub_name
            ),
            None,
        )
        if not critical_start_completed_entry:
            log.error(
                f"CRITICAL LOGIC ERROR: start_subtask '{critical_start_sub_name}' not found. Fallback."
            )
            return self._expand_subtask_wo_monitoring(
                curr_node, candidate, not_yet_candidates, feasible_candidates
            )
        critical_start_sub_actual_end_time = (
            critical_start_completed_entry.schedule_end_time
        )

        if self._monitoring_budget_reached(
            curr_state,
            critical_start_sub_end_time=critical_start_sub_actual_end_time,
            critical_end_sub_name=critical_end_sub_name,
        ):
            log.debug(
                "Monitoring budget reached for '%s'. Falling back to wait-without-monitoring.",
                critical_end_sub_name,
            )
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_duration,
                feasible_candidates=feasible_candidates,
            )
        # Retrieve variance from the edge info
        edge_data = curr_state.constraints.get_edge_data(
            critical_start_sub_name, critical_end_sub_name
        )
        variance_val = constants.INIT_PRIOR_VARIANCE
        if edge_data and "info" in edge_data:
            variance_val = edge_data["info"].get("Variance", constants.INIT_PRIOR_VARIANCE)

        original_absolute_monitoring_trigger_time = (
            self._compute_monitoring_trigger_time(
                raw_object_name=candidate.subtask.execution.primitive_actions[
                    0
                ].split()[1],
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                mean_duration=original_critical_interval_duration,
                variance=variance_val,
            )
        )

        total_wait_duration = max(
            0,
            original_absolute_monitoring_trigger_time
            - curr_state.current_time
            - nav_duration,
        )

        # 현재 시간에서 wait하고 모니터링을하는게 deadline을 넘기면 wo monitoring으로 fallback
        if not self._monitoring_can_finish_before_deadline(
            monitoring_start_time=original_absolute_monitoring_trigger_time,
            critical_start_sub_end_time=critical_start_sub_actual_end_time,
            critical_interval_duration=original_critical_interval_duration,
            post_monitor_buffer=nav_duration,
        ):
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_duration,
                feasible_candidates=feasible_candidates,
            )

        if total_wait_duration <= EPSILON:
            monitoring_target_obj = candidate.subtask.execution.primitive_actions[
                0
            ].split()[1]
            predecessor_monitor_target_obj = None
            predecessor_monitor_target_name = None
            if (
                curr_state.subtask is not None
                and curr_state.subtask.subtask_type == "Monitor"
            ):
                predecessor_execution = curr_state.subtask.execution
                if (
                    predecessor_execution
                    and predecessor_execution.objects
                    and predecessor_execution.objects[0] is not None
                ):
                    predecessor_monitor_target_obj = predecessor_execution.objects[0]
                try:
                    predecessor_monitor_target_name = extract_monitoring_target_name(
                        curr_state.subtask.name
                    )
                except ValueError:
                    predecessor_monitor_target_name = None
            if (
                curr_state.subtask is not None
                and curr_state.subtask.subtask_type == "Monitor"
                and (
                    predecessor_monitor_target_obj == monitoring_target_obj
                    or predecessor_monitor_target_name == critical_end_sub_name
                )
            ):
                log.debug(
                    "[_expand_wait_with_monitoring] Zero-duration wait for '%s' "
                    "immediately after monitoring the same target. Falling back to "
                    "wait-without-monitoring to avoid redundant re-monitoring.",
                    candidate.subtask.name,
                )
                return self._expand_wait_wo_monitoring(
                    curr_node,
                    candidate,
                    not_yet_candidates,
                    nav_duration=nav_duration,
                    feasible_candidates=feasible_candidates,
                )
            predecessor_name = (
                curr_state.subtask.name
                if curr_state.subtask is not None
                else critical_start_sub_name
            )
            target_start_time = (
                self._get_candidate_target_start_time(candidate)
                or curr_state.current_time
            )
            log.debug(
                "[_expand_wait_with_monitoring] Zero-duration wait for '%s'. "
                "Skipping synthetic WAIT node and inserting immediate monitoring.",
                candidate.subtask.name,
            )
            inserted_monitor_node = self._insert_monitoring_step(
                curr_node=curr_node,
                candidate=candidate,
                monitoring_target_obj=monitoring_target_obj,
                predecessor_name=predecessor_name,
                target_actual_start_time=target_start_time,
                not_yet_candidates=not_yet_candidates,
                critical_start_sub_name=critical_start_sub_name,
                critical_start_sub_end_time=critical_start_sub_actual_end_time,
                critical_end_sub_name=critical_end_sub_name,
                critical_interval_duration=original_critical_interval_duration,
                monitoring_target_sub_name=critical_end_sub_name,
                is_critical_link=True,
                critical_end_post_monitor_buffer=nav_duration,
            )
            if inserted_monitor_node is not None:
                return inserted_monitor_node
            log.debug(
                "[_expand_wait_with_monitoring] Immediate monitoring fallback for '%s' "
                "was rejected. Falling back to wait-without-monitoring.",
                candidate.subtask.name,
            )
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_duration,
                feasible_candidates=feasible_candidates,
            )

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=total_wait_duration, type="Controllable"),
            repetition=1,
            subtask_type="WAIT",
            execution=Execution(
                objects=None, primitive_actions=[f"WAIT {total_wait_duration}"]
            ),
            temporal_constraints=None,
        )
        wait_start_time = curr_state.current_time
        wait_end_time = curr_state.current_time + total_wait_duration

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            schedule_start_time=wait_start_time,
            schedule_end_time=wait_end_time,
            schedule_nav_time=0.0,
            execution_status=True,
        )
        new_completed = curr_state.completed_entries + [completed_entry]

        new_state = SchedulerState(
            subtask=wait_sub,
            completed_entries=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=wait_end_time,
            scene_positions=curr_state.scene_positions,
            held_object=curr_state.held_object,
        )

        # Create a synthetic candidate to represent the 'Wait' action for the heuristic calculator.
        wait_candidate = Candidate(
            subtask=wait_sub,
            is_critical=candidate.is_critical,
            logical_interaction_start_time=candidate.logical_interaction_start_time,
            scheduling_due=candidate.scheduling_due,
        )

        # Global Risk Check을 위해 feasible_candidates도 포함하여 전달
        all_candidates = not_yet_candidates
        if feasible_candidates:
            all_candidates = feasible_candidates + not_yet_candidates

        step_risk, _ = self.cost_calculator.calc_heuristic(
            curr_node,
            wait_candidate,
            all_candidates,
            # Wait action creates delay. We must check if this delay hurts ANY feasible or not_yet task.
        )

        # Accumulate max risk level
        new_risk = max(curr_node.risk_level, step_risk)

        log.info(
            f"[_expand_wait_with_monitoring] Waiting for{candidate.subtask.name}: end_time({wait_end_time:.2f}) = current_time({curr_state.current_time:.2f}) + wait_duration({total_wait_duration:.2f})"
        )

        pre_monitor_node = SimulationNode(
            heuristic_cost=wait_end_time,
            depth=curr_node.depth + 1,
            tie_breaker=curr_node.tie_breaker,
            parent_node=curr_node,
            state=new_state,
            risk_level=new_risk,
        )
        if not self._is_monitoring_step_admissible(
            pre_monitor_node,
            monitor_start_time=wait_end_time,
            monitor_finish_time=wait_end_time + MONITORING_DURATION,
            protected_target_name=critical_end_sub_name,
        ):
            log.debug(
                "Wait-with-monitoring branch for '%s' was rejected by monitoring admissibility. Falling back to wait-without-monitoring.",
                critical_end_sub_name,
            )
            return self._expand_wait_wo_monitoring(
                curr_node,
                candidate,
                not_yet_candidates,
                nav_duration=nav_duration,
                feasible_candidates=feasible_candidates,
            )

        monitoring_sub = TaskUtil.create_monitoring_subtask(
            name=f"{critical_end_sub_name}",
            obj=candidate.subtask.execution.primitive_actions[0].split()[1],
        )
        monitoring_sub.decomposed = True

        # --- Phase 5: 제약 조건 그래프 및 remaining_subtasks 업데이트 ---
        # 없던 wait subtask가 생긴 상황, 모니터링 task도 만들었음. 제약 조건으로 연결해야 함.
        # wait는 0,True로 monitoring과 연결짓고, candidate와 monitoring은 interval, True만큼 업데이트 시켜야 함
        new_constraints_graph = copy.deepcopy(new_state.constraints)

        if not new_constraints_graph.has_node(wait_sub.name):
            new_constraints_graph.add_node(wait_sub.name)
            log.debug(f"Node for WAIT subtask '{wait_sub.name}' added to graph.")
        if not new_constraints_graph.has_node(monitoring_sub.name):
            new_constraints_graph.add_node(monitoring_sub.name)
            log.debug(
                f"Node for MONITORING subtask '{monitoring_sub.name}' added to graph."
            )

        edge_from_wait_to_mon = {"Interval": 0.0, "IsCritical": True}
        if not new_constraints_graph.has_edge(wait_sub.name, monitoring_sub.name):
            new_constraints_graph.add_edge(
                wait_sub.name,
                monitoring_sub.name,
                info=edge_from_wait_to_mon,
            )
            log.debug(
                f"Added wait to monitoring constraint: '{wait_sub.name}' -> '{monitoring_sub.name} ({edge_from_wait_to_mon['Interval']:.2f}, {edge_from_wait_to_mon['IsCritical']}).'."
            )

        interval_crit_start_to_mon = wait_end_time - critical_start_sub_actual_end_time
        info_crit_start_to_mon = {
            "Interval": max(0.0, interval_crit_start_to_mon),
            "IsCritical": True,
        }

        if not new_constraints_graph.has_edge(
            critical_start_sub_name, monitoring_sub.name
        ):
            new_constraints_graph.add_edge(
                critical_start_sub_name,
                monitoring_sub.name,
                info=info_crit_start_to_mon,
            )
        else:
            new_constraints_graph.edges[critical_start_sub_name, monitoring_sub.name][
                "info"
            ].update(info_crit_start_to_mon)
        log.debug(
            f"Added/Updated main monitoring constraint: '{critical_start_sub_name}' -> '{monitoring_sub.name}', Interval: {info_crit_start_to_mon['Interval']:.2f}."
        )

        critical_end_sub_logical_start_time = (
            critical_start_sub_actual_end_time + original_critical_interval_duration
        )
        monitoring_sub_expected_completion_time = wait_end_time + MONITORING_DURATION

        interval_mon_to_crit_end = (
            critical_end_sub_logical_start_time
            - monitoring_sub_expected_completion_time
        )
        info_mon_to_crit_end = {
            "Interval": max(0.0, interval_mon_to_crit_end),
            "IsCritical": True,
        }

        # [DEBUG LOG] Check Interval Update in _expand_subtask_with_monitoring
        prev_interval_sub = "N/A"
        if new_constraints_graph.has_edge(monitoring_sub.name, critical_end_sub_name):
            prev_interval_sub = (
                new_constraints_graph.edges[monitoring_sub.name, critical_end_sub_name]
                .get("info", {})
                .get("Interval", "N/A")
            )

        log.debug(
            f"[DEBUG _expand_subtask_with_monitoring] Updating Edge '{monitoring_sub.name}' -> '{critical_end_sub_name}'\n"
            f"  - CritEndDeadline: {critical_end_sub_logical_start_time:.2f}\n"
            f"  - MonitorFinish: {monitoring_sub_expected_completion_time:.2f}\n"
            f"  - Mon -> CritEnd Interval: {interval_mon_to_crit_end:.2f} (Prev: {prev_interval_sub})"
        )

        if not new_constraints_graph.has_edge(
            monitoring_sub.name, critical_end_sub_name
        ):
            new_constraints_graph.add_edge(
                monitoring_sub.name,
                critical_end_sub_name,
                info=info_mon_to_crit_end,
            )
        else:
            new_constraints_graph.edges[monitoring_sub.name, critical_end_sub_name][
                "info"
            ].update(info_mon_to_crit_end)

        # Verify update
        check_interval_sub = new_constraints_graph.edges[
            monitoring_sub.name, critical_end_sub_name
        ]["info"]["Interval"]
        log.debug(f"  -> Update Verified: {check_interval_sub:.2f}")
        log.debug(
            f"Added/Updated main monitoring constraint: '{monitoring_sub.name}' -> '{critical_end_sub_name}', Interval: {info_mon_to_crit_end['Interval']:.2f}."
        )

        new_state = SchedulerState(
            subtask=new_state.subtask,
            completed_entries=new_state.completed_entries,
            remaining_subtasks=list(new_state.remaining_subtasks) + [monitoring_sub],
            constraints=new_constraints_graph,
            current_time=wait_end_time,
            scene_positions=new_state.scene_positions,
            held_object=new_state.held_object,
        )

        # return node_after_early_sub._replace(state=updated_final_state)

        refreshed_node = SimulationNode(
            parent_node=curr_node,
            heuristic_cost=wait_end_time,
            depth=curr_node.depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
            risk_level=new_risk,
        )
        return self._refresh_node_heuristic_cost(
            refreshed_node,
            context=f"monitor-wait:{candidate.subtask.name}",
        )

    def _expand_wait_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        not_yet_candidates: List[Candidate],
        nav_duration: float = 0.0,
        feasible_candidates: List[Candidate] = None,
        max_wait_duration: Optional[float] = None,
        additional_delay: float = 0.0,
    ) -> Optional[SimulationNode]:
        """
        Inserts a single "Wait" action until the candidate's actual_interaction_start_time.

        - If actual_interaction_start_time <= current_time, wait_duration becomes 0.
        - This wait is modeled as a Subtask with type="Wait".


        Args:
            curr_node (SimulationNode): Current node in the search tree.
            candidate (Candidate): The candidate subtask we're waiting for.
            nav_duration (float): Estimated navigation duration to the target object.
            additional_delay (float): Extra wait time to avoid conflicts (used for Conflict-Avoidance Wait).

        Returns:
            SimulationNode: The child node representing the new state after waiting.
            모니터링 시점까지 대기 혹은 Earliest start time의 candidate 시작 시점까지 대기
        """
        curr_state = curr_node.state
        depth = curr_node.depth

        target_start_time = (
            candidate.actual_interaction_start_time
            if candidate.actual_interaction_start_time is not None
            else (
                candidate.logical_interaction_start_time
                if candidate.logical_interaction_start_time is not None
                else curr_state.current_time
            )
        )

        # [Added 250130] Support Conflict-Avoidance Wait
        # If additional_delay is provided, push the target start time further.
        if additional_delay > 0:
            target_start_time += additional_delay

        if max_wait_duration is not None:
            target_start_time = min(
                target_start_time, curr_state.current_time + max_wait_duration
            )

        # Calculate Wait Duration
        total_wait_duration = max(
            0.0, target_start_time - curr_state.current_time - nav_duration
        )

        log.debug(
            f"[_expand_wait_wo_monitoring] Check for {candidate.subtask.name}:\n"
            f"  Current Time: {curr_state.current_time:.2f}\n"
            f"  Target Start (Est): {target_start_time:.2f}\n"
            f"  Nav Duration: {nav_duration:.2f}\n"
            f"  -> Calculated Wait Duration: {total_wait_duration:.2f}"
        )

        if total_wait_duration <= EPSILON:
            log.debug(
                f"[_expand_wait_wo_monitoring] Total wait duration ({total_wait_duration:.2f}) is less than or equal to EPSILON. Skip waiting."
            )
            return None

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=total_wait_duration, type="Controllable"),
            repetition=1,
            subtask_type="WAIT",
            execution=Execution(
                objects=None, primitive_actions=[f"WAIT {total_wait_duration}"]
            ),
            temporal_constraints=None,
        )

        start_time = curr_state.current_time
        end_time = curr_state.current_time + total_wait_duration

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            schedule_start_time=start_time,
            schedule_end_time=end_time,
            schedule_nav_time=0.0,
            execution_status=True,
        )
        new_completed = curr_state.completed_entries + [completed_entry]

        new_state = SchedulerState(
            subtask=wait_sub,
            completed_entries=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            constraints=curr_state.constraints,
            current_time=end_time,
            scene_positions=curr_state.scene_positions,
            held_object=curr_state.held_object,
        )

        # Create a synthetic candidate to represent the 'Wait' action for the heuristic calculator.
        wait_candidate = Candidate(
            subtask=wait_sub,
            is_critical=candidate.is_critical,
            logical_interaction_start_time=candidate.logical_interaction_start_time,
            scheduling_due=candidate.scheduling_due,
        )

        # Global Risk Check을 위해 feasible_candidates도 포함하여 전달
        all_candidates = not_yet_candidates
        if feasible_candidates:
            all_candidates = feasible_candidates + not_yet_candidates

        step_risk, total_heuristic_cost = self.cost_calculator.calc_heuristic(
            curr_node,
            wait_candidate,
            all_candidates,
            # Wait action creates delay. We must check if this delay hurts ANY feasible or not_yet task.
        )
        # [Modified] HeuristicManager returns h(n) (Remaining Work + Debt).
        # We add end_time (g(n)) here to get the total cost f(n) = g(n) + h(n).
        new_cost = end_time + total_heuristic_cost

        # Accumulate max risk level
        new_risk = max(curr_node.risk_level, step_risk)

        log.info(
            f"[_expand_wait_wo_monitoring] {candidate.subtask.name}: end_time({end_time:.2f}) = current_time({curr_state.current_time:.2f}) + wait_duration({total_wait_duration:.2f})"
        )
        log.info(
            f"cost({new_cost:.2f}) = end_time({end_time:.2f}) + total_heuristic_cost({total_heuristic_cost:.2f})\n"
        )

        return SimulationNode(
            parent_node=curr_node,
            heuristic_cost=new_cost,
            depth=depth + 1,
            tie_breaker=next(self._counter),
            state=new_state,
            risk_level=new_risk,
        )
