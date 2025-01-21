import copy
import itertools
from queue import PriorityQueue
from typing import Any, List, NamedTuple, Optional, Tuple

import networkx as nx
from anytree import Node

from core.task import Subtask
from task_management.rule import ConstraintHandler, SlotHandler
from utils.util import create_module_logger, load_navigation_times, tasks_to_subtasks

log = create_module_logger(module_name=__name__, is_file_handler=False)

# Constants
COST_WEIGHT = 3
DEFAULT_SIMULATION_DEPTH = 5
DEFAULT_BEAM_WIDTH = 1


class TaskTree:
    """
    Manages a tree of tasks (subtasks or wait nodes).
    """

    def __init__(self):
        self.root_node = Node(name="Init", start=0, end=0, duration=0)

    def _add_node(self, parent: Node, name: str, start: int, end: int) -> Node:
        new_node = Node(
            name=name,
            parent=parent,
            start=start,
            end=end,
            duration=end - start,
        )
        log.debug(f"Added node: {new_node.name}, duration={new_node.duration}")
        return new_node

    def add_wait_node(self, parent: Node, subtask_name: str, wait_time: int) -> Node:
        """
        Adds a wait node as a child of `parent`.
        """
        return self._add_node(
            parent=parent,
            name=f"Wait for {subtask_name}",
            start=parent.end,
            end=parent.end + wait_time,
        )

    def add_subtask_node(
        self, parent: Node, subtask: "Subtask", navigate_time: int = 0
    ) -> Node:
        """
        Adds a subtask node (including navigation time).
        """
        return self._add_node(
            parent=parent,
            name=subtask.name,
            start=parent.end,
            end=parent.end + navigate_time + subtask.duration.interval,
        )


class SimulationState(NamedTuple):
    name: str

    partial_plan: List[Any]
    remaining_subtasks: List[Any]


