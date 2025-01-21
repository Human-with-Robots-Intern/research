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

# ------------------------------------------------
# 설정 상수
# ------------------------------------------------
COST_WEIGHT = 3
DEFAULT_SIMULATION_DEPTH = 3  # 3-step lookahead
DEFAULT_BEAM_WIDTH = 2


class TaskTree:
    """
    Tree 구조에 실제 확정된 Subtask(또는 Wait)를 차례로 추가 관리.
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
        return self._add_node(
            parent=parent,
            name=f"Wait for {subtask_name}",
            start=parent.end,
            end=parent.end + wait_time,
        )

    def add_subtask_node(
        self, parent: Node, subtask: "Subtask", navigate_time: int = 0
    ) -> Node:
        return self._add_node(
            parent=parent,
            name=subtask.name,
            start=parent.end,
            end=parent.end + navigate_time + subtask.duration.interval,
        )


class SimulationState(NamedTuple):
    """
    시뮬레이션 중 임시 상태 (partial_plan, remaining_subtasks 등)
    """

    name: str  # 마지막으로 실행된 subtask 이름 (또는 "Init")
    partial_plan: List[Any]  # 지금까지 실행한 Subtask/Wait 시퀀스
    remaining_subtasks: List[Any]  # 아직 실행 안 한 Subtask 목록


class TaskTreeBuilder:
    """
    N-step (기본 3-step) Lookahead 후, cost가 가장 낮은 경로의 "첫 Subtask"만 트리에 확정하는 방식.
    - 기존 코드의 휴리스틱/비용 함수와 Time-Slot 로직을 최대한 보존하되,
      depth별 탐색 및 cost 누적 문제를 수정.
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

        # 핸들러
        self.constraint_handler = constraint_handler or ConstraintHandler(constraints)
        self.slot_handler = slot_handler or SlotHandler(self._expand_node)
        # 기타
        self.navigation_times = load_navigation_times()
        self.subtasks_info = None

        # 우선순위큐 tie-breaker (count)
        self._counter = itertools.count()

    def build_tree(self, tasks: List[Any]) -> Node:
        """
        전체 파이프라인:
        - 남은 Subtask가 있을 때까지:
          1) depth=3까지 lookahead
          2) 그 중 cost가 최소인 경로 골라, "첫 Subtask"만 Tree에 확정
          3) state 업데이트
        - 반복
        """
        remaining_subtasks = tasks_to_subtasks(tasks)
        self.subtasks_info = copy.deepcopy(remaining_subtasks)

        current_node = self.tree.root_node
        current_state = SimulationState(
            name="Init",
            partial_plan=[],
            remaining_subtasks=remaining_subtasks,
        )

        while current_state.remaining_subtasks:
            # 1) 3-step lookahead 확장
            simulated_paths = self._simulate_expansion(current_state)

            if not simulated_paths:
                log.warning("No valid paths found. Stopping expansion.")
                break

            # 2) 후보들을 정렬/프루닝하여 best 1개 선택
            best_path, _ = self._prune_simulated_paths(simulated_paths)
            if not best_path:
                log.warning("All expansions invalid. Stopping.")
                break

            best_cost, best_depth, last_subtask, best_remain, best_plan = best_path
            if not best_plan:
                log.warning("Best path has empty plan. Stopping.")
                break

            # "첫 Subtask"만 실제 트리에 반영
            first_subtask = best_plan[0]
            if first_subtask.name.startswith("Wait for"):
                # 대기 노드
                wait_time = first_subtask.duration
                current_node = self.tree.add_wait_node(
                    parent=current_node,
                    subtask_name=first_subtask.name,
                    wait_time=wait_time,
                )
            else:
                # 일반 Subtask
                nav_time = self._calc_navigate_time(current_state, first_subtask)
                current_node = self.tree.add_subtask_node(
                    parent=current_node,
                    subtask=first_subtask,
                    navigate_time=nav_time,
                )

            # 3) state 업데이트 (chosen_subtask만큼 제거)
            updated_remaining = [
                s
                for s in current_state.remaining_subtasks
                if s.name != first_subtask.name
            ]
            new_plan = current_state.partial_plan + [first_subtask]
            current_state = SimulationState(
                name=first_subtask.name,
                partial_plan=new_plan,
                remaining_subtasks=updated_remaining,
            )

        return self.tree.root_node

    # ------------------------------------------------
    #   1) LOOKAHEAD 시뮬레이션 (최대 depth=3)
    # ------------------------------------------------
    def _simulate_expansion(
        self, state: SimulationState
    ) -> List[Tuple[float, int, Any, List[Any], List[Any]]]:
        """
        state부터 depth=3까지 확장.
        return: List of (total_cost, depth, last_subtask, remaining_subtasks, plan)
        """

        # 큐: (accum_cost, depth, order, SimulationState)
        queue = PriorityQueue()
        # 초기 상태
        queue.put((0.0, 0, next(self._counter), state))

        simulated_paths: List[Tuple[float, int, Any, List[Any], List[Any]]] = []

        while not queue.empty():
            curr_cost, curr_depth, _, curr_state = queue.get()

            # depth 한계 도달 -> 더 이상 확장 X, 현재 시나리오를 leaf로 저장
            if curr_depth >= self.simulation_depth:
                last_subtask = (
                    curr_state.partial_plan[-1] if curr_state.partial_plan else None
                )
                simulated_paths.append(
                    (
                        curr_cost,
                        curr_depth,
                        last_subtask,
                        curr_state.remaining_subtasks,
                        curr_state.partial_plan,
                    )
                )
                continue

            # time slot 검사
            out_ts = self.constraint_handler.get_temporal_constraints(
                curr_state.name, type="out"
            )
            separation_interval, is_time_critical, related_subtask = out_ts

            if separation_interval > 0:
                # 슬롯 로직
                self._simulate_time_slot_case(
                    total_cost=curr_cost,
                    current_depth=curr_depth,
                    current_state=curr_state,
                    simulated_paths=simulated_paths,
                    temporal_constraint=out_ts,
                    queue=queue,
                )
            else:
                # 일반 로직
                self._simulate_normal_case(
                    total_cost=curr_cost,
                    current_depth=curr_depth,
                    current_state=curr_state,
                    simulated_paths=simulated_paths,
                    queue=queue,
                )

        return simulated_paths

    def _simulate_normal_case(
        self,
        total_cost: float,
        current_depth: int,
        current_state: SimulationState,
        simulated_paths: List[Tuple[float, int, Any, List[Any], List[Any]]],
        queue: PriorityQueue,
    ):
        """
        슬롯이 아닌 일반 확장 케이스
        - get_expandable_subtasks(...)로 feasible한 subtask 전개
        """
        feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
            current_state
        )
        for child_subtask in feasible_subtasks:
            # expand
            cost_val, new_remaining = self._expand_node(
                total_cost=total_cost,
                current_depth=current_depth,
                current_state=current_state,
                child_candidate=child_subtask,
                queue=queue,
            )
            # partial plan 업데이트
            new_plan = current_state.partial_plan + [child_subtask]
            last_subtask = child_subtask
            new_cost = total_cost + cost_val
            new_depth = current_depth + 1

            # 현재 스텝에서도 결과를 저장(beam 관리 위해)
            simulated_paths.append(
                (new_cost, new_depth, last_subtask, new_remaining, new_plan)
            )

    # ------------------------------------------------
    #   2) TIME-SLOT 로직
    # ------------------------------------------------
    def _simulate_time_slot_case(
        self,
        total_cost: float,
        current_depth: int,
        current_state: SimulationState,
        simulated_paths: List[Tuple[float, int, Any, List[Any], List[Any]]],
        temporal_constraint: Tuple[Any, ...],
        queue: PriorityQueue,
    ):
        """
        separation_interval 내에서 가능한 subtask 여러 개를 배치해볼 수 있음.
        - 최종적으로 slot 종료 시점(또는 전부 배치 불가 시점)에 한 번에 "하나의 완성된 시나리오"로 처리
        - cost 누적 주의
        """
        separation_interval, is_time_critical, related_subtask = temporal_constraint

        # slot 내 subtask 배치 후보를 관리할 우선순위큐
        # 항목: ( (-subtask_count, slot_cost), order, leftover, global_cost, partial_plan, remain )
        #  - subtask_count가 많을수록 우선 (음수로 넣어서 내림차순)
        #  - slot_cost: 슬롯 내에서만 소모된 실행시간 (단순 참고용)
        #  - global_cost: 지금까지 누적된 전체 cost(휴리스틱)
        mini_queue = PriorityQueue()
        mini_queue.put(
            (
                (0, 0.0),
                next(self._counter),
                separation_interval,
                total_cost,
                current_state.partial_plan[:],
                current_state.remaining_subtasks[:],
            )
        )

        # 슬롯 안에서 만들어진 시나리오들
        filled_scenarios = []

        while not mini_queue.empty():
            (
                (neg_count, slot_cost),
                _,
                leftover,
                global_cost,
                plan_so_far,
                remain_so_far,
            ) = mini_queue.get()
            subtask_count = -neg_count

            # slot 내부에서 배치 가능한 subtask 찾기
            virtual_state = SimulationState(
                name=current_state.name,
                partial_plan=plan_so_far,
                remaining_subtasks=remain_so_far,
            )
            feasible_subtasks = self.constraint_handler.get_expandable_subtasks(
                virtual_state
            )

            # 남은 leftover에 들어갈 수 있는 것만 필터
            expandables = []
            for candidate in feasible_subtasks:
                # slot과 directly 연관된 subtask는 배치 순서상 나중에? (기존 코드 로직 유지)
                if candidate.name == related_subtask:
                    continue
                # 내비게이션 시간
                nav_time = self._calc_navigate_time(virtual_state, candidate)

                single_cost_val = nav_time + candidate.duration.interval
                total_dur = candidate.duration.interval + nav_time

                if total_dur <= leftover:
                    expandables.append((candidate, single_cost_val))

            if expandables:
                # slot 안에 더 배치 가능
                for cand_subtask, sub_cost_val in expandables:
                    nav_time = self._calc_navigate_time(virtual_state, cand_subtask)
                    total_dur = cand_subtask.duration.interval + nav_time

                    # 새로운 global cost
                    new_global_cost = global_cost + sub_cost_val
                    new_leftover = leftover - total_dur
                    new_plan = plan_so_far + [cand_subtask]
                    new_remain = [
                        r for r in remain_so_far if r.name != cand_subtask.name
                    ]

                    mini_queue.put(
                        (
                            (-(subtask_count + 1), slot_cost + total_dur),
                            next(self._counter),
                            new_leftover,
                            new_global_cost,
                            new_plan,
                            new_remain,
                        )
                    )
            else:
                # 더 넣을 subtask가 없다. leftover가 남았다면 "Wait" 처리
                if leftover > 0:
                    wait_sub = Subtask(
                        task_name=None,
                        name=(
                            f"Wait for {related_subtask}" if related_subtask else "Idle"
                        ),
                        duration=leftover,
                        repetition=1,
                        type="Wait",
                        execution=None,
                        temporal_constraints=None,
                    )
                    # wait도 cost 계산
                    wait_cost_val = self._calc_wait_cost(current_depth, wait_sub)
                    final_cost = global_cost + wait_cost_val
                    final_plan = plan_so_far + [wait_sub]

                    # slot 종료 후 depth+1
                    filled_scenarios.append(
                        (
                            subtask_count,
                            final_cost,
                            current_depth + 1,
                            final_plan,
                            remain_so_far[:],
                        )
                    )
                else:
                    # leftover=0, 그대로 종료
                    filled_scenarios.append(
                        (
                            subtask_count,
                            global_cost,
                            current_depth + 1,
                            plan_so_far[:],
                            remain_so_far[:],
                        )
                    )

            # slot 내에서도 beam 폭 제한
            if mini_queue.qsize() > (self.beam_width * 20):
                temp_list = []
                while not mini_queue.empty():
                    temp_list.append(mini_queue.get())
                temp_list.sort(
                    key=lambda x: x[0]
                )  # x[0] = (-(count), slot_cost) 오름차순
                for item in temp_list[: self.beam_width * 10]:
                    mini_queue.put(item)

        # slot에서 나온 시나리오들 정렬 (subtask_count 많은 것 우선 -> cost 낮은 것 우선)
        filled_scenarios.sort(key=lambda x: (-x[0], x[1]))
        top_scenarios = filled_scenarios[: self.beam_width]

        # top_scenarios: (subtask_count, final_cost, new_depth, plan, remain)
        for sc in top_scenarios:
            sc_count, sc_cost, sc_depth, sc_plan, sc_remain = sc
            last_sub = sc_plan[-1] if sc_plan else None

            # 시뮬레이션 결과로 기록
            simulated_paths.append((sc_cost, sc_depth, last_sub, sc_remain, sc_plan))

            # depth가 simulation_depth 미만이면 queue에 넣어 더 확장
            if sc_depth < self.simulation_depth:
                new_state = SimulationState(
                    name=last_sub.name if last_sub else current_state.name,
                    partial_plan=sc_plan,
                    remaining_subtasks=sc_remain,
                )
                queue.put((sc_cost, sc_depth, next(self._counter), new_state))

    # ------------------------------------------------
    #   EXPAND NODE (실제 휴리스틱 COST 계산)
    # ------------------------------------------------
    def _expand_node(
        self,
        total_cost: float,
        current_depth: int,
        current_state: SimulationState,
        child_candidate: Subtask,
        queue: PriorityQueue,
    ) -> Tuple[float, List[Any]]:
        """
        사용자 기존 휴리스틱 공식을 그대로 사용:
          cost_val = (COST_WEIGHT - current_depth) * (
              child_candidate.duration.interval + navigate_time + (incoming_ts[0] - outgoing_ts[0])
          )
        """
        # in/out TS
        outgoing_ts = self.constraint_handler.get_temporal_constraints(
            child_candidate.name, type="out"
        )
        incoming_ts = self.constraint_handler.get_temporal_constraints(
            child_candidate.name, type="in"
        )

        nav_time = self._calc_navigate_time(current_state, child_candidate)
        cost_val = self._calc_heuristic_cost(
            current_depth, child_candidate, nav_time, incoming_ts, outgoing_ts
        )

        new_remaining = [
            s
            for s in current_state.remaining_subtasks
            if s.name != child_candidate.name
        ]
        new_plan = current_state.partial_plan + [child_candidate]

        new_state = SimulationState(
            name=child_candidate.name,
            partial_plan=new_plan,
            remaining_subtasks=new_remaining,
        )

        new_total_cost = total_cost + cost_val
        new_depth = current_depth + 1

        # 아직 depth가 한계 이하이면 queue에 넣어 더 확장
        if new_depth <= self.simulation_depth:
            queue.put((new_total_cost, new_depth, next(self._counter), new_state))

        return cost_val, new_remaining

    # ------------------------------------------------
    #   COST 계산 함수들 (사용자 휴리스틱 그대로)
    # ------------------------------------------------
    def _calc_heuristic_cost(
        self,
        current_depth: int,
        subtask: Subtask,
        navigate_time: float,
        incoming_ts: Tuple[int, bool, Any],
        outgoing_ts: Tuple[int, bool, Any],
    ) -> float:
        """
        기존 코드에서 사용하던 공식 보존:
          cost_val = (COST_WEIGHT - current_depth) * (
              subtask.duration.interval
              + navigate_time
              + (incoming_ts[0] - outgoing_ts[0])
          )
        """
        separation_in_in, _, _ = incoming_ts
        separation_in_out, _, _ = outgoing_ts

        # 음수가 될 수도 있으므로, 혹은 0이 될 수도 있으므로, 실제 로직은 필요에 따라 보정 가능
        time_diff = separation_in_in - separation_in_out

        factor = max(
            COST_WEIGHT - current_depth, 1
        )  # depth가 커질 때 음수가 되지 않도록
        cost_val = factor * (subtask.duration.interval + navigate_time + time_diff)
        return cost_val

    def _calc_wait_cost(self, current_depth: int, wait_subtask: Subtask) -> float:
        """
        Wait 노드에 대한 비용 (사용자가 원하는 방식대로 지정 가능).
        간단히: (COST_WEIGHT - depth)* duration 정도로 처리
        """

        return wait_subtask.duration

    # ------------------------------------------------
    #   NAVIGATION
    # ------------------------------------------------
    def _calc_navigate_time(
        self, current_state: SimulationState, child_subtask: Subtask
    ) -> float:
        if current_state.name.startswith("Wait") or child_subtask.name.startswith(
            "Wait"
        ):
            return 0.0
        if current_state.name == "Init":
            last_location = "agent"
        else:
            last_location = self._find_last_location(current_state)
            if not last_location:
                last_location = "agent"

        target_location = self._find_first_location(child_subtask)
        if not target_location:
            return 0.0

        move_time = self._lookup_navigation_time(last_location, target_location)
        return move_time

    def _find_last_location(self, state: SimulationState) -> Optional[str]:
        # partial_plan 뒤에서부터 탐색
        for subtask in reversed(state.partial_plan):
            if subtask.name.startswith("Wait"):
                continue
            # subtask_info 검색
            subtask_info = next(
                (s for s in self.subtasks_info if s.name == subtask.name), None
            )
            if (
                subtask_info
                and subtask_info.execution
                and subtask_info.execution.primitive_actions
            ):
                # 거꾸로 순회
                for action in reversed(subtask_info.execution.primitive_actions):
                    if action.startswith("NAVIGATE_TO"):
                        return action.split()[-1]
        return None

    def _find_first_location(self, subtask: Subtask) -> Optional[str]:
        if subtask.execution and subtask.execution.primitive_actions:
            for action in subtask.execution.primitive_actions:
                if action.startswith("NAVIGATE_TO"):
                    return action.split()[-1]
        return None

    def _lookup_navigation_time(
        self, last_location: str, target_location: str
    ) -> float:
        matched_source_key = next(
            (k for k in self.navigation_times if k.startswith(last_location)), None
        )
        if not matched_source_key:
            log.warning(
                f"No source key matched for '{last_location}' in navigation times."
            )
            return 0.0

        matched_target_key = next(
            (
                k
                for k in self.navigation_times[matched_source_key]
                if target_location in k
            ),
            None,
        )
        if not matched_target_key:
            log.warning(
                f"No target key matched for '{target_location}' under '{matched_source_key}'."
            )
            return 0.0

        move_time = self.navigation_times[matched_source_key].get(
            matched_target_key, None
        )
        if move_time is None:
            log.warning(
                f"Navigation time from '{matched_source_key}' to '{matched_target_key}' not found."
            )
            return 0.0
        return move_time

    # ------------------------------------------------
    #   PRUNE (Beam)
    # ------------------------------------------------
    def _prune_simulated_paths(
        self, paths: List[Tuple[float, int, Any, List[Any], List[Any]]]
    ) -> Tuple[
        Optional[Tuple[float, int, Any, List[Any], List[Any]]],
        List[Tuple[float, int, Any, List[Any], List[Any]]],
    ]:
        """
        paths: (cost, depth, last_subtask, remain, plan)
        cost 기준 오름차순 정렬 후 상위 beam_width만 남김
        """
        if not paths:
            return None, []

        sorted_paths = sorted(paths, key=lambda x: x[0])  # cost ascending
        pruned = sorted_paths[: self.beam_width]

        best_path = pruned[0] if pruned else None
        return best_path, pruned
