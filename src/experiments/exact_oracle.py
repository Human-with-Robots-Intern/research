"""Exact deterministic oracle baseline for offline scheduling experiments."""

from __future__ import annotations

import copy
import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from src.core.scheduler import Scheduler
from src.models.dataclass import (
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from src.scheduler import ActionHandler, ConstraintHandler, HeuristicManager
from src.utils.common import create_module_logger
from src.utils.config import constants
from src.utils.io_utils.result_saver import serialize_completed_entries

log = create_module_logger(__name__, module_log=True)


@dataclass(frozen=True)
class OracleSolution:
    """Container for a deterministic oracle solve result.

    Args:
        instruction: Instruction file name solved by the oracle.
        case: Case identifier for the instruction.
        optimal_schedule_time: Best deterministic makespan found by the solver.
        optimal_sequence: Best deterministic action sequence, including explicit
            wait subtasks chosen by the oracle.
        solve_time: Wall-clock time spent in the oracle solver.
        search_nodes: Number of DFS nodes explored.
        pruned_nodes: Number of nodes pruned by incumbent bounds.
        idle_advances: Number of implicit idle advances performed.
        exact: Whether the result is provably exact.
        timeout_hit: Whether the search stopped because of a time limit.
        completed_entries: Scheduled entries for the best solution branch.
    """

    instruction: str
    case: str
    optimal_schedule_time: Optional[float]
    optimal_sequence: list[str]
    solve_time: float
    search_nodes: int
    pruned_nodes: int
    idle_advances: int
    exact: bool
    timeout_hit: bool
    completed_entries: list[CompletedEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""

        return {
            "instruction": self.instruction,
            "case": self.case,
            "optimal_schedule_time": self.optimal_schedule_time,
            "final_schedule_time": self.optimal_schedule_time,
            "optimal_sequence": list(self.optimal_sequence),
            "solve_time": self.solve_time,
            "total_compute_time": self.solve_time,
            "search_nodes": self.search_nodes,
            "pruned_nodes": self.pruned_nodes,
            "idle_advances": self.idle_advances,
            "exact": self.exact,
            "timeout_hit": self.timeout_hit,
            "steps": serialize_completed_entries(self.completed_entries),
        }


class DeterministicExactOracle:
    """Explore deterministic schedules with exhaustive DFS and branch-and-bound.

    This oracle intentionally excludes monitoring and online belief updates.
    It reuses the project's action simulation and candidate feasibility logic
    so the comparison stays aligned with the scheduler's deterministic
    execution semantics. Under the current relaxed, EDF-like comparison mode,
    timing misses do not invalidate a branch during oracle search; the oracle
    solves for the best makespan over executable schedules and leaves timing
    quality to post-hoc TCSR reporting.
    """

    def __init__(
        self,
        action_handler: ActionHandler,
        constraint_handler: ConstraintHandler,
        heuristic_manager: HeuristicManager,
        *,
        time_limit_seconds: float,
    ) -> None:
        """Initialize the oracle solver.

        Args:
            action_handler: Shared deterministic action simulator.
            constraint_handler: Feasibility checker for subtasks.
            heuristic_manager: Passed through to the internal Scheduler for
                state-expansion mechanics; not used by the oracle search itself.
            time_limit_seconds: Maximum allowed solve time per instruction.
        """

        self.action_handler = action_handler
        self.constraint_handler = constraint_handler
        self.heuristic_manager = heuristic_manager
        self.time_limit_seconds = float(time_limit_seconds)
        self.scheduler = Scheduler(
            action_handler=action_handler,
            constraint_handler=constraint_handler,
            heuristic_manager=heuristic_manager,
            monitoring_policy=None,
            beam_width=1,
            simulation_depth=1,
        )
        self._deadline_monotonic_tolerance = float(constants.EPSILON)
        self._strict_timing_epsilon = 1e-6
        self._best_makespan: Optional[float] = None
        self._incumbent_upper_bound: Optional[float] = None
        self._best_sequence: list[str] = []
        self._best_completed_entries: list[CompletedEntry] = []
        self._search_nodes = 0
        self._pruned_nodes = 0
        self._idle_advances = 0
        self._timeout_hit = False
        self._started_at = 0.0

    def solve(
        self,
        initial_state: SchedulerState,
        *,
        instruction: str,
        case: str,
        incumbent_upper_bound: Optional[float] = None,
    ) -> OracleSolution:
        """Solve the deterministic initial schedule exactly when possible.

        Args:
            initial_state: Initial scheduler state for the instruction.
            instruction: Instruction file name used in reporting.
            case: Case identifier used in reporting.
            incumbent_upper_bound: Optional initial upper bound from an existing
                scheduler rollout to accelerate pruning.

        Returns:
            OracleSolution containing the best schedule found and exactness flags.
        """

        self._best_makespan = None
        self._incumbent_upper_bound = (
            float(incumbent_upper_bound) if incumbent_upper_bound is not None else None
        )
        self._best_sequence = []
        self._best_completed_entries = []
        self._search_nodes = 0
        self._pruned_nodes = 0
        self._idle_advances = 0
        self._timeout_hit = False
        self._started_at = time.perf_counter()
        root_node = SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=0,
            parent_node=None,
            state=initial_state,
            risk_level=0,
        )

        self.scheduler._begin_search_session()
        try:
            self._search(root_node, ())
        finally:
            self.scheduler._end_search_session()

        solve_time = time.perf_counter() - self._started_at
        return OracleSolution(
            instruction=instruction,
            case=case,
            optimal_schedule_time=self._best_makespan,
            optimal_sequence=self._best_sequence,
            solve_time=solve_time,
            search_nodes=self._search_nodes,
            pruned_nodes=self._pruned_nodes,
            idle_advances=self._idle_advances,
            exact=(not self._timeout_hit and self._best_makespan is not None),
            timeout_hit=self._timeout_hit,
            completed_entries=copy.deepcopy(self._best_completed_entries),
        )

    def _search(self, node: SimulationNode, sequence: tuple[str, ...]) -> None:
        """Depth-first branch-and-bound search over deterministic schedules.

        Branching is heuristic-free: every feasible candidate is explored in
        neutral (name-sorted) order, and an idle-advance branch toward the next
        release time is always considered alongside immediate execution — not
        only as a fallback.  This ensures the oracle is independent of the
        scheduling heuristic used during online execution.

        Args:
            node: Current deterministic scheduler state.
            sequence: Executed deterministic action sequence.
        """

        if self._timeout_hit:
            return
        if (time.perf_counter() - self._started_at) >= self.time_limit_seconds:
            self._timeout_hit = True
            return

        # NOTE: risk_level is intentionally NOT used for oracle pruning.
        # Scheduler risk is a search aid and can diverge from the oracle's
        # branch semantics because it depends on partial lookahead/reservations.
        # In the current relaxed comparison mode, timing misses remain
        # executable and are scored post-hoc via TCSR rather than rejected
        # during search. The oracle therefore prunes only by branch-and-bound
        # makespan and the time limit.
        current_time = float(node.state.current_time)
        incumbent_bound = (
            self._best_makespan
            if self._best_makespan is not None
            else self._incumbent_upper_bound
        )
        if (
            incumbent_bound is not None
            and current_time > incumbent_bound + self._deadline_monotonic_tolerance
        ):
            self._pruned_nodes += 1
            return

        self._search_nodes += 1
        if not node.state.remaining_subtasks:
            if not self._is_terminal_schedule_valid(node.state):
                self._pruned_nodes += 1
                return
            self._commit_solution(current_time, sequence, node.state.completed_entries)
            return

        feasible_candidates, not_yet_candidates = (
            self.constraint_handler.get_feasible_candidates(node)
        )
        reserved_candidate_name = self.scheduler._get_reserved_prenavigation_candidate_name(
            node
        )
        feasible_candidates, not_yet_candidates = (
            self.scheduler._apply_reserved_prenavigation_filter(
                node,
                feasible_candidates,
                not_yet_candidates,
            )
        )

        # Branch A: for each feasible candidate, explore an explicit
        # conflict-avoidance WAIT branch (when one exists) and then the
        # immediate execution branch. This keeps oracle branching aligned with
        # the scheduler's deterministic search space, where a currently
        # feasible task may still benefit from a small delay before starting.
        for candidate in self._order_candidates(node, feasible_candidates):
            if self._is_critical_deadline_violated(node, candidate):
                self._pruned_nodes += 1
                continue
            wait_node = self._expand_feasible_conflict_avoidance_wait(
                node,
                candidate,
                feasible_candidates,
                not_yet_candidates,
            )
            if wait_node is not None:
                self._search(wait_node, sequence + (wait_node.state.subtask.name,))
                if self._timeout_hit:
                    return
            child_node = self.scheduler._expand_subtask_wo_monitoring(
                node,
                candidate,
                not_yet_candidates,
                feasible_candidates,
            )
            if child_node is None:
                continue
            self._search(child_node, sequence + (child_node.state.subtask.name,))
            if self._timeout_hit:
                return

        # Branch B: blocked-candidate branches (WAIT and early PRENAV).
        if not_yet_candidates:
            for blocked_candidate in self._order_blocked_candidates(not_yet_candidates):
                prenav_node = self._expand_blocked_prenavigation(
                    node,
                    blocked_candidate,
                    feasible_candidates,
                    not_yet_candidates,
                )
                if prenav_node is not None:
                    self._search(
                        prenav_node,
                        sequence + (prenav_node.state.subtask.name,),
                    )
                    if self._timeout_hit:
                        return

                wait_node = self._expand_blocked_wait(
                    node,
                    blocked_candidate,
                    feasible_candidates,
                    not_yet_candidates,
                )
                if wait_node is not None:
                    self._search(wait_node, sequence + (wait_node.state.subtask.name,))
                    if self._timeout_hit:
                        return

        # Branch C: pre-task strategic delay for feasible non-critical candidates.
        # When a non-critical task is feasible now but starting it immediately would
        # cause a parallel timing constraint to expire in a tight window, it can be
        # better to idle until a pending critical deadline and only then start the
        # non-critical work.  Branch A never discovers this because it always tries
        # immediate execution; Branch B only waits for *blocked* candidates.
        # Branch C closes the gap by generating one "wait-until-LIT" node per
        # distinct future critical LIT, allowing the oracle to explore schedules
        # where non-critical tasks are deliberately deferred.
        if not reserved_candidate_name:
            for delay_until in self._collect_pretask_delay_targets(
                current_time, feasible_candidates, not_yet_candidates
            ):
                wait_node = self._expand_pretask_delay_wait(
                    node, delay_until, feasible_candidates, not_yet_candidates
                )
                if wait_node is not None:
                    self._search(wait_node, sequence + (wait_node.state.subtask.name,))
                    if self._timeout_hit:
                        return

        # Dead-end: no feasible candidates and no future releases.
        if not feasible_candidates and not not_yet_candidates:
            return

    def _commit_solution(
        self,
        makespan: float,
        sequence: Sequence[str],
        completed_entries: Sequence[CompletedEntry],
    ) -> None:
        """Update the incumbent solution when a better or equal solution is found.

        Using ``<=`` rather than ``<`` ensures the sequence is recorded even when
        the oracle starts with an external incumbent equal to the optimal value.

        Args:
            makespan: Completed makespan for the candidate solution.
            sequence: Executed subtask names on the winning branch.
            completed_entries: Scheduled entries associated with the branch.
        """

        if self._best_makespan is None or makespan <= self._best_makespan:
            self._best_makespan = makespan
            self._best_sequence = list(sequence)
            self._best_completed_entries = copy.deepcopy(list(completed_entries))
        if (
            self._incumbent_upper_bound is None
            or makespan < self._incumbent_upper_bound
        ):
            self._incumbent_upper_bound = makespan

    def _is_terminal_schedule_valid(self, state: SchedulerState) -> bool:
        """Return whether the completed branch is executable.

        Oracle search now follows relaxed late-continue semantics to stay
        comparable with EDF-like baselines and the scheduler's current
        execution behavior. Completed schedules are therefore not rejected for
        timing misses here; TCSR is computed later for reporting.
        """

        _ = state
        return True

    def _is_critical_deadline_violated(
        self,
        node: SimulationNode,
        candidate: Candidate,
    ) -> bool:
        """Return whether a candidate must be pruned for timing lateness.

        Under relaxed late-continue semantics, no executable candidate is
        removed solely because it has become late relative to a critical
        timing target. Timing quality is evaluated after rollout via TCSR.
        """

        _ = node, candidate
        return False

    def _is_monitoring_edge(self, predecessor_name: str, successor_name: str) -> bool:
        """Return True when either endpoint belongs to a monitoring-only edge."""

        return predecessor_name.lower().startswith(
            "monitoring"
        ) or successor_name.lower().startswith("monitoring")

    def _read_constraint_info(
        self,
        edge_data: dict[str, Any],
    ) -> tuple[float, bool]:
        """Extract the interval and critical flag from a constraint edge."""

        info = edge_data.get("info", {})
        return float(info.get("Interval", 0.0)), bool(info.get("IsCritical", False))

    def _get_schedule_interaction_start(self, entry: CompletedEntry) -> float:
        """Return the scheduled interaction-start timestamp for an entry."""

        return float(entry.schedule_start_time) + float(entry.schedule_nav_time or 0.0)

    def _order_candidates(
        self,
        curr_node: SimulationNode,
        feasible_candidates: Sequence[Candidate],
    ) -> list[Candidate]:
        """Return candidates in a heuristic-free, deterministic order.

        Sorting by name alone ensures the oracle explores branches in a fixed,
        reproducible sequence without importing any scheduling heuristic.  The
        branch-and-bound incumbent bound still prunes dominated branches, so
        the order affects efficiency but not correctness.

        Args:
            curr_node: Current deterministic search node (unused; kept for API
                compatibility).
            feasible_candidates: Immediately executable candidates.

        Returns:
            Candidate list sorted lexicographically by subtask name.
        """

        return sorted(feasible_candidates, key=lambda c: c.subtask.name)

    def _order_blocked_candidates(
        self,
        not_yet_candidates: Sequence[Candidate],
    ) -> list[Candidate]:
        """Return blocked candidates on the scheduler's earliest timing frontier."""

        return self.scheduler._get_blocked_candidate_frontier(list(not_yet_candidates))

    def _expand_blocked_wait(
        self,
        node: SimulationNode,
        candidate: Candidate,
        feasible_candidates: Sequence[Candidate],
        not_yet_candidates: Sequence[Candidate],
    ) -> Optional[SimulationNode]:
        """Create an explicit WAIT successor for one blocked candidate.

        Args:
            node: Current deterministic search node.
            candidate: Blocked candidate to wait for.
            feasible_candidates: Immediately executable candidates.
            not_yet_candidates: Candidates blocked only by timing/readiness.

        Returns:
            WAIT child node, or ``None`` when no useful wait exists.
        """

        wait_node = self.scheduler._expand_single_wait(
            node,
            candidate,
            list(not_yet_candidates),
            feasible_candidates=list(feasible_candidates),
        )
        if wait_node is not None:
            self._idle_advances += 1
        return wait_node

    def _expand_blocked_prenavigation(
        self,
        node: SimulationNode,
        candidate: Candidate,
        feasible_candidates: Sequence[Candidate],
        not_yet_candidates: Sequence[Candidate],
    ) -> Optional[SimulationNode]:
        """Create an early NAV-only successor for a blocked candidate."""

        return self.scheduler._expand_blocked_prenavigation(
            node,
            candidate,
            list(not_yet_candidates),
            feasible_candidates=list(feasible_candidates),
        )

    def _expand_feasible_conflict_avoidance_wait(
        self,
        node: SimulationNode,
        candidate: Candidate,
        feasible_candidates: Sequence[Candidate],
        not_yet_candidates: Sequence[Candidate],
    ) -> Optional[SimulationNode]:
        """Create an explicit WAIT successor for a feasible future-conflicting step.

        The scheduler can deliberately delay a currently feasible candidate by a
        small amount when immediate execution would collide with a reserved
        future critical window. The oracle must branch on the same explicit
        wait to preserve search-space parity with the scheduler.
        """

        if node.state.constraints is None:
            return None

        conflict_delay, _ = self.scheduler.cost_calculator.check_future_conflict(
            node,
            candidate,
        )
        if float(conflict_delay) <= constants.EPSILON:
            return None

        nav_duration = self.scheduler._estimate_candidate_navigation_duration(
            node,
            candidate,
        )
        wait_node = self.scheduler._expand_wait_wo_monitoring(
            node,
            candidate,
            list(not_yet_candidates),
            nav_duration=nav_duration,
            feasible_candidates=list(feasible_candidates),
            additional_delay=float(conflict_delay),
        )
        if wait_node is not None:
            self._idle_advances += 1
        return wait_node

    def _collect_pretask_delay_targets(
        self,
        current_time: float,
        feasible_candidates: Sequence[Candidate],
        not_yet_candidates: Sequence[Candidate],
    ) -> list[float]:
        """Return distinct future critical LITs worth waiting for in Branch C.

        Only returns targets when there is at least one feasible non-critical
        candidate (otherwise there is nothing to delay).  Targets are the
        ``logical_interaction_start_time`` values of all critical candidates
        (both feasible and not-yet) that lie strictly in the future.

        Args:
            current_time: Current DFS time.
            feasible_candidates: Immediately executable candidates.
            not_yet_candidates: Candidates blocked by timing or readiness.

        Returns:
            Sorted list of distinct delay target times.
        """
        has_non_critical_feasible = any(
            not c.is_critical for c in feasible_candidates
        )
        if not has_non_critical_feasible:
            return []

        targets: set[float] = set()
        for c in list(feasible_candidates) + list(not_yet_candidates):
            if not c.is_critical:
                continue
            lit = c.logical_interaction_start_time
            if lit is not None and lit > current_time + constants.EPSILON:
                targets.add(float(lit))

        return sorted(targets)

    def _expand_pretask_delay_wait(
        self,
        node: SimulationNode,
        delay_until: float,
        feasible_candidates: Sequence[Candidate],
        not_yet_candidates: Sequence[Candidate],
    ) -> Optional[SimulationNode]:
        """Create a free idle-wait node that advances time to delay_until.

        Uses the first feasible non-critical candidate as a vehicle for
        ``_expand_wait_wo_monitoring`` with ``nav_duration=0`` so the wait is
        a pure time advance with no implied navigation.  All remaining tasks
        are preserved unchanged; the DFS continues normally from delay_until.

        Args:
            node: Current DFS node.
            delay_until: Target time to advance to (a critical task's LIT).
            feasible_candidates: Immediately executable candidates.
            not_yet_candidates: Candidates blocked by timing or readiness.

        Returns:
            Wait node with ``current_time == delay_until``, or ``None``.
        """
        vehicle = next(
            (c for c in feasible_candidates if not c.is_critical), None
        )
        if vehicle is None:
            return None

        delayed_vehicle = dataclasses.replace(
            vehicle, actual_interaction_start_time=delay_until
        )
        wait_node = self.scheduler._expand_wait_wo_monitoring(
            node,
            delayed_vehicle,
            list(not_yet_candidates),
            nav_duration=0.0,
            feasible_candidates=list(feasible_candidates),
        )
        if wait_node is not None:
            self._idle_advances += 1
        return wait_node


def build_scheduler_state_after_subtask(
    curr_node: SimulationNode,
    candidate: Candidate,
    action_handler: ActionHandler,
) -> Optional[SchedulerState]:
    """Build the next deterministic scheduler state for a concrete subtask.

    Args:
        curr_node: Current scheduler node.
        candidate: Candidate subtask to execute.
        action_handler: Deterministic action simulator.

    Returns:
        Next scheduler state, or ``None`` when simulation fails.
    """

    action_info = action_handler.get_actions_info(
        curr_node,
        candidate.subtask.execution.primitive_actions,
    )
    if action_info is None or not action_info.success:
        return None

    planned_nav_start_time = curr_node.state.current_time
    completion_time = planned_nav_start_time + action_info.cumulative_time
    copied_subtask = copy.deepcopy(candidate.subtask)
    copied_subtask.duration.total_time = action_info.cumulative_time
    completed_entry = CompletedEntry(
        subtask=copied_subtask,
        schedule_start_time=planned_nav_start_time,
        schedule_end_time=completion_time,
        schedule_nav_time=action_info.first_nav_duration,
        execution_status=bool(action_info.success),
    )
    remaining_subtasks = [
        remaining
        for remaining in curr_node.state.remaining_subtasks
        if remaining.name != candidate.subtask.name
    ]
    return SchedulerState(
        subtask=copied_subtask,
        completed_entries=curr_node.state.completed_entries + [completed_entry],
        remaining_subtasks=remaining_subtasks,
        constraints=curr_node.state.constraints,
        current_time=completion_time,
        scene_positions=action_info.scene_positions,
        held_object=action_info.held_object,
    )


def build_initial_oracle_upper_bound(
    current_best: Optional[float],
) -> Optional[float]:
    """Normalize an optional incumbent upper bound for the oracle.

    Args:
        current_best: Existing deterministic scheduler makespan, if available.

    Returns:
        Floating-point incumbent upper bound or ``None``.
    """

    if current_best is None:
        return None
    return float(current_best)
