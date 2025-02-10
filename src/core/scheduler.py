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
from utils.visualizer import visualize_graph

log = create_module_logger(module_name=__name__, is_file_handler=True)


class Scheduler:

    def __init__(
        self,
        search_width: int = BEAM_WIDTH,
        simulation_depth: int = SIMULATION_DEPTH,
    ):

        self.search = search_width
        self.simulation_depth = simulation_depth
        log.info(f"{RED}{search_width=}, {simulation_depth=}{RESET}")

        self.nav_manager = NavigationManager()
        self.constraint_handler = ConstraintHandler()
        self.cost_calculator = HeuristicManager(self.constraint_handler)

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(
        self,
        parent_state: SchedulerState,
    ) -> Optional[SchedulerState]:

        child_state = self._simulate_search(parent_state)

        if child_state is None:
            log.error("[get_next_state] No child_state found (No feasible solution).")
            return None

        new_state = self._extract_state(parent_state, child_state)

        if new_state is None:
            log.error(
                f"[get_next_state] ChildState was found, but _extract_state returned None."
            )

        return new_state

    def _simulate_search(
        self,
        init_state: SchedulerState,
    ) -> Optional[SchedulerState]:

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

            # 이미 탐색할 수 없거나 종료 조건에 도달했는지 확인
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 1) 현재 시점에 "실행 가능한" 서브태스크 찾기
            # subtask, earliest_start, is_critical 반환
            feasible_candidates, not_yet_feasible_candidate = (
                self.constraint_handler.get_feasible_candidates(curr_node)
            )
            filtered_candidates = []
            for feasible_candidate in feasible_candidates:
                nav_time, _ = self.nav_manager.compute_navigation_time(
                    curr_node, feasible_candidate.subtask
                )
                if not (
                    feasible_candidate.deadline.due_date
                    < curr_state.current_time
                    + nav_time
                    + feasible_candidate.subtask.duration.interval
                ):
                    filtered_candidates.append(feasible_candidate)
            feasible_candidates = filtered_candidates

            if len(feasible_candidates) == 0 and len(not_yet_feasible_candidate) == 0:
                # 해당 branch는 infeasible
                continue  # => 이 노드는 확장 안 하고 skip

            log.warning(
                f"========================================\n"
                f"Depth = {curr_depth+1} / Current Time : {round(curr_state.current_time,2)}\n"
                f"Completed_subs ={[ce.subtask.name for ce in curr_state.completed_subtasks]}\n"
                f"Remaining_subs ={[r.name for r in curr_state.remaining_subtasks]}\n\n"
                f"Feasible_subs={[candidate for candidate in feasible_candidates]},\n"
                f"Not_yet_feasible_subs={[candidate for candidate in not_yet_feasible_candidate]}\n"
                f"==================================================\n"
            )
            visualize_graph(
                curr_node.state.constraints, "assets/results/debug", is_display=False
            )
            # (2) 아직 시작 시간이 되지 않은 서브태스크(not_yet_feasible_subs)에 대해, wait 고려
            if feasible_candidates == []:
                for candidate in not_yet_feasible_candidate:
                    new_node = self._expand_wait_subtask(curr_node, candidate, counter)
                    expanded_nodes.append(new_node)
            ##########################

            # --- (3) 즉시 실행 가능한 각 서브태스크 확장 ---
            for candidate in feasible_candidates:
                # 추가할 subtask에 고려할 deadline이 존재하는 경우
                if (
                    candidate.deadline.due_date != float("inf")
                    and not curr_node.state.subtask.decomposed
                ):
                    # 직전 subtask가 time-critical을 시작하는 경우 -> monitoring subtask으로 분할
                    new_node = self._expand_subtask_with_monitoring(
                        curr_node, candidate, counter, candidate.deadline
                    )

                else:
                    # 직전 subtask가 time-critical을 시작하지 않는 경우 -> 일반적인 subtask 실행
                    new_node = self._expand_subtask_wo_monitoring(
                        curr_node,
                        candidate,
                        counter,
                    )
                expanded_nodes.append(new_node)

            # --- (3) Local Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost)
            for i, nd in enumerate(expanded_nodes):
                if i < self.search:
                    queue.put(nd)
                else:
                    break

        if not best_solutions:
            log.error("[_simulate_search] best_solutions is empty -> No feasible\n")
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost)
        best_node = best_solutions[0]
        log.debug(
            f"[_simulate_search] Found best_node with Subtask={best_node.state.subtask.name}, "
            f"Cost={best_node.heuristic_cost}\n"
        )
        return best_node.state

    def _extract_state(
        self, parent_state: SchedulerState, child_state: SchedulerState
    ) -> Optional[SchedulerState]:

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

        next_state = SchedulerState(
            subtask=new_subtask,
            completed_subtasks=new_completed_schedule,
            remaining_subtasks=new_remaining_subtasks,
            constraints=new_constraints,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )

        return next_state

    # Helper function for _expand_subtask_with_monitoring
    def _expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        counter: itertools.count,
        deadline: tuple,
    ) -> SimulationNode:
        # 현재 상태 및 변수 설정
        curr_state = curr_node.state
        curr_depth = curr_node.depth
        curr_heuristic = curr_node.heuristic_cost

        deadline, linked_sub_name = deadline.due_date, deadline.subtask_name
        old_name = candidate.subtask.name

        # constraints 그래프를 deep copy하여 수정합니다.
        new_constraints = copy.deepcopy(curr_state.constraints)

        # 기존 candidate.subtask의 모든 인엣지와 아웃엣지를 저장한 후, 노드를 완전히 제거합니다.
        if new_constraints.has_node(old_name):
            in_edges = list(new_constraints.in_edges(old_name, data=True))
            out_edges = list(new_constraints.out_edges(old_name, data=True))
            new_constraints.remove_node(old_name)
        else:
            in_edges = []
            out_edges = []

        # 이동 시간(nav_time)과 새로운 위치 계산
        nav_time, new_location = self.nav_manager.compute_navigation_time(
            curr_node, candidate.subtask
        )
        subtask_start_time = curr_state.current_time
        # 전체 실행 시간: 이동 시간 + 서브태스크 실행 시간
        total_exec_time = candidate.subtask.duration.interval + nav_time

        # monitoring 시작 시점을 Bayesian 기준에 따라 계산합니다.
        monitoring_timing = subtask_start_time + (total_exec_time) * BAYESIAN_CRITERIA

        # early와 remain 서브태스크의 duration 계산
        early_dur = monitoring_timing - subtask_start_time

        # MONITORING_DURATION만큼 모니터링 후 남은 실행시간 계산
        remain_dur = total_exec_time - early_dur

        # 새로 생성되는 서브태스크들의 이름은 내부 함수에서 고유하게 생성하도록 합니다.
        early_sub = make_early_subtask(candidate.subtask, early_dur)
        mon_sub = make_monitoring_subtask(linked_sub_name)
        remain_sub = make_remain_subtask(candidate.subtask, remain_dur)

        # 새 노드들을 constraints 그래프에 추가합니다.
        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        # 1) 기존 candidate.subtask의 인엣지들을 새로 생성한 early_sub로 연결합니다.
        for pred, _, data in in_edges:
            new_constraints.add_edge(pred, early_sub.name, info=data.get("info", {}))

        # 2) 기존 candidate.subtask의 아웃엣지들을 새로 생성한 remain_sub로 연결합니다.
        for _, succ, data in out_edges:
            new_constraints.add_edge(remain_sub.name, succ, info=data.get("info", {}))

        # 3) 내부 체인 연결: early_sub → mon_sub → remain_sub
        new_constraints.add_edge(
            early_sub.name,
            mon_sub.name,
            info={
                "Interval": 0,
                "IsCritical": True,
            },
        )

        new_constraints.add_edge(
            mon_sub.name,
            remain_sub.name,
            info={"Interval": 0, "IsCritical": False},
        )

        # 새로운 remaining subtasks 업데이트:
        # 기존 후보 서브태스크(old_name)를 제거하고, 모니터링과 remain 서브태스크를 추가합니다.
        new_remaining = [r for r in curr_state.remaining_subtasks if r.name != old_name]
        new_remaining.extend([mon_sub, remain_sub])

        # early_sub를 바로 실행하는 것으로 가정 (나머지는 remaining에 남음)
        start_time = subtask_start_time
        end_time = start_time + early_sub.duration.interval

        # 비용 계산: 현재 비용에 heuristic step cost 추가
        step_cost = self.cost_calculator.calc_heuristic(curr_node, candidate, nav_time)
        new_cost = curr_heuristic + step_cost

        # 완료된 서브태스크 기록에 early_sub 실행 기록 추가
        completed_entry = CompletedEntry(
            subtask=early_sub,
            start_time=start_time,
            end_time=end_time,
        )
        new_completed = curr_state.completed_subtasks + [completed_entry]

        # 새로운 상태 생성: 업데이트된 constraints, remaining subtasks, 현재 시간, 위치 등 포함
        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=new_constraints,
            current_time=end_time,
            agent_location=new_location,
        )
        log.info(
            f"[_expand_subtask_with_monitoring]\n"
            f"*{candidate.subtask.name}, Score = {round(new_cost,LOG_ROUND)}\n"
            f"Interval = {round(start_time,LOG_ROUND)} ~ {round(end_time,LOG_ROUND)} ({round(end_time-start_time,LOG_ROUND)})\n"
            f"remaining_subtasks = {[r.name for r in new_remaining]}\n"
        )

        # 새로운 SimulationNode 생성하여 반환
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
