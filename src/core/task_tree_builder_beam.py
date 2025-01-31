import copy
import itertools
from queue import PriorityQueue
from typing import List, Optional

import networkx as nx

from core.task import Subtask
from task_management import ConstraintHandler, CostCalculator, NavigationManager
from utils.constants import DEFAULT_BEAM_WIDTH, DEFAULT_SIMULATION_DEPTH
from utils.dataclass import CompletedEntry, SchedulerState, SimulationNode
from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class Scheduler:

    def __init__(
        self,
        init_constraints: nx.DiGraph,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = DEFAULT_SIMULATION_DEPTH,
    ):

        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.constraint_handler = ConstraintHandler(init_constraints)
        self.cost_calculator = CostCalculator(self.constraint_handler)
        self.nav_manager = NavigationManager()

        self._counter = itertools.count()  # tie-breaker용

    def get_next_state(
        self,
        parent_state: SchedulerState,
        current_constraints: nx.DiGraph,
    ) -> Optional[SchedulerState]:
        """
        1) 현재 Subtask에 대한 out-edge(temporal constraint) 확인.
        2) separation_interval > 0이면 time_slot 기반 탐색(_simulate_time_slot),
           아니면 lookahead 기반 탐색(_simulate_lookahead).
        3) 탐색 결과 중 '다음으로 실행할 Subtask'를 골라 SchedulerState로 반환.
        """
        # 제약 갱신
        self.constraint_handler.constraints = current_constraints
        child_state = self._simulate_beam_search(parent_state)

        if not child_state:
            log.warning("No valid next step found.")
            return None

        return self._extract_state(parent_state, child_state)

    def _simulate_beam_search(
        self,
        init_state: SchedulerState,
    ) -> Optional[SchedulerState]:

        queue = PriorityQueue()
        # 초기 상태
        queue.put(
            SimulationNode(
                heuristic_cost=0.0,
                depth=0,
                elapsed_time=0.0,
                tie_breaker=next(self._counter),
                state=current_state,
            )
        )

        collected_solutions: List[SimulationNode] = []

        separation_interval = temporal_constraint.interval
        is_critical = temporal_constraint.is_critical
        related_subtask_name = temporal_constraint.related_subtask_name
        have_critical = False

        while not queue.empty():
            curr_node = queue.get()
            curr_heuristic = curr_node.heuristic_cost
            curr_depth = curr_node.depth
            curr_state = curr_node.state

            # 만약 이미 모든 서브태스크를 끝냈거나(remaining_subtasks가 없음)
            # 혹은 depth가 한계(simulation_depth) 도달하면
            # 더 이상 확장하지 않고 best_solutions에 저장
            if not curr_state.remaining_subtasks or curr_depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            # 현재 상태에서 실행 가능한 subtask들
            expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_node
            )
            if not expandable_subtasks:
                # feasible subtask가 없으므로, 더 이상 확장 불가
                collected_solutions.append(curr_node)
                continue

            # 각 candidate에 대해 확장
            is_expanded_curr_step = False
            for sub in expandable_subtasks:
                ############이거의 위치가 아래에서 위로 가지고 왔더니 time-critical 조건은 맞췄어요. 이유는.. 아마도 time 추가를 한 다음에 timeover여부를 결정해서 그런 것 같아요.
                nav_time, agent_location = self.nav_manager.compute_navigation_time(
                    curr_node, sub
                )
                new_heuristic_cost = self.cost_calculator.calc_heuristic_cost(
                    curr_node, sub, nav_time
                )
                copied_sub = copy.deepcopy(sub)
                copied_sub.duration.interval += nav_time
                ## nav_time제거시 알맞게 나옴. 여러 json파일을 돌려보면 확실하게 알수 있을 것이라 판단(즉, 현재 상태에서 다른 로직은 다 맞고 여기에 waitng과 monitering만 추가하면 된다고 생각함.)
                #################

                if sub.name == related_subtask_name:
                    # critical -> leftover >= 0이어야 실행 가능
                    ######### 여기는 부등호로 바꿨어요
                    # is_critical 상황 종료 -> have_critical = False
                    if is_critical and leftover <= 0:
                        have_critical = False
                        continue
                    # non-critical -> leftover <= 0이어야 실행 가능
                    if (not is_critical) and leftover > 0:
                        continue

                    # 지금 subtask가 is_critical인 것보다 이전에 진행하던 작업이 is_critical인게 중요해서 밑에 추가해줬어요.
                    # 쓰다가 깨달았는데 is_critical인 상황을 벗어나면 다시 업데이트하는 것도 반영해줘야 할 것 같아요.
                    if copied_sub.duration.interval < leftover and leftover > 0 and have_critical:
                        # separation_interval 내에 실행 불가
                        continue

                    if is_critical:
                        have_critical = True
                    else:
                        have_critical = False

                # ############
                # nav_time, agent_location = self.nav_manager.compute_navigation_time(
                #     curr_node, sub
                # )
                # new_heuristic_cost = self.cost_calculator.calc_heuristic_cost(
                #     curr_node, sub, nav_time
                # )
                # copied_sub = copy.deepcopy(sub)
                # copied_sub.duration.interval += nav_time
                # ##################

                new_heuristic_cost += curr_heuristic_cost
                new_depth = curr_depth + 1
                new_elapsed_time = curr_elapsed_time + copied_sub.duration.interval
                updated_completed = curr_node.state.completed_subtasks + [copied_sub]
                new_remain_subtasks = [
                    r
                    for r in curr_node.state.remaining_subtasks
                    if r.name != copied_sub.name
                ]

                new_scheduler_state = SchedulerState(
                    copied_sub,
                    updated_completed,
                    new_remain_subtasks,
                    agent_location,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic_cost,
                        depth=new_depth,
                        elapsed_time=new_elapsed_time,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )
                is_expanded_curr_step = True
            if is_critical and leftover > 0 and not is_expanded_curr_step:
                wait_sub = Subtask(
                    task_name=None,
                    name=(f"Wait for {related_subtask_name}"),
                    duration=leftover,
                    repetition=1,
                    type="Wait",
                    execution=None,
                    temporal_constraints=None,
                )

                new_heuristic_cost = curr_heuristic_cost + leftover
                new_elapsed_time = curr_elapsed_time + leftover
                new_depth = curr_depth + 1

                # "부모 node"에서 completed_subtasks 가져오기
                new_completed_subtasks = curr_node.state.completed_subtasks + [wait_sub]
                new_remain_subtasks = curr_node.state.remaining_subtasks

                new_scheduler_state = SchedulerState(
                    subtask=wait_sub,
                    completed_subtasks=new_completed_subtasks,
                    remaining_subtasks=new_remain_subtasks,
                    agent_location=curr_node.state.agent_location,
                )

                queue.put(
                    SimulationNode(
                        heuristic_cost=new_heuristic_cost,
                        depth=new_depth,
                        elapsed_time=new_elapsed_time,
                        tie_breaker=next(self._counter),
                        state=new_scheduler_state,
                    )
                )

        if not collected_solutions:
            return None

        # 비용 오름차순으로 정렬 -> 상위 beam_width만 추려서, 그중 최대 cost를 best
        sorted_paths = sorted(
            collected_solutions, key=lambda x: x.heuristic_cost, reverse=True
        )

        best_result = sorted_paths[0] if sorted_paths else None

        return best_result

    # ------------------------------------------------
    #   2) Lookahead (depth=simulation_depth) 기반 탐색
    # ------------------------------------------------
    def _simulate_lookahead(
        self,
        init_state: SchedulerState,  # subtask, completed_subtasks, remaining_subtasks (subtask는 부모 노드, completed_subtasks는 부모 노드의 completed_subtasks (subtask 제외), remaining_subtasks는 부모 노드의 remaining_subtasks)
    ) -> Optional[SimulationNode]:
        """
        lookahead(깊이=simulation_depth)까지 확장하는
        Beam Search 예시.
        """
        queue = PriorityQueue()
        # 초기 상태
        queue.put(
            SimulationNode(
                heuristic_cost=0.0,
                depth=0,
                elapsed_time=0.0,
                tie_breaker=next(self._counter),
                state=init_state,
            )
        )

        collected_solutions: List[SimulationNode] = []

        while not queue.empty():
            curr_node = queue.get()

            curr_heuristic = curr_node.heuristic_cost
            curr_depth = curr_node.depth
            curr_elapsed_time = curr_node.elapsed_time

            if curr_depth >= self.simulation_depth:
                # 탐색 제한 도달
                collected_solutions.append(curr_node)
                continue

            # --- (3) 실행 가능한 각 서브태스크 확장 ---
            expanded_nodes: List[SimulationNode] = []
            for candidate_sub in feasible_subs:
                # 이동 시간(nav_time) 계산
                nav_time, new_location = self.nav_manager.compute_navigation_time(
                    curr_node, candidate_sub
                )
                copied_sub = copy.deepcopy(candidate_sub)

                # 서브태스크 실제 실행 시간 = subtask.duration + nav_time
                # (주의: subtask.duration 자체를 덮어쓰지 않는 편이 안전)
                exec_time = candidate_sub.duration.interval + nav_time
                start_time = curr_state.current_time
                end_time = start_time + exec_time
                copied_sub.duration.interval = exec_time
                # 비용 계산
                step_cost = self.cost_calculator.calc_heuristic_cost(
                    curr_node, candidate_sub, nav_time
                )
                new_cost = curr_heuristic + step_cost

                # 완료 정보 업데이트
                completed_entry = CompletedEntry(
                    subtask=copied_sub,
                    start_time=start_time,
                    end_time=end_time,
                )
                new_completed = curr_state.completed_subtasks + [completed_entry]
                new_remaining = [
                    r
                    for r in curr_state.remaining_subtasks
                    if r.name != candidate_sub.name
                ]

                new_state = SchedulerState(
                    subtask=copied_sub,
                    completed_subtasks=new_completed,
                    remaining_subtasks=new_remaining,
                    current_time=end_time,
                    agent_location=new_location,
                )

                new_node = SimulationNode(
                    heuristic_cost=new_cost,
                    depth=curr_depth + 1,
                    tie_breaker=next(counter),
                    state=new_state,
                )
                expanded_nodes.append(new_node)

            # --- (4) Beam pruning: 상위 K개만 큐에 삽입 (비용 기준) ---
            expanded_nodes.sort(key=lambda nd: nd.heuristic_cost, reverse=True)
            for i, nd in enumerate(expanded_nodes):
                if i < self.beam_width:
                    queue.put(nd)
                else:
                    break

        # --- (5) 모두 확장 완료 후, best_solutions에서 비용 최소 해를 선정 ---
        if not best_solutions:
            return None

        best_solutions.sort(key=lambda nd: nd.heuristic_cost, reverse=True)
        best_node = best_solutions[0]  # 최소 비용 해
        return best_node.state

    def _extract_state(
        self, parent_state: SchedulerState, child_state: SchedulerState
    ) -> SchedulerState:
        # 부모 노드에 있던 subtask 이름 집합
        parent_completed_set = {
            ce.subtask.name for ce in parent_state.completed_subtasks
        }
        # 자식 노드의 completed_subtasks (List[CompletedEntry])
        child_plan = child_state.completed_subtasks

        # 자식 노드에서 새로 추가된 CompletedEntry들(=부모엔 없던 subtask)
        new_entries = [
            ce for ce in child_plan if ce.subtask.name not in parent_completed_set
        ]
        if not new_entries:
            # 새로 추가된 subtask가 없다면, 그냥 child_state 그대로 반환 or 예외 처리
            return child_state

        new_entry = new_entries[0]
        new_subtask = new_entry.subtask

        # 부모 노드의 completed_subtasks에 새 entry 추가
        new_completed_subtasks = parent_state.completed_subtasks + [new_entry]

        # remaining_subtasks에서 이 subtask 제거
        new_remaining_subtasks = [
            r for r in parent_state.remaining_subtasks if r.name != new_subtask.name
        ]

        # 이제 새 SchedulerState 생성
        return SchedulerState(
            subtask=new_subtask,  # 새로 완료된 subtask
            completed_subtasks=new_completed_subtasks,
            remaining_subtasks=new_remaining_subtasks,
            agent_location=child_state.agent_location,
            current_time=new_entry.end_time,
        )
