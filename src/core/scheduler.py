import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.agent import Agent
from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager, NavigationManager
from scheduler.dataclass import CompletedEntry, SchedulerState, SimulationNode
from utils import BEAM_WIDTH, SIMULATION_DEPTH, create_module_logger
from utils.constants import (
    BAYESIAN_CRITERIA,
    GREEN,
    LOG_ROUND,
    MONITORING_DURATION,
    RESET,
)
from utils.task import get_monitoring_subtask
from utils.task.task_util import (
    make_early_subtask,
    make_monitoring_subtask,
    make_remain_subtask,
)

log = create_module_logger(module_name=__name__)


class Scheduler:

    def __init__(
        self,
        agent: Agent,
        beam_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):
        self.agent = agent
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.nav_manager = NavigationManager()
        self.constraint_handler = ConstraintHandler(self.nav_manager)
        self.cost_calculator = HeuristicManager(self.constraint_handler)

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(
        self,
        parent_state: SchedulerState,
    ) -> Optional[SchedulerState]:
        """Get the next state by running beam search from the given parent_state."""

        child_state = self._simulate_beam_search(parent_state)

        if child_state is None:
            log.error("[get_next_state] No child_state found (No feasible solution).")
            return None

        new_state = self._extract_state(parent_state, child_state)

        if new_state is None:
            log.error(
                f"[get_next_state] ChildState was found, but _extract_state returned None."
            )

        return new_state

    def _simulate_beam_search(
        self,
        init_state: SchedulerState,
    ) -> Optional[SchedulerState]:
        """Run a beam search from init_state to find the best next step."""

        queue = PriorityQueue()
        counter = itertools.count()

        init_node = SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=next(counter),
            state=init_state,
        )
        queue.put(init_node)
        best_solutions = []

        while not queue.empty():
            curr_node = queue.get()
            curr_state = curr_node.state
            curr_depth = curr_node.depth

            # 이미 탐색할 수 없거나 종료 조건에 도달했는지 확인
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                log.debug(
                    f"[_simulate_beam_search] Append to best_solutions: "
                    f"Remaining={len(curr_state.remaining_subtasks)}, Depth={curr_depth}\n"
                )
                best_solutions.append(curr_node)
                continue

            # 1) 현재 시점에 "즉시 실행 가능한" 서브태스크 찾기
            out_slot = self.constraint_handler.get_temporal_constraints(
                curr_state.subtask.name, curr_state.constraints, "out"
            )

            feasible_subs, not_yet_feasible_subs = (
                self.constraint_handler.get_feasible_subtasks(curr_node)
            )
            if len(feasible_subs) == 0 and len(not_yet_feasible_subs) == 0:
                # 해당 branch는 infeasible
                continue  # => 이 노드는 확장 안 하고 skip
            log.warning(
                f"========================================\n"
                f"[_simulate_beam_search]\n"
                f"Expanding Subtask={curr_state.subtask.name}\n"
                f"(Current Time : {round(curr_state.current_time,2)}, Out_{out_slot})\n\n"
                f"Feasible_subs={[sub.name for sub in feasible_subs]},\n"
                f"Not_yet_feasible_subs={[f'{sub[0].name}:{sub[1]}' for sub in not_yet_feasible_subs]}\n"
                f"==================================================\n"
            )

            # "early_sub" 직후라면 => monitoring_sub가 우선 실행
            if curr_state.pending_monitoring:
                log.warning(
                    f"[_simulate_beam_search]\npending_monitoring found: {curr_state.pending_monitoring.name}\n"
                )
                feasible_subs = [curr_state.pending_monitoring]
                not_yet_feasible_subs = []

            expanded_nodes: List[SimulationNode] = []
            # --- (2) 즉시 실행 가능한 각 서브태스크 확장 ---
            for candidate_sub in feasible_subs:
                log.debug(
                    f"[_simulate_beam_search] Expanding feasible_sub: {candidate_sub.name}\n"
                )
                if (
                    out_slot.is_critical
                    and not candidate_sub.decomposed
                    and not curr_node.state.subtask.decomposed
                ):
                    # time-critical인 경우 -> monitoring subtask으로 분할
                    new_node = self._expand_subtask_with_monitoring(
                        curr_node,
                        candidate_sub,
                        counter,
                    )
                else:
                    # time-critical이 아닌 경우 -> 일반적인 subtask 실행
                    new_node = self._expand_subtask_wo_monitoring(
                        curr_node,
                        candidate_sub,
                        counter,
                    )
                expanded_nodes.append(new_node)

            # (3) 아직 시작 시간이 되지 않은 서브태스크(not_yet_feasible_subs)에 대해, wait 고려
            for candidate_sub, earliest_start_time, is_critical in sorted(
                not_yet_feasible_subs, key=lambda x: x[1]
            ):
                log.debug(
                    f"[_simulate_beam_search] Expanding not_yet_feasible_sub: "
                    f"-{candidate_sub.name}, earliest={earliest_start_time}, isCritical={is_critical}\n"
                )
                if (
                    out_slot.is_critical
                    and not candidate_sub.decomposed
                    and not curr_node.state.subtask.decomposed
                ):
                    new_node = self._expand_wait_subtasks_with_monitoring(
                        curr_node, candidate_sub, counter, earliest_start_time
                    )
                else:
                    new_node = self._expand_wait_subtasks(
                        curr_node, candidate_sub, counter, earliest_start_time
                    )
                expanded_nodes.append(new_node)

            # --- (4) Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)
            for i, nd in enumerate(expanded_nodes):

                if i < self.beam_width:
                    queue.put(nd)
                else:
                    break

        if not best_solutions:
            log.error(
                "[_simulate_beam_search] best_solutions is empty -> No feasible\n"
            )
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        best_node = best_solutions[0]
        log.debug(
            f"[_simulate_beam_search] Found best_node with Subtask={best_node.state.subtask.name}, "
            f"Cost={best_node.heuristic_cost}\n"
        )
        return best_node.state

    def _extract_state(
        self, parent_state: SchedulerState, child_state: SchedulerState
    ) -> Optional[SchedulerState]:
        """
        beam search로 확장된 state(자식)에서 '새로 실행된 1-step'만 parent_state에 반영
        """
        if child_state is None:
            log.error("[_extract_state] child_state is None\n")
            return None

        parent_completed_set = {
            ce.subtask.name for ce in parent_state.completed_subtasks
        }
        child_plan = child_state.completed_subtasks

        new_entries = [
            ce for ce in child_plan if ce.subtask.name not in parent_completed_set
        ]

        log.debug(
            f"[_extract_state] new_entries={[entry.subtask.name for entry in new_entries]}, "
            f"child_state Subtask={child_state.subtask.name}\n"
        )

        if not new_entries:
            # 이미 완료된 것들만 존재하면 그대로 child_state를 반환
            log.debug("[_extract_state] No new entries -> returning child_state\n")
            return child_state

        # 새로 추가된 subtask 중 첫 번째 것만 가져옴
        new_entry = new_entries[0]
        new_subtask = new_entry.subtask
        new_completed_subtasks = parent_state.completed_subtasks + [new_entry]

        if not new_subtask.decomposed:
            new_constraints = parent_state.constraints
            new_remaining_subtasks = [
                r for r in parent_state.remaining_subtasks if r.name != new_subtask.name
            ]
        else:
            new_constraints = child_state.constraints
            additional_remaining_subtasks = [
                new_entry.subtask for new_entry in new_entries[1:]
            ]
            new_remaining_subtasks = []
            added_names = set()

            for new_completed_sub in new_completed_subtasks:
                added_names.add(new_completed_sub.subtask.name)

            # child_state.remaining_subtasks 중 중복되지 않는 값만
            for sub in child_state.remaining_subtasks:
                if sub.name not in added_names:
                    new_remaining_subtasks.append(sub)
                    added_names.add(sub.name)

            # 동시에 완료된 나머지 subtask
            for sub in additional_remaining_subtasks:
                if sub.name not in added_names:
                    new_remaining_subtasks.append(sub)
                    added_names.add(sub.name)

        if (
            parent_state.pending_monitoring is not None
            and new_subtask.name == parent_state.pending_monitoring.name
        ):
            next_pending_monitoring = None
        else:
            next_pending_monitoring = child_state.pending_monitoring

        next_state = SchedulerState(
            subtask=new_subtask,
            completed_subtasks=new_completed_subtasks,
            remaining_subtasks=new_remaining_subtasks,
            pending_monitoring=next_pending_monitoring,
            constraints=new_constraints,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )

        log.warning(
            f"{GREEN}========================================\n"
            f"[_extract_state]\n"
            f"- {new_subtask.name}\n"
            f"CompletedSubtasks={[ce.subtask.name for ce in new_completed_subtasks]},\n"
            f"Remaining={[r.name for r in new_remaining_subtasks]},\n"
            f"current_time={round(new_entry.end_time,LOG_ROUND)}\n"
            f"=================================================={RESET}\n"
        )

        return next_state

    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
    ) -> SimulationNode:
        """
        time-critical subtask -> early, monitoring, remain
        + DAG에서 ordering dependency: early -> mon -> remain
        + 첫 단계에서는 early_sub만 실행(1-step)
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_constraints = curr_state.constraints

        _, _, related_sub_name = self.constraint_handler.get_temporal_constraints(
            curr_state.subtask.name, curr_constraints, "out"
        )

        # 이동 시간
        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )

        subtask_start_time = curr_state.current_time
        subtask_end_time = (
            subtask_start_time + candidate_sub.duration.interval + nav_time
        )

        monitoring_timing = (
            subtask_start_time
            + (nav_time + candidate_sub.duration.interval) * BAYESIAN_CRITERIA
        )

        log.debug(
            f"[_expand_subtask_with_monitoring]\nSubtask={candidate_sub.name}, "
            f"\nnav_time={nav_time}, start={subtask_start_time}, end={subtask_end_time}, "
            f"\nmonitoring_timing={monitoring_timing}\n"
        )

        new_constraints = copy.deepcopy(curr_constraints)
        if new_constraints.has_node(candidate_sub.name):
            new_constraints.remove_node(candidate_sub.name)

        early_dur = monitoring_timing - subtask_start_time
        remain_dur = subtask_end_time - monitoring_timing

        early_sub = make_early_subtask(candidate_sub, early_dur)
        mon_sub = make_monitoring_subtask(related_sub_name)
        remain_sub = make_remain_subtask(candidate_sub, remain_dur)

        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        new_constraints.add_edge(
            early_sub.name, mon_sub.name, info={"Interval": 0, "IsCritical": True}
        )
        new_constraints.add_edge(
            mon_sub.name, remain_sub.name, info={"Interval": 0, "IsCritical": False}
        )

        in_edges = curr_constraints.in_edges(candidate_sub.name, data=True)
        out_edges = curr_constraints.out_edges(candidate_sub.name, data=True)

        for pred, _, data in in_edges:
            new_constraints.add_edge(pred, early_sub.name, info=data.get("info", {}))
        for _, succ, data in out_edges:
            new_constraints.add_edge(remain_sub.name, succ, info=data.get("info", {}))

        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate_sub.name
        ]
        new_remaining.append(mon_sub)
        new_remaining.append(remain_sub)

        # early_sub 실행
        start_time = curr_state.current_time
        end_time = start_time + early_sub.duration.interval
        step_cost = self.cost_calculator.calc_heuristic_cost(
            curr_node, early_sub, nav_time
        )
        new_cost = curr_heuristic + step_cost

        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        log.info(
            f"[_expand_subtask_with_monitoring]\n"
            f"*{early_sub.name}\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(early_sub.duration.interval,LOG_ROUND)})\n"
            f"Heuristic = {round(new_cost,LOG_ROUND)}\n"
        )

        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            pending_monitoring=mon_sub,
            constraints=new_constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: int,
    ) -> SimulationNode:
        """Subtask 1개에 포함된 기존 primitive action 전체를 수행하는 노드 확장."""
        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )
        exec_time = candidate_sub.duration.interval + nav_time
        start_time = curr_state.current_time
        end_time = start_time + exec_time

        copied_sub = copy.deepcopy(candidate_sub)
        copied_sub.duration.interval = exec_time

        new_heuristic_cost = self.cost_calculator.calc_heuristic_cost(
            curr_node, candidate_sub, nav_time
        )
        new_cost = curr_heuristic + new_heuristic_cost

        completed_entry = CompletedEntry(
            subtask=copied_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate_sub.name
        ]

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            pending_monitoring=None,
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_subtask_wo_monitoring]\n"
            f"*{candidate_sub.name}\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(exec_time,LOG_ROUND)})\n"
            f"Heuristic = {round(new_cost,LOG_ROUND)}\n"
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _expand_wait_subtasks_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
        earliest_start_time: float,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 서브태스크에 대해
        1) 일반 Wait
        2) time-critical이면 모니터링 시점에 맞춘 partial Wait
        """
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_constraints = curr_state.constraints

        _, _, related_sub_name = self.constraint_handler.get_temporal_constraints(
            curr_state.subtask.name, curr_constraints, "out"
        )

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )

        monitoring_timing = (
            curr_state.current_time
            + (earliest_start_time - curr_state.current_time) * BAYESIAN_CRITERIA
        )
        wait_duration = (
            monitoring_timing - curr_state.current_time - MONITORING_DURATION
        )

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate_sub.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None, primitive_actions=[f"Wait {wait_duration}"]
            ),
            temporal_constraints=None,
        )

        mon_sub = make_monitoring_subtask(related_sub_name)

        start_time = curr_state.current_time
        end_time = start_time + wait_sub.duration.interval
        step_cost = self.cost_calculator.calc_heuristic_cost(curr_node, wait_sub, 0)
        new_cost = curr_heuristic + step_cost

        completed_entry = CompletedEntry(
            subtask=wait_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_remaining = curr_state.remaining_subtasks + [mon_sub]
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            pending_monitoring=mon_sub,
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_wait_subtasks_with_monitoring]\n"
            f"*{wait_sub.name} (earliest_start={round(earliest_start_time,LOG_ROUND)})\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(wait_duration,LOG_ROUND)})\n"
            f"Heuristic = {round(new_cost,LOG_ROUND)}\n"
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _expand_wait_subtasks(
        self,
        curr_node: SimulationNode,
        candidate_sub: Subtask,
        counter: itertools.count,
        earliest_start_time: float,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 Subtask에 대해
        'Wait Subtask'를 생성하여 해당 시간을 대기하는 노드를 확장
        """
        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate_sub
        )
        wait_start_time = curr_state.current_time
        wait_duration = earliest_start_time - curr_state.current_time

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate_sub.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None, primitive_actions=[f"Wait {wait_duration}"]
            ),
            temporal_constraints=None,
        )

        new_completed = curr_state.completed_subtasks + [
            CompletedEntry(
                subtask=wait_sub,
                start_time=curr_state.current_time,
                end_time=curr_state.current_time + wait_duration,
            )
        ]
        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=curr_state.remaining_subtasks,
            pending_monitoring=None,
            constraints=curr_state.constraints,
            current_time=curr_state.current_time + wait_duration,
            agent_location=new_location,
        )

        cost_for_wait = self.cost_calculator.calc_heuristic_cost(curr_node, wait_sub, 0)
        new_cost = curr_heuristic + cost_for_wait

        log.info(
            f"[_expand_wait_subtasks]\n"
            f"*{wait_sub.name} (earliest_start={round(earliest_start_time,LOG_ROUND)})\n"
            f"Interval = {round(wait_start_time,LOG_ROUND)} ~ {round(wait_start_time+wait_duration,LOG_ROUND)} ({round(wait_duration,LOG_ROUND)})\n"
            f"Heuristic = {round(new_cost,LOG_ROUND)}\n"
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node


# TODO 왜 pending Monitoring이 누락되지?
