import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

from core.task import Duration, Execution, Subtask
from scheduler import ConstraintHandler, HeuristicManager, NavigationManager
from scheduler.dataclass import (
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from utils import BEAM_WIDTH, SIMULATION_DEPTH, create_module_logger
from utils.constants import (
    BAYESIAN_CRITERIA,
    GREEN,
    LOG_ROUND,
    MONITORING_DURATION,
    RED,
    RESET,
)
from utils.task.task_util import (
    make_early_subtask,
    make_monitoring_subtask,
    make_remain_subtask,
)

log = create_module_logger(module_name=__name__, is_file_handler=True)


class Scheduler:

    def __init__(
        self,
        beam_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):

        self.beam_width = beam_width
        self.simulation_depth = simulation_depth
        log.info(f"{RED}{beam_width=}, {simulation_depth=}{RESET}")

        self.nav_manager = NavigationManager()
        self.constraint_handler = ConstraintHandler()
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
            expanded_nodes: List[SimulationNode] = []

            curr_node = queue.get()
            curr_state, curr_depth = curr_node.state, curr_node.depth
            curr_out_slot = self.constraint_handler.get_time_slots(
                curr_state.subtask.name, curr_state.constraints, "out"
            )

            # 이미 탐색할 수 없거나 종료 조건에 도달했는지 확인
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 1) 현재 시점에 "실행 가능한" 서브태스크 찾기
            # subtask, earliest_start, is_critical 반환
            feasible_candidate, not_yet_feasible_candidate = (
                self.constraint_handler.get_feasible_candidates(curr_node)
            )

            if len(feasible_candidate) == 0 and len(not_yet_feasible_candidate) == 0:
                # 해당 branch는 infeasible
                continue  # => 이 노드는 확장 안 하고 skip

            log.warning(
                f"========================================\n"
                f"Depth = {curr_depth+1} / Current Time : {round(curr_state.current_time,2)}\n"
                f"Completed_subs ={[ce.subtask.name for ce in curr_state.completed_subtasks]}\n"
                f"Remaining_subs ={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[candidate for candidate in feasible_candidate]},\n"
                f"Not_yet_feasible_subs={[candidate for candidate in not_yet_feasible_candidate]}\n"
                f"==================================================\n"
            )

            # --- (2) 즉시 실행 가능한 각 서브태스크 확장 ---
            for candidate in feasible_candidate:
                if (
                    curr_out_slot.is_critical
                    and not curr_node.state.subtask.decomposed
                    and not candidate.subtask.decomposed
                ):
                    # 직전 subtask가 time-critical을 시작하는 경우 -> monitoring subtask으로 분할
                    new_node = self._expand_subtask_with_monitoring(
                        curr_node,
                        candidate,
                        counter,
                    )
                else:
                    # 직전 subtask가 time-critical을 시작하지 않는 경우 -> 일반적인 subtask 실행
                    new_node = self._expand_subtask_wo_monitoring(
                        curr_node,
                        candidate,
                        counter,
                    )
                expanded_nodes.append(new_node)

            # (3) 아직 시작 시간이 되지 않은 서브태스크(not_yet_feasible_subs)에 대해, wait 고려

            for candidate in not_yet_feasible_candidate:
                if (
                    curr_out_slot.is_critical
                    and not candidate.subtask.decomposed
                    and not curr_node.state.subtask.decomposed
                ):
                    # 모니터링 직전까지 대기 추가
                    new_node = self._expand_wait_subtask_for_monitoring(
                        curr_node, candidate, counter
                    )
                else:
                    # 모니터링 직후 혹은 일반적인 대기 추가
                    new_node = self._expand_wait_subtask(curr_node, candidate, counter)
                expanded_nodes.append(new_node)

            # --- (4) Local Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
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
        # ! Roll-back 잘 되고 있는지 보기!
        if child_state is None:
            log.error("[_extract_state] child_state is None\n")
            return None

        parent_completed = [ce for ce in parent_state.completed_subtasks]
        child_completed = [ce for ce in child_state.completed_subtasks]
        new_entries = child_completed[len(parent_completed) :]

        if not new_entries:
            # 이미 완료된 것들만 존재하면 그대로 child_state를 반환
            log.debug("[_extract_state] No new entries -> returning child_state\n")
            return child_state

        # 새로 추가된 subtask 중 첫 번째 것만 가져옴
        new_entry = new_entries[0]
        new_completed_schedule = parent_state.completed_subtasks + [new_entry]
        new_subtask = new_entry.subtask

        if not new_subtask.decomposed:
            # 동적으로 Wait, Monitoring 생성된 경우
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

            for new_completed_sub in new_completed_schedule:
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

        next_state = SchedulerState(
            subtask=new_subtask,
            completed_subtasks=new_completed_schedule,
            remaining_subtasks=new_remaining_subtasks,
            constraints=new_constraints,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )

        return next_state

    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        counter: itertools.count,
    ) -> SimulationNode:
        """
        time-critical subtask -> early, monitoring, remain
        + DAG에서 ordering dependency: early -> mon -> remain
        + 첫 단계에서는 early_sub만 실행(1-step)
        """
        # ! 이 부분에서, Monitoring이 등장하는 Path에만 Remain이 등장해야 하지, 다른 Path에는 Remain이 등장하면 안됨.
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_constraints = curr_state.constraints

        early_sub, mon_sub, remain_sub, new_constraints = (
            self._decompose_sub_by_monitoring(curr_node, candidate)
        )

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate.subtask
        )

        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate.subtask.name
        ]
        new_remaining.append(mon_sub)
        new_remaining.append(remain_sub)

        # early_sub 실행
        start_time = curr_state.current_time
        end_time = start_time + early_sub.duration.interval

        early_candidate = Candidate(
            subtask=early_sub,
            earliest_start_time=candidate.earliest_start_time,  # 실행 즉시 시작
            is_critical=candidate.is_critical,
        )

        # ! Monitoring을 위한 Early Subtask 소요 시간은 아는데, 이동 시간 포함하여 계산할 수 있나? 어긋 날수도...?
        # ! 0.7 Bayesian Timing에 아직 Navigate 중 일수도 있잖아...
        step_cost = self.cost_calculator.calc_heuristic(curr_node, early_candidate, 0)

        new_cost = curr_heuristic + step_cost

        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        log.info(
            f"[_expand_subtask_with_monitoring]\n"
            f"*{early_sub.name}, Score = {round(new_cost,LOG_ROUND)}\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(early_sub.duration.interval,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in new_remaining]}\n"
        )

        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
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

    # Helper function for _expand_subtask_with_monitoring
    def _decompose_sub_by_monitoring(
        self, curr_node: SimulationNode, candidate: Candidate
    ):
        # TODO Monitoring으로 분할될 때, Primitive Action 해결하기
        # TODO 모니터링에서 바라볼 오브젝트

        curr_state = curr_node.state
        curr_constraints = curr_state.constraints
        obj = curr_state.subtask.execution.primitive_actions[-1].split(" ")[-1]
        _, _, related_sub_name = self.constraint_handler.get_time_slots(
            curr_state.subtask.name, curr_constraints, "out"
        )

        # 이동 시간
        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate.subtask
        )

        subtask_start_time = curr_state.current_time
        subtask_end_time = (
            subtask_start_time + candidate.subtask.duration.interval + nav_time
        )

        monitoring_timing = (
            subtask_start_time
            + (nav_time + candidate.subtask.duration.interval) * BAYESIAN_CRITERIA
        )

        new_constraints = copy.deepcopy(curr_constraints)

        if new_constraints.has_node(candidate.subtask.name):
            new_constraints.remove_node(candidate.subtask.name)

        early_dur = round(monitoring_timing - subtask_start_time, LOG_ROUND)
        remain_dur = round(subtask_end_time - monitoring_timing, LOG_ROUND)

        early_sub = make_early_subtask(candidate.subtask, early_dur)
        mon_sub = make_monitoring_subtask(related_sub_name, obj)
        remain_sub = make_remain_subtask(candidate.subtask, remain_dur)

        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        new_constraints.remove_edge(curr_node.state.subtask.name, related_sub_name)
        new_constraints.add_edge(
            curr_node.state.subtask.name,
            mon_sub.name,
            info={"Interval": early_dur, "IsCritical": True},
        )
        new_constraints.add_edge(
            mon_sub.name,
            related_sub_name,
            info={"Interval": remain_dur, "IsCritical": True},
        )
        new_constraints.add_edge(
            early_sub.name,
            remain_sub.name,
            info={
                "Interval": monitoring_timing
                - subtask_start_time
                + MONITORING_DURATION,
                "IsCritical": False,
            },
        )

        in_edges = curr_constraints.in_edges(candidate.subtask.name, data=True)
        out_edges = curr_constraints.out_edges(candidate.subtask.name, data=True)

        for pred, _, data in in_edges:
            new_constraints.add_edge(pred, early_sub.name, info=data.get("info", {}))
        for _, succ, data in out_edges:
            new_constraints.add_edge(remain_sub.name, succ, info=data.get("info", {}))
        return early_sub, mon_sub, remain_sub, new_constraints

    def _expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        counter: int,
    ) -> SimulationNode:
        """Subtask 1개에 포함된 기존 primitive action 전체를 수행하는 노드 확장."""
        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate.subtask
        )
        exec_time = candidate.subtask.duration.interval + nav_time
        start_time = curr_state.current_time
        end_time = start_time + exec_time

        copied_sub = copy.deepcopy(candidate.subtask)
        copied_sub.duration.interval = exec_time

        new_heuristic_cost = self.cost_calculator.calc_heuristic(
            curr_node, candidate, nav_time
        )

        new_cost = curr_heuristic + new_heuristic_cost

        completed_entry = CompletedEntry(
            subtask=copied_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        new_remaining = [
            r for r in curr_state.remaining_subtasks if r.name != candidate.subtask.name
        ]

        new_state = SchedulerState(
            subtask=copied_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_subtask_wo_monitoring]\n"
            f"*{candidate.subtask.name}, Score = {round(new_cost,LOG_ROUND)}\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(exec_time,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in new_remaining]}\n"
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _expand_wait_subtask_for_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        counter: itertools.count,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 서브태스크에 대해
        1) 일반 Wait
        2) time-critical이면 모니터링 시점에 맞춘 partial Wait
        """
        # TODO Nav Time 무지성으로 넣은거 검토하기 -> Wait에 (Nav랑 Wait같이 넣기)
        # TODO 그러니까, Critical Subtask를 위해 wait 하는 경우 거기 가서 기다려야 한다고
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost
        curr_constraints = curr_state.constraints

        _, _, related_sub_name = self.constraint_handler.get_time_slots(
            curr_state.subtask.name, curr_constraints, "out"
        )

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate.subtask
        )

        monitoring_timing = (
            curr_state.current_time
            + (candidate.earliest_start_time - curr_state.current_time)
            * BAYESIAN_CRITERIA
        )
        wait_duration = (
            monitoring_timing - curr_state.current_time - MONITORING_DURATION
        )

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
            duration=Duration(interval=wait_duration, type="Controllable"),
            repetition=1,
            type="Wait",
            execution=Execution(
                objects=None, primitive_actions=[f"Wait {wait_duration}"]
            ),
            temporal_constraints=None,
        )

        obj = curr_state.subtask.execution.primitive_actions[-1].split(" ")[-1]
        mon_sub = make_monitoring_subtask(related_sub_name, obj)

        start_time = curr_state.current_time
        end_time = start_time + wait_sub.duration.interval

        wait_candidate = Candidate(
            subtask=wait_sub,
            earliest_start_time=candidate.earliest_start_time,  # 실행 즉시 시작
            is_critical=False,
        )

        step_cost = self.cost_calculator.calc_heuristic(curr_node, wait_candidate, 0)
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
            constraints=curr_state.constraints,
            current_time=end_time,
            agent_location=new_location,
        )

        log.info(
            f"[_expand_wait_subtasks_with_monitoring]\n"
            f"*{wait_sub.name}, Score = {round(new_cost,LOG_ROUND)} (earliest_start={round(candidate.earliest_start_time,LOG_ROUND)})\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(wait_duration,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in new_remaining]}\n"
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node

    def _expand_wait_subtask(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        counter: itertools.count,
    ):
        """
        아직 earliest_start_time이 도래하지 않은 Subtask에 대해
        'Wait Subtask'를 생성하여 해당 시간을 대기하는 노드를 확장
        """

        curr_state = curr_node.state
        curr_heuristic = curr_node.heuristic_cost
        curr_depth = curr_node.depth

        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate.subtask
        )
        wait_start_time = curr_state.current_time
        wait_duration = candidate.earliest_start_time - curr_state.current_time

        wait_sub = Subtask(
            task_name=None,
            name=f"Wait for {candidate.subtask.name}",
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
            constraints=curr_state.constraints,
            current_time=curr_state.current_time + wait_duration,
            agent_location=new_location,
        )

        wait_candidate = Candidate(
            subtask=wait_sub,
            earliest_start_time=candidate.earliest_start_time,
            is_critical=False,
        )

        new_heuristic = self.cost_calculator.calc_heuristic(
            curr_node, wait_candidate, 0
        )

        new_cost = curr_heuristic + new_heuristic

        log.info(
            f"[_expand_wait_subtasks]\n"
            f"*{wait_sub.name}, Score = {round(new_cost,LOG_ROUND)} (earliest_start={round(candidate.earliest_start_time,LOG_ROUND)}, is_critical={candidate.is_critical})\n"
            f"Interval = {round(wait_start_time,LOG_ROUND)} ~ {round(wait_start_time+wait_duration,LOG_ROUND)} ({round(wait_duration,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in curr_state.remaining_subtasks]}\n"
        )

        new_node = SimulationNode(
            heuristic_cost=new_cost,
            depth=curr_depth + 1,
            tie_breaker=next(counter),
            state=new_state,
        )
        return new_node
