import copy
import itertools
from queue import PriorityQueue
from typing import Any, List, Optional, Tuple

import networkx as nx
from anytree import Node

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
        all_subtasks = tasks_to_subtasks(tasks)
        self.subtasks_info = sorted(
            all_subtasks, key=lambda task: task.duration.interval
        )

        current_node = self.tree.root_node
        remaining_subtasks = copy.deepcopy(all_subtasks)

        while remaining_subtasks:
            # 1) Get the time slot constraints for the current node
            separation_interval, is_time_critical = self._calculate_time_slot(
                current_node
            )

            # 2) Simulate expansions from the current node
            simulated_paths = self._simulate_expansion(
                parent_node=current_node,
                remaining_subtasks=remaining_subtasks,
                separation_interval=separation_interval,
                is_time_critical=is_time_critical,
            )

            if not simulated_paths:
                log.warning("No valid paths found. Stopping expansion.")
                break

            # 3) Prune and select the best path
            best_path, _ = self._prune_simulated_paths(simulated_paths)
            if best_path is None:
                log.warning("All expansions are invalid. Stopping expansion.")
                break

            # 4) best_path is (cost, depth, subtask, updated_remaining)
            _, _, selected_subtask, updated_remaining = best_path

            # 5) Actually add the chosen subtask to the real tree
            #    (Note: if you want purely "simulate" first, you might store the partial plan
            #     and only add to the real tree after the entire beam search.)
            current_node = self.tree.add_subtask_node(current_node, selected_subtask)
            remaining_subtasks = updated_remaining

        return self.tree.root_node

    #####################
    # SIMULATION LOGIC  #
    #####################

    def _simulate_expansion(
        self,
        parent_node: Node,
        remaining_subtasks: List[Any],
        separation_interval: int,
        is_time_critical: bool,
    ) -> List[Tuple[int, int, Any, List[Any]]]:
        """
        Simulate expansions from `parent_node` within the simulation depth.
        Return a list of paths: (total_cost, depth, subtask, updated_subtasks).
        """
        queue = PriorityQueue()
        # We put an initial state into the queue
        queue.put((0, 0, next(self._counter), parent_node, remaining_subtasks))

        simulated_paths = []
        visited_states = set()

        while not queue.empty():
            total_cost, current_depth, _, node_state, subtasks_state = queue.get()

            # Avoid repeated states
            state_id = (
                id(node_state),
                tuple(s.name for s in subtasks_state),
                current_depth,
            )
            if state_id in visited_states:
                continue
            visited_states.add(state_id)

            # Stop if at max depth or nothing left to schedule
            if current_depth >= self.simulation_depth or not subtasks_state:
                continue

            # If there's a time slot, handle that scenario
            if separation_interval > 0:
                self._simulate_time_slot_case(
                    current_node=node_state,
                    remaining_subtasks=subtasks_state,
                    simulated_paths=simulated_paths,
                    total_cost=total_cost,
                    current_depth=current_depth,
                    separation_interval=separation_interval,
                    is_time_critical=is_time_critical,
                )
            else:
                # Normal expansion: expand all subtasks that are feasible
                self._simulate_normal_case(
                    node_state=node_state,
                    subtasks_state=subtasks_state,
                    queue=queue,
                    total_cost=total_cost,
                    current_depth=current_depth,
                    simulated_paths=simulated_paths,
                )

        return simulated_paths

    def _simulate_time_slot_case(
        self,
        current_node: Node,
        remaining_subtasks: List[Any],
        simulated_paths: List[Tuple[int, int, Any, List[Any]]],
        total_cost: int,
        current_depth: int,
        separation_interval: int,
        is_time_critical: bool,
    ):
        """
        Simulation logic when we have a time slot (separation_interval > 0).
        This tries to 'fill' that slot with as many subtasks as possible.
        """
        scheduled_subtasks, updated_remaining = self.fill_time_slot(
            remaining_subtasks, (separation_interval, is_time_critical)
        )

        # For demonstration, we are modifying `current_node` directly.
        # WARNING: This modifies the real tree. For a purely "look-ahead" approach,
        #          you might want a *temporary copy* of the node or the entire tree.
        for i, subtask in enumerate(scheduled_subtasks):
            nav_time = (
                0
                if i == 0
                else self._calc_navigate_time(scheduled_subtasks[i - 1], subtask)
            )
            current_node = self.tree.add_subtask_node(
                current_node, subtask, navigate_time=nav_time
            )
            separation_interval -= subtask.duration.interval + nav_time

        if separation_interval > 0 and is_time_critical:
            # Add a wait node if there's leftover separation time
            current_node = self.tree.add_wait_node(
                parent=current_node,
                subtask_name="Time-Critical Wait",
                wait_time=separation_interval,
            )

        # Now expand from the next subtask if possible
        if updated_remaining:
            next_subtask = updated_remaining[0]
            cost, child_node, new_remaining = self._expand_node(
                parent_node=current_node,
                child_candidate=next_subtask,
                remaining_subtasks=updated_remaining,
                parent_depth=current_depth,
            )
            if child_node:
                # Only append to simulated_paths if at top-level (current_depth == 0)
                if current_depth == 0:
                    simulated_paths.append(
                        (
                            total_cost + cost,
                            current_depth + 1,
                            next_subtask,
                            new_remaining,
                        )
                    )

    def _simulate_normal_case(
        self,
        node_state: Node,
        subtasks_state: List[Any],
        queue: PriorityQueue,
        total_cost: int,
        current_depth: int,
        simulated_paths: List[Tuple[int, int, Any, List[Any]]],
    ):
        """
        Normal expansion case: expand feasible subtasks (no separation interval).
        """
        expandable_subtasks = self.constraint_handler.get_expandable_subtasks(
            node_state, subtasks_state
        )
        for subtask in expandable_subtasks:
            cost, child_node, updated_remaining = self._expand_node(
                parent_node=node_state,
                child_candidate=subtask,
                remaining_subtasks=subtasks_state,
                parent_depth=current_depth,
            )
            if child_node:
                # Add the new state to the queue
                queue.put(
                    (
                        total_cost + cost,
                        current_depth + 1,
                        next(self._counter),
                        child_node,
                        updated_remaining,
                    )
                )
                # If this is the first level of expansion, we save a path
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
        parent_node: Node,
        child_candidate: Any,
        remaining_subtasks: List[Any],
        parent_depth: int,
    ) -> Tuple[int, Optional[Node], List[Any]]:
        """
        Expands a child candidate and returns (cost, new_child_node, new_remaining).
        """
        # Retrieve constraints
        outgoing_ts, incoming_ts = self.constraint_handler.get_temporal_constraints(
            child_candidate.name
        )

        if outgoing_ts is None or incoming_ts is None:
            log.warning(
                f"Subtask '{child_candidate.name}' has no valid time slot. Skipping."
            )
            return float("inf"), None, remaining_subtasks

        # Calculate navigation time
        navigate_time = self._calc_navigate_time(parent_node, child_candidate)

        # Actually create the child node in the real tree:
        child_node = self.tree.add_subtask_node(
            parent_node, child_candidate, navigate_time
        )
        new_remaining = [
            s for s in remaining_subtasks if s.name != child_candidate.name
        ]

        # Example cost formula
        cost_val = (COST_WEIGHT - parent_depth) * (
            child_candidate.duration.interval
            + navigate_time
            + (incoming_ts[0] - outgoing_ts[0])
        )
        return cost_val, child_node, new_remaining

    def fill_time_slot(
        self,
        remaining_subtasks: List[Any],
        temporal_constraint: Tuple[int, bool],
        beam_width: int = 3,
        max_depth: int = 10,
    ) -> Tuple[List[Any], List[Any]]:
        """
        Beam Search를 사용하여, 'separation_interval' 내에 들어갈 수 있는
        '최적(또는 근사 최적) subtask 조합'을 찾는 예시 함수.

        Args:
            remaining_subtasks: 아직 스케줄링되지 않은 서브태스크 리스트
            temporal_constraint: (separation_interval, is_time_critical)
            beam_width: 한 번의 레벨 확장에서 유지할 후보(상태) 개수
            max_depth: 탐색 최대 깊이 (필요 시 제한, 없으면 'remaining_subtasks' 개수 등으로 설정)

        Returns:
            (scheduled_subtasks, updated_remaining)
            - scheduled_subtasks: 선택된 subtask들의 최적(또는 근사 최적) 조합
            - updated_remaining: 선택 후 남은 subtasks
        """
        import heapq  # Python의 우선순위 큐 모듈 (PriorityQueue도 가능)

        separation_interval, _ = temporal_constraint

        # 상태 정의:
        #   - total_time: 현재까지 누적 소요시간 (작업 + 이동)
        #   - depth: 현재까지 선택한 subtask 수 (또는 검색 깊이)
        #   - combo: 현재까지 선택된 subtask 목록
        #   - tasks_left: 남은 subtask 목록
        #
        # 우선순위 큐(힙)에서는 (cost, state_id, total_time, depth, combo, tasks_left) 순으로 관리
        #   - cost: 최소화/최대화하고 싶은 값
        #   - state_id: tie-breaking용 (heapq는 동점(cost 동일) 시 비교가 필요)
        #   - 나머지는 실제 상태 정보

        # 여기서는 "사용한 시간(total_time)을 많이 쓰는 것이 좋다"고 가정 →
        #   "음수(-total_time)"를 cost로 두어, heap에서 cost가 더 작을수록(= -time이 더 작을수록) = time이 더 클수록 우선.
        # 즉, "total_time" 최대화 = "cost = -total_time" 최소화

        initial_state = (0.0, 0, 0.0, 0, [], remaining_subtasks)
        # cost=0.0, state_id=0, total_time=0.0, depth=0, combo=[], tasks_left=remaining_subtasks

        # 파이썬 heapq는 "오름차순(작은 값 우선)"이므로,
        # "total_time 최대화"를 위해 cost = -total_time 사용
        heap = []
        heapq.heappush(heap, initial_state)

        visited_states = set()
        best_combo = []
        best_time = 0.0
        state_counter = 1  # tie-breaking용

        current_depth = 0

        while heap and current_depth <= max_depth:
            # 1) 한 레벨에서 확장할 후보를 최대 beam_width개까지 꺼낸다
            level_candidates = []
            for _ in range(beam_width):
                if not heap:
                    break
                level_candidates.append(heapq.heappop(heap))

            # 2) 각 후보를 확장
            for cost, _, total_time, depth, combo, tasks_left in level_candidates:
                # 현재 상태가 이미 best라면 갱신
                if total_time > best_time:
                    best_time = total_time
                    best_combo = combo

                if depth >= max_depth:
                    # 더 이상 깊이 확장 불가
                    continue

                # 남은 subtasks 각각을 시도해본다
                for subtask in tasks_left:
                    # 이동 시간 계산
                    if combo:
                        prev_subtask = combo[-1]
                        nav_time = self._calc_navigate_time(prev_subtask, subtask)
                    else:
                        nav_time = 0.0

                    needed = subtask.duration.interval + nav_time
                    new_total = total_time + needed

                    # separation_interval 안에 들어가는지 검사
                    if new_total <= separation_interval:
                        new_combo = combo + [subtask]
                        new_tasks_left = [
                            t for t in tasks_left if t.name != subtask.name
                        ]
                        new_depth = depth + 1

                        # cost = -new_total (total_time을 최대화하려면 cost를 -로)
                        new_cost = -new_total

                        # tie-breaking용 state_counter 사용
                        new_state = (
                            new_cost,
                            state_counter,
                            new_total,
                            new_depth,
                            new_combo,
                            new_tasks_left,
                        )
                        state_counter += 1

                        # 중복 상태 체크(간단히 combo와 total_time만으로 해볼 수 있음)
                        state_sig = (
                            tuple(sorted([st.name for st in new_combo])),
                            round(new_total, 2),
                        )
                        if state_sig not in visited_states:
                            visited_states.add(state_sig)
                            heapq.heappush(heap, new_state)

            current_depth += 1  # 다음 레벨로

        # 최종 best_combo가 separation_interval 내에서 가장 total_time이 큰 조합
        scheduled_subtasks = best_combo
        updated_remaining = [
            t for t in remaining_subtasks if t not in scheduled_subtasks
        ]
        return scheduled_subtasks, updated_remaining

    #######################
    # TIME & PATH HELPERS #
    #######################

    def _calculate_time_slot(self, node: Node) -> Tuple[int, bool]:
        """
        Get the outgoing time slot (separation interval, is_critical) for the node.
        Default to (0, False) if no constraints exist.
        """
        try:
            outgoing_ts, incoming_ts = self.constraint_handler.get_temporal_constraints(
                node.name
            )
            if not outgoing_ts:
                log.warning(
                    f"No time slot available for node {node.name}. Defaulting to 0."
                )
                return 0, False
            # The outgoing time slot is of form (duration, critical)
            # Make sure you handle them correctly: outgoing_ts could be (duration_value, is_critical_bool)
            separation = outgoing_ts[0]  # e.g. 120
            is_critical = outgoing_ts[1] if len(outgoing_ts) > 1 else False
            return separation, is_critical
        except Exception as e:
            log.error(f"Error calculating time slot for node {node.name}: {e}")
            return 0, False

    def _calc_navigate_time(self, source_node: Node, target_subtask: Any) -> float:
        """
        Look up navigation time between source and target using `self.navigation_times`.
        """
        # 1) Get subtask info from source node
        source_subtask_info = next(
            (s for s in self.subtasks_info if s.name == source_node.name), None
        )
        if not source_subtask_info:
            log.warning(
                f"Source subtask '{source_node.name}' not found in subtasks_info."
            )
            return float("inf")

        # 2) Find the last NAVIGATE_TO in the source subtask
        source_actions = source_subtask_info.execution.primitive_actions
        last_location = next(
            (
                action.split()[-1]
                for action in reversed(source_actions)
                if action.startswith("NAVIGATE_TO")
            ),
            None,
        )
        if not last_location:
            log.warning(
                f"No 'NAVIGATE_TO' action found in source subtask '{source_node.name}'."
            )
            return float("inf")

        # 3) Find the first NAVIGATE_TO in the target subtask
        target_actions = target_subtask.execution.primitive_actions
        first_location = next(
            (
                action.split()[-1]
                for action in target_actions
                if action.startswith("NAVIGATE_TO")
            ),
            None,
        )
        if not first_location:
            log.warning(
                f"No 'NAVIGATE_TO' action found in target subtask '{target_subtask.name}'."
            )
            return float("inf")

        # 4) Lookup in navigation_times
        #    In your code, it's done by matching keys that start with the location names
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
                if first_location in k
            ),
            None,
        )
        if not matched_target_key:
            log.warning(
                f"No target key matched for '{first_location}' under '{matched_source_key}' in navigation times."
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
            f"Navigation time from '{last_location}' to '{first_location}' is {move_time}."
        )
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