class TaskTreeBuilder:
    """
    Builds a TaskTree using a multi-step (3-step) beam-search simulation.
    """

    def __init__(
        self,
        constraints: nx.DiGraph,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        simulation_depth: int = DEFAULT_SIMULATION_DEPTH,
        constraint_handler: ConstraintHandler = None,
        slot_handler: SlotHandler = None,
    ):
        self.tree = TaskTree()
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self.constraint_handler = constraint_handler or ConstraintHandler(constraints)
        self.slot_handler = slot_handler or SlotHandler(self._expand_node)
        self.navigation_times = load_navigation_times()
        self.subtasks_info = None

        self.best_plan: Optional[Node] = None
        self.best_makespan: float = float("inf")

        # For tie-breaking
        self._counter = itertools.count()

    def build_tree(self, tasks: List[Any]) -> Node:
        """
        Build a task tree using the 3-step simulation method.
        """
        remaining_subtasks = tasks_to_subtasks(tasks)
        self.subtasks_info = copy.deepcopy(remaining_subtasks)

        current_node = self.tree.root_node

        # Initialize the simulation state
        current_state = SimulationState(
            name="Init",
            partial_plan=[],
            remaining_subtasks=remaining_subtasks,
        )

        while current_state.remaining_subtasks:
            # 1) Get temporal constraints for the current node
            simulated_paths = self._simulate_expansion(current_state)

            if not simulated_paths:
                log.warning("No valid paths found. Stopping expansion.")
                break

            # 2) Prune and select the best path
            best_path, _ = self._prune_simulated_paths(simulated_paths)
            if best_path is None:
                log.warning("All expansions are invalid. Stopping expansion.")
                break

            # 3) best_path is (cost, depth, subtask, updated_remaining)
            _, _, selected_subtask, updated_remaining = best_path

            # 4) Actually add the chosen subtask to the real tree
            #    (Note: if you want purely "simulate" first, you might store the partial plan
            #     and only add to the real tree after the entire beam search.)

            if selected_subtask.name.startswith("Wait for"):
                # 남은 slot 시간 (대기 시간)을 계산
                # Tree에 대기 노드 추가
                current_node = self.tree.add_wait_node(
                    parent=current_node,
                    wait_time=selected_subtask.duration,
                    subtask_name=selected_subtask.name,
                )

            else:
                # 일반 서브태스크를 Tree에 추가
                navigate_time = self._calc_navigate_time(
                    current_state, selected_subtask
                )
                current_node = self.tree.add_subtask_node(
                    current_node, selected_subtask, navigate_time
                )

            current_state = SimulationState(
                name=selected_subtask.name,
                partial_plan=current_state.partial_plan + [selected_subtask],
                remaining_subtasks=updated_remaining,
            )

        return self.tree.root_node

    #####################
    # SIMULATION LOGIC  #
    #####################

    def _simulate_expansion(
        self, state: SimulationState
    ) -> List[Tuple[int, int, Any, List[Any]]]:
        """
        Simulate expansions from `parent_node` within the simulation depth.
        Return a list of paths: (total_cost, depth, subtask, updated_subtasks).
        """
        queue = PriorityQueue()
        queue.put((0, 0, next(self._counter), state))

        # 메모리에 저장될 simulated_paths
        simulated_paths = []

        while not queue.empty():
            total_cost, current_depth, _, state = queue.get()

            # Get temporal constraints for the current node
            outgoing_time_slot = self.constraint_handler.get_temporal_constraints(
                state.name, type="out"
            )
            separation_interval, _, _ = outgoing_time_slot

            # If there's a time slot, handle that scenario
            if separation_interval > 0:
                self._simulate_time_slot_case(
                    total_cost=total_cost,
                    current_depth=current_depth,
                    current_state=state,
                    simulated_paths=simulated_paths,
                    temporal_constraint=outgoing_time_slot,
                    queue=queue,
                )
            else:
                # Normal expansion: expand all subtasks that are feasible
                self._simulate_normal_case(
                    total_cost=total_cost,
                    current_depth=current_depth,
                    current_state=state,
                    simulated_paths=simulated_paths,
                    temporal_constraint=outgoing_time_slot,
                    queue=queue,
                )

        return simulated_paths

    def _simulate_time_slot_case(
        self,
        total_cost: int,
        current_depth: int,
        current_state: SimulationState,
        simulated_paths: List[Tuple[int, int, Any, List[Any]]],
        temporal_constraint: Tuple[Any, ...],
        queue: PriorityQueue,
    ):
        """
        Time slot case. (slot 내에 여러 subtask를 배치해보는 로직)

        예시: slot을 많이(혹은 원하는 기준으로) 채우고, 그 중 상위 beam_width만 선택.
        """

        separation_interval, is_time_critical, related_subtask = temporal_constraint

        mini_beam_queue = PriorityQueue()

        # 초기 상태: ( -subtask_count, slot_cost, leftover_time, partial_plan, remaining_subtasks )
        # subtask_count = slot 내 배치 개수, 음수로 넣어 많은 subtask가 우선되도록
        mini_beam_queue.put(
            (
                (0, 0),  # 우선순위
                next(self._counter),
                separation_interval,
                0,
                current_state.partial_plan[:],
                current_state.remaining_subtasks[:],
            )
        )

        mini_simulated_scenarios = []

        while not mini_beam_queue.empty():
            priority_value, _, curr_leftover, curr_slot_cost, curr_plan, curr_remain = (
                mini_beam_queue.get()
            )
            subtask_count, cost_value = priority_value
            # 양수로 변환 (이제야, 갯수를 의미)
            subtask_count = -subtask_count

            # 현재 상태에서 expand 가능한 subtask
            virtual_state = SimulationState(
                name=current_state.name,
                partial_plan=curr_plan,
                remaining_subtasks=curr_remain,
            )
            feasible_tasks = self.constraint_handler.get_expandable_subtasks(
                virtual_state
            )

            # slot 내에 배치할 수 있는지(= duration + nav_time <= curr_leftover)
            expandable_subtasks_in_slot = []
            for expandable_subtask in feasible_tasks:
                if (
                    expandable_subtask.name == related_subtask
                ):  # 제약 조건과 관련된 것은 skip (time slot 채운 후 배치할 예정)
                    continue
                navigate_time = self._calc_navigate_time(
                    virtual_state, expandable_subtask
                )
                total_duration = expandable_subtask.duration.interval + navigate_time
                if total_duration <= curr_leftover:
                    expandable_subtasks_in_slot.append(expandable_subtask)

            if expandable_subtasks_in_slot:
                # slot 내에 배치할 수 있는 subtask가 있을 때
                for expandable_subtask in expandable_subtasks_in_slot:
                    navigate_time = self._calc_navigate_time(
                        virtual_state, expandable_subtask
                    )
                    # 총 소요 시간 계산
                    total_duration = (
                        expandable_subtask.duration.interval + navigate_time
                    )

                    # 슬롯에 채운 만큼 new_slot_cost 증가
                    new_slot_cost = curr_slot_cost + total_duration

                    new_remain = [
                        r for r in curr_remain if r.name != expandable_subtask.name
                    ]

                    mini_beam_queue.put(
                        (
                            (-(subtask_count + 1), new_slot_cost),
                            next(self._counter),
                            curr_leftover - total_duration,
                            curr_slot_cost + total_duration,
                            curr_plan + [expandable_subtask],
                            new_remain,
                        )
                    )
            else:
                # slot 내에 배치할 수 있는 subtask가 없지만, 남은 separation_interval이 있을 때
                # wait에 해당하는 처리가 필요
                if curr_leftover > 0:
                    # 대기 처리

                    new_slot_cost = (
                        curr_slot_cost + curr_leftover  # 남은 slot만큼 대기
                    )  # 대기 시간만큼 비용 증가

                    # Wait Node 추가 (가상 plan에 반영)
                    wait_node_name = (
                        f"Wait for {related_subtask}" if related_subtask else "Idle"
                    )
                    wait_subtask = Subtask(
                        task_name=None,
                        name=wait_node_name,
                        duration=curr_leftover,
                        repetition=1,
                        type="Wait",
                        execution=None,
                        temporal_constraints=None,
                    )
                    mini_simulated_scenarios.append(
                        (
                            subtask_count,  # 대기는 작업 개수에 포함하지 않음
                            total_cost + new_slot_cost,  # 전체 비용
                            current_depth + 1,  # 심화 depth
                            curr_plan + [wait_subtask],  # 가상 plan에 대기 추가
                            curr_remain[:],  # 남은 작업은 그대로
                            0,  # 남은 slot 시간은 0
                        )
                    )
                else:
                    # 더 이상 배치할 작업도, 남은 slot 시간도 없으므로 종료
                    mini_simulated_scenarios.append(
                        (
                            subtask_count,
                            total_cost + curr_slot_cost,
                            current_depth + 1,
                            curr_plan[:],
                            curr_remain[:],
                            curr_leftover,
                        )
                    )
            # beam 폭 제한 (fill_queue)
            if mini_beam_queue.qsize() > (self.beam_width * 10):
                temp_list = []
                while not mini_beam_queue.empty():
                    temp_list.append(mini_beam_queue.get())
                # 우선순위: (-(subtask_count), slot_cost)
                temp_list.sort(key=lambda x: x[0])  # x[0] = (-(count), cost)
                for item in temp_list[: self.beam_width * 5]:
                    mini_beam_queue.put(item)

        # filled_scenarios 중 "subtask_count가 가장 많고, cost가 낮은" 순으로 정렬
        mini_simulated_scenarios.sort(key=lambda x: (-x[0], x[1]))
        # x: (subtask_count, final_cost, new_depth, final_plan, final_remain, leftover)

        # 상위 beam_width 개만 후속단계( simulated_paths ) 에 반영
        top_scenarios = mini_simulated_scenarios[: self.beam_width]

        for scenario in top_scenarios:
            sc_count, sc_cost, sc_depth, sc_plan, sc_remain, sc_leftover = scenario
            # 마지막으로 배치된 subtask
            last_subtask = sc_plan[-1] if sc_plan else None

            # simulated_paths: (cost, depth, subtask, updated_remaining)
            if last_subtask:

                simulated_paths.append(
                    (
                        sc_cost,  # 최종 비용
                        sc_depth,  # 새로운 depth
                        last_subtask,  # 마지막 subtask
                        sc_remain,  # 남은 subtasks
                    )
                )
            # else:
            #     # slot에 아무 것도 넣지 못한 경우( subtask_count=0 )
            #     # 그냥 반환할 수도 있고, or time_critical leftover 처리 가능
            #     simulated_paths.append(
            #         (
            #             sc_cost,
            #             sc_depth,
            #             None,
            #             sc_remain,
            #         )
            #   )

    def _simulate_normal_case(
        self,
        total_cost: int,
        current_depth: int,
        current_state: SimulationState,
        simulated_paths: List[Tuple[int, int, Any, List[Any]]],
        temporal_constraint: Tuple[int, bool],
        queue: PriorityQueue,
    ):
        """
        Normal expansion case: expand feasible subtasks (no separation interval).
        """
        # (separation interval이 없는) 부모 노드에서 실행 가능한 서브태스크를 가져옴
        expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
            current_state
        )
        # Expand each subtask
        for subtask in expandable_subtasks:
            cost, updated_remaining = self._expand_node(
                total_cost=total_cost,
                current_depth=current_depth,
                current_state=current_state,
                child_candidate=subtask,
                queue=queue,
            )

            if current_depth == 0:
                simulated_paths.append(
                    (
                        total_cost + cost,
                        current_depth + 1,
                        subtask,
                        updated_remaining,
                    )
                )

    ########################
    # EXPANSION & SCORING  #
    ########################

    def _expand_node(
        self,
        total_cost: int,
        current_depth: int,
        current_state: SimulationState,
        child_candidate: Any,
        queue: PriorityQueue,
    ) -> Tuple[int, List[Any]]:
        """
        Expands a child candidate and returns (cost, new_child_node, new_remaining).
        """
        outgoing_ts = self.constraint_handler.get_temporal_constraints(
            child_candidate.name, type="out"
        )
        incoming_ts = self.constraint_handler.get_temporal_constraints(
            child_candidate.name, type="in"
        )

        # Calculate navigation time
        navigate_time = self._calc_navigate_time(current_state, child_candidate)

        new_remaining = [
            s
            for s in current_state.remaining_subtasks
            if s.name != child_candidate.name
        ]

        # Example cost formula
        cost_val = (COST_WEIGHT - current_depth) * (
            child_candidate.duration.interval
            + navigate_time
            + (incoming_ts[0] - outgoing_ts[0])
        )

        new_state = SimulationState(
            name=child_candidate.name,
            partial_plan=current_state.partial_plan + [child_candidate],
            remaining_subtasks=new_remaining,
        )
        queue.put(
            (
                cost_val + total_cost,
                current_depth + 1,
                next(self._counter),
                new_state,
            )
        )
        return cost_val, new_remaining

    #######################
    # TIME & PATH HELPERS #
    #######################

    def _calc_navigate_time(
        self, current_state: SimulationState, child_subtask: "Subtask"
    ) -> float:
        """
        Calculate navigation time between the current state and the child subtask.
        Handles Init, Wait, and Subtasks without NAVIGATE_TO actions.
        """
        # 1. Wait Node 처리: 이동 없음
        if current_state.name.startswith("Wait") or child_subtask.name.startswith(
            "Wait"
        ):
            log.info(
                f"Either the current state '{current_state.name}' or the target subtask '{child_subtask.name}' is a Wait Node. Navigation time is 0."
            )
            return 0.0

        # 2. Init Node 처리: 기본 위치는 'agent'
        if current_state.name == "Init":
            last_location = "agent"
        else:
            # 3. Subtask 처리: 마지막 위치 탐색
            last_location = self._find_last_location(current_state)
            if not last_location:
                log.warning(
                    f"No valid NAVIGATE_TO action found for state '{current_state.name}'. Defaulting to 'agent'."
                )
                last_location = "agent"

        # 4. Target subtask에서 첫 NAVIGATE_TO 액션 찾기
        target_location = self._find_first_location(child_subtask)
        if not target_location:
            log.info(
                f"No NAVIGATE_TO action in target subtask '{child_subtask.name}'. Navigation time is 0."
            )
            return 0.0

        # 5. Navigation 시간 계산
        move_time = self._lookup_navigation_time(last_location, target_location)
        return move_time

    def _prune_simulated_paths(
        self, paths: List[Tuple[int, int, Any, List[Any]]]
    ) -> Tuple[
        Optional[Tuple[int, int, Any, List[Any]]], List[Tuple[int, int, Any, List[Any]]]
    ]:
        """
        Prune to top `beam_width` paths and return the best path.
        """
        if not paths:
            log.warning("No paths to prune.")
            return None, []

        pruned = sorted(paths, key=lambda x: (x[0], x[1]))[: self.beam_width]
        return pruned[0], pruned

    def _find_last_location(self, state: SimulationState) -> Optional[str]:
        """
        Find the last 'NAVIGATE_TO' location in the partial plan.
        If none is found, return None.
        """
        for subtask in reversed(state.partial_plan):
            if subtask.name.startswith("Wait"):
                continue  # Wait Node는 건너뜀

            subtask_info = next(
                (s for s in self.subtasks_info if s.name == subtask.name), None
            )
            if subtask_info:
                # 'NAVIGATE_TO' 액션 검색
                last_location = next(
                    (
                        action.split()[-1]
                        for action in reversed(subtask_info.execution.primitive_actions)
                        if action.startswith("NAVIGATE_TO")
                    ),
                    None,
                )
                if last_location:
                    return last_location
        return None  # 찾지 못한 경우

    def _find_first_location(self, subtask: "Subtask") -> Optional[str]:
        """
        Find the first 'NAVIGATE_TO' action in the subtask's primitive actions.
        If none is found, return None.
        """
        return next(
            (
                action.split()[-1]
                for action in subtask.execution.primitive_actions
                if action.startswith("NAVIGATE_TO")
            ),
            None,
        )

    def _lookup_navigation_time(
        self, last_location: str, target_location: str
    ) -> float:
        """
        Lookup the navigation time between two locations.
        """
        matched_source_key = next(
            (k for k in self.navigation_times if k.startswith(last_location)), None
        )
        if not matched_source_key:
            log.warning(
                f"No source key matched for '{last_location}' in navigation times."
            )
            return float("inf")

        matched_target_key = next(
            (
                k
                for k in self.navigation_times.get(matched_source_key, {})
                if target_location in k
            ),
            None,
        )
        if not matched_target_key:
            log.warning(
                f"No target key matched for '{target_location}' under '{matched_source_key}' in navigation times."
            )
            return float("inf")

        move_time = self.navigation_times[matched_source_key].get(
            matched_target_key, None
        )
        if move_time is None:
            log.warning(
                f"Navigation time from '{matched_source_key}' to '{matched_target_key}' not found."
            )
            return float("inf")

        log.info(
            f"Navigation time from '{last_location}' to '{target_location}' is {move_time}."
        )
        return move_time
