import copy
import heapq
import math
from typing import Optional, Tuple

from core.task import Subtask
from ithor.utils.math_utils import _adjust_if_unreachable
from scheduler.dataclass import SimulationNode
from utils.constants import (
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    PRIMITIVE_ACTION_SET,
)
from utils.util import create_module_logger

log = create_module_logger(__name__, is_file_handler=True)


class ActionHandler:
    def __init__(self, nav_graph):
        self.nav_graph = nav_graph

    def simulate_navigate_actions(
        self, current_node: SimulationNode, primitive_actions: list[str]
    ) -> Tuple[float, float, dict[str, Tuple[float, float, float]], Optional[str]]:
        scene_positions = copy.deepcopy(current_node.state.scene_positions)
        held_object = copy.deepcopy(current_node.state.held_object)
        total_nav_time = 0.0
        total_action_time = 0.0

        for prim_action in primitive_actions:
            tokens = prim_action.split()
            if not tokens:
                continue
            action = tokens[0].upper()
            target_obj_id = tokens[1] if len(tokens) > 1 else None
            partial_str = tokens[2] if len(tokens) > 2 else None

            if (
                action != "GRASP"
                and target_obj_id
                and target_obj_id not in scene_positions
            ):
                log.error(f"Object {target_obj_id} not in scene_positions.")
                raise ValueError(f"Object {target_obj_id} not in scene_positions.")

            if action == "NAVIGATE_TO":
                navigate_path = self._find_shortest_path(
                    scene_positions["agent"], scene_positions[target_obj_id]
                )
                if partial_str is None:
                    nav_time = (len(navigate_path) - 1) * NAV_STEP_DURATION
                    if navigate_path:
                        scene_positions["agent"] = navigate_path[-1]
                else:
                    try:
                        nav_val = float(partial_str)
                    except ValueError:
                        nav_val = (len(navigate_path) - 1) * NAV_STEP_DURATION
                        log.warning(
                            f"Invalid partial time '{partial_str}', using {nav_val}"
                        )
                    steps = int(math.floor(nav_val / NAV_STEP_DURATION))
                    steps = max(0, min(steps, len(navigate_path) - 1))
                    nav_time = nav_val
                    if navigate_path:
                        scene_positions["agent"] = navigate_path[steps]
                total_nav_time += nav_time
                total_action_time += nav_time

            elif action == "GRASP":
                if held_object is not None:
                    raise ValueError(f"Already holding {held_object}")
                held_object = target_obj_id
                total_action_time += PRIMITIVE_ACTION_DURATION

            elif action in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                if held_object is None:
                    raise ValueError("No object in hand to place.")
                scene_positions[held_object] = scene_positions[target_obj_id]
                held_object = None
                total_action_time += PRIMITIVE_ACTION_DURATION

            elif action in PRIMITIVE_ACTION_SET:
                total_action_time += PRIMITIVE_ACTION_DURATION
            else:
                raise ValueError(f"Unknown action name: {action}")

        return total_nav_time, total_action_time, scene_positions, held_object

    def _find_shortest_path(
        self, start_pos: Tuple[float, float, float], end_pos: Tuple[float, float, float]
    ) -> list[Tuple[float, float, float]]:
        start_pos = _adjust_if_unreachable(start_pos)
        end_pos = _adjust_if_unreachable(end_pos)
        if start_pos == end_pos:
            return [start_pos]

        def direction(a, b):
            return (b[0] - a[0], b[2] - a[2])

        pq = []
        heapq.heappush(pq, (0, start_pos, None, [start_pos]))
        visited = {}

        while pq:
            turn_cnt, cur_pos, cur_dir, path = heapq.heappop(pq)
            if cur_pos == end_pos:
                return path
            if cur_pos in visited and visited[cur_pos] <= turn_cnt:
                continue
            visited[cur_pos] = turn_cnt
            for nxt in self.nav_graph.get(cur_pos, []):
                if nxt in path:
                    continue
                new_dir = direction(cur_pos, nxt)
                nxt_turn = (
                    turn_cnt
                    if (cur_dir is None or new_dir == cur_dir)
                    else (turn_cnt + 1)
                )
                new_path = path + [nxt]
                heapq.heappush(pq, (nxt_turn, nxt, new_dir, new_path))

        raise ValueError(f"No path found from {start_pos} to {end_pos}.")
