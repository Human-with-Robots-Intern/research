import copy
import itertools
from queue import PriorityQueue
from typing import List, NamedTuple, Optional, Tuple

import networkx as nx
from anytree import Node

from core.task import Subtask
from task_management.cost_calculator import CostCalculator, NavigationManager
from task_management.rule import ConstraintHandler, SlotHandler

# 모듈 분리된 클래스들
from task_management.task_tree import TaskTree
from task_management.time_slot_simulator import TimeSlotSimulator
from utils.util import create_module_logger, load_navigation_times, tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=False)

DEFAULT_SIMULATION_DEPTH = 3
DEFAULT_BEAM_WIDTH = 2


class SimulationState(NamedTuple):
    """
    시뮬레이션 중 임시 상태.
    """

    name: str  # 마지막으로 실행된 Subtask 이름 (또는 "Init")
    partial_plan: List[Subtask]
    remaining_subtasks: List[Subtask]


class TaskTreeBuilder:
    """
    Beam Search(lookahead depth=3)로 Subtask를 확정해 나가는 로직.
    """

    def __init__(
        self,
        constraints: nx.DiGraph,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = DEFAULT_SIMULATION_DEPTH,
    ):
        self.tree = TaskTree()
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        # 핸들러
        self.constraint_handler = ConstraintHandler(constraints)
        self.slot_handler = SlotHandler(self._expand_subtask)  # 필요시 사용

        # 부품 모듈들
        self.cost_calculator = CostCalculator(
            constraint_handler=self.constraint_handler
        )
        self.navigation_manager = NavigationManager(
            navigation_times=load_navigation_times(),
            all_subtasks_info=[],  # 뒤에서 set
        )
        self.time_slot_simulator = TimeSlotSimulator(
            beam_width=self.beam_width,
            constraint_handler=self.constraint_handler,
            cost_calculator=self.cost_calculator,
            navigation_manager=self.navigation_manager,
        )

        self.subtasks_info = None  # 전체 Subtask 원본 보관
        self._counter = itertools.count()  # tie-breaker for PriorityQueue ordering

    def build_tree(self, tasks: List[Subtask]) -> Node:
        """
        전체 파이프라인:
          1) 남은 Subtask가 있을 때까지:
             - depth=3까지 lookahead
             - cost 최소인 경로 선택 -> "첫 Subtask"만 Tree에 반영
             - state 업데이트
          2) 최종 트리 반환
        """
        subtasks = tasks_to_subtasks(tasks)
        self.subtasks_info = copy.deepcopy(subtasks)
        # NavigationManager 설정
        self.navigation_manager.subtasks_info = self.subtasks_info

        current_node = self.tree.root_node
        current_state = SimulationState("Init", [], subtasks)

        while current_state.remaining_subtasks:
            # 1) 시뮬레이션(expansion)
            # 1) out-edge(temporal constraint)가 있는 경우: separation_interval > 0인 경우
            time_slot = self.constraint_handler.get_temporal_constraints(
                current_state.name, direction="out"
            )

            if time_slot[0] > 0:
                simulated_paths = self._simulate_time_slot(current_state, time_slot)
            else:
                simulated_paths = self._simulate_lookahead(current_state)

            if not simulated_paths:
                log.warning("No valid paths found. Stopping expansion.")
                break

            # 2) 후보들을 cost 오름차순 정렬 -> 상위 1개 선택
            best_path, _ = self._prune_simulated_paths(simulated_paths)
            if not best_path:
                log.warning("All expansions invalid. Stopping.")
                break

            best_cost, best_depth, last_subtask, remain_after, plan_after = best_path
            if not last_subtask:
                log.warning("Best path has empty plan. Stopping.")
                break

            # 첫 Subtask만 트리에 반영
            chosen_subtask = last_subtask
            if chosen_subtask.name.startswith("Wait for"):
                # Wait 노드인 경우 (예: 대기 지시 Subtask)
                wait_time = chosen_subtask.duration
                current_node = self.tree.add_wait_node(
                    parent=current_node,
                    subtask_name=chosen_subtask.name,
                    wait_time=wait_time,
                )
            else:
                # 일반 subtask
                nav_time = self.navigation_manager.calculate_navigation_time(
                    current_state.name, current_state.partial_plan, chosen_subtask
                )
                current_node = self.tree.add_subtask_node(
                    parent=current_node, subtask=chosen_subtask, navigate_time=nav_time
                )

            # 3) state 갱신
            new_remaining = [
                s
                for s in current_state.remaining_subtasks
                if s.name != chosen_subtask.name
            ]
            new_plan = current_state.partial_plan + [chosen_subtask]
            current_state = SimulationState(
                chosen_subtask.name, new_plan, new_remaining
            )

        return self.tree.root_node

    # ------------------------------------------------
    #   Lookahead (depth=simulation_depth)
    # ------------------------------------------------
    def _simulate_time_slot(
        self, current_state: SimulationState, temporal_constraint: float
    ):
        queue = PriorityQueue()
        queue.put((0.0, 0, next(self._counter), current_state))

        results: List[
            Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]
        ] = []

        while not queue.empty():
            curr_cost, curr_depth, _, curr_state = queue.get()

            # depth 제한에 도달 -> 결과로 바로 저장
            if curr_depth >= self.simulation_depth:
                last_subtask = (
                    curr_state.partial_plan[-1] if curr_state.partial_plan else None
                )
                results.append(
                    (
                        curr_cost,
                        curr_depth,
                        last_subtask,
                        curr_state.remaining_subtasks,
                        curr_state.partial_plan,
                    )
                )
                continue
        # Time-slot 필수 시뮬레이션
        slot_scenarios = self.time_slot_simulator.simulate_time_slot(
            total_cost=curr_cost,
            current_depth=curr_depth,
            current_subtask_name=curr_state.name,
            partial_plan=curr_state.partial_plan,
            remaining_subtasks=curr_state.remaining_subtasks,
            temporal_constraint=temporal_constraint,
        )
        # slot_scenarios -> list of (subtask_count, final_cost, new_depth, final_plan, remain)
        for scenario in slot_scenarios:
            sub_count, sc_cost, sc_depth, sc_plan, sc_remain = scenario
            last_sub = sc_plan[-1] if sc_plan else None
            results.append((sc_cost, sc_depth, last_sub, sc_remain, sc_plan))

            if sc_depth < self.simulation_depth:
                new_state = SimulationState(
                    name=last_sub.name if last_sub else curr_state.name,
                    partial_plan=sc_plan,
                    remaining_subtasks=sc_remain,
                )
                queue.put((sc_cost, sc_depth, next(self._counter), new_state))

    def _simulate_lookahead(
        self, init_state: SimulationState
    ) -> List[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]]:
        """
        init_state 부터 depth=simulation_depth까지 확장.
        PriorityQueue 를 사용하여 cost 오름차순으로 탐색.

        Returns:
            List of tuples:
                (total_cost, depth, last_subtask, remaining_subtasks, partial_plan)
        """
        queue = PriorityQueue()
        queue.put((0.0, 0, next(self._counter), init_state))

        results: List[
            Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]
        ] = []

        while not queue.empty():
            curr_cost, curr_depth, _, curr_state = queue.get()

            # depth 제한에 도달 -> 결과로 바로 저장
            if curr_depth >= self.simulation_depth:
                last_subtask = (
                    curr_state.partial_plan[-1] if curr_state.partial_plan else None
                )
                results.append(
                    (
                        curr_cost,
                        curr_depth,
                        last_subtask,
                        curr_state.remaining_subtasks,
                        curr_state.partial_plan,
                    )
                )
                continue

            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                curr_state
            )
            for feasible_subtask in feasible_subtasks:
                cost_val, updated_remain = self._expand_subtask(
                    total_cost=curr_cost,
                    current_depth=curr_depth,
                    current_state=curr_state,
                    candidate_subtask=feasible_subtask,
                )
                new_cost = curr_cost + cost_val
                new_depth = curr_depth + 1
                new_plan = curr_state.partial_plan + [feasible_subtask]

                results.append(
                    (
                        new_cost,
                        new_depth,
                        feasible_subtask,
                        updated_remain,
                        new_plan,
                    )
                )

                if new_depth < self.simulation_depth:
                    new_state = SimulationState(
                        feasible_subtask.name, new_plan, updated_remain
                    )
                    queue.put((new_cost, new_depth, next(self._counter), new_state))

        return results

    def _expand_subtask(
        self,
        total_cost: float,
        current_depth: int,
        current_state: SimulationState,
        candidate_subtask: Subtask,
    ) -> Tuple[float, List[Subtask]]:
        """
        Subtask 확장 시 비용 계산(heuristic) 후, remaining_subtasks 갱신.
        """
        # Get constraints for candidate_subtask
        incoming_ts = self.constraint_handler.get_temporal_constraints(
            candidate_subtask.name, direction="in"
        )
        outgoing_ts = self.constraint_handler.get_temporal_constraints(
            candidate_subtask.name, direction="out"
        )

        # Calculate navigation time
        nav_time = self.navigation_manager.calculate_navigation_time(
            current_state.name, current_state.partial_plan, candidate_subtask
        )

        # Calculate heuristic cost
        cost_val = self.cost_calculator.calc_heuristic_cost(
            current_depth, candidate_subtask, nav_time, incoming_ts, outgoing_ts
        )

        # Filter out the chosen subtask from remaining
        new_remaining = [
            s
            for s in current_state.remaining_subtasks
            if s.name != candidate_subtask.name
        ]

        return cost_val, new_remaining

    # ------------------------------------------------
    #   BEAM PRUNE
    # ------------------------------------------------
    def _prune_simulated_paths(
        self,
        paths: List[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]],
    ) -> Tuple[
        Optional[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]],
        List[Tuple[float, int, Optional[Subtask], List[Subtask], List[Subtask]]],
    ]:
        """
        (cost, depth, last_subtask, remain, plan)을 cost 기준으로 정렬 후
        beam_width만큼 살리고 그중 최소 cost를 best_path로 선정.
        """
        if not paths:
            return None, []

        sorted_paths = sorted(paths, key=lambda x: x[0])  # cost ascending
        pruned = sorted_paths[: self.beam_width]

        best_path = pruned[0] if pruned else None
        return best_path, pruned
