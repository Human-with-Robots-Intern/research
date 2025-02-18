# math_utils.py

import heapq
import math
from typing import Callable, Dict, List, Set, Tuple

from ..utils.constants import GRID_SIZE


def build_navigation_graph(
    controller,
) -> Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]:
    """
    AI2THOR에서 한 번만 호출해서 reachable positions를 받아,
    '대각 이동 없이' 한 축만 차이 나는 위치들끼리 연결한 그래프를 만든다.
    """
    positions_data = controller.step("GetReachablePositions").metadata["actionReturn"]
    positions = [quantize_position((p["x"], p["y"], p["z"])) for p in positions_data]

    neighbors = {}
    for pos in positions:
        neighbors[pos] = set()

    for pos in positions:
        for other in positions:
            if pos == other:
                continue
            dx = abs(pos[0] - other[0])
            dy = abs(pos[1] - other[1])
            dz = abs(pos[2] - other[2])
            # 원본처럼 sum(dx,dy,dz) == GRID_SIZE 면 neighbor
            if (dx + dy + dz) == GRID_SIZE:
                neighbors[pos].add(other)

    return neighbors


def find_shortest_path(
    nav_graph: Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]],
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
) -> List[Tuple[float, float, float]]:
    """
    원본 코드와 동일하게 BFS + 회전(turn) 최소화를 구현한다.

    - nav_graph: build_navigation_graph() 로 생성된 이웃 정보
    - is_reachable_func: pos가 유효한지(또는 nav_graph에 들어있는지) 검사
    - adjust_to_reachable_func: pos가 unreachable일 때 가까운 reachable로 조정(원하면 여러 번 시도 가능)
    """

    # (A) 시작/끝이 reachable하지 않으면 조정
    start = _adjust_if_unreachable(start)
    end = _adjust_if_unreachable(end)

    # 같으면 바로 반환
    if start == end:
        return [start]

    def direction_vec(a, b):
        # y(고도)는 무시, (dx, dz)만 비교
        return (b[0] - a[0], b[2] - a[2])

    # 우선순위큐 (turn_count, current_pos, direction, path)
    pq = []
    heapq.heappush(pq, (0, start, None, [start]))
    visited = {}

    while pq:
        turn_count, current_pos, current_dir, path = heapq.heappop(pq)

        if current_pos == end:
            return path

        if current_pos in visited and visited[current_pos] <= turn_count:
            continue
        visited[current_pos] = turn_count

        # 이웃 탐색
        for nxt in nav_graph.get(current_pos, []):
            if nxt in path:  # cycle 방지
                continue

            new_dir = direction_vec(current_pos, nxt)
            if current_dir is None or current_dir == new_dir:
                new_turn = turn_count
            else:
                new_turn = turn_count + 1

            new_path = path + [nxt]
            heapq.heappush(pq, (new_turn, nxt, new_dir, new_path))

    raise ValueError(f"No path found from {start} to {end} with BFS-turn logic.")


def _is_reachable(self, pos) -> bool:
    # nav_graph에 키로 있으면 reachable이라 가정
    pos = quantize_position(pos)
    return pos in self.nav_graph


def _adjust_to_reachable(self, pos):
    # unreachable이면 nav_graph 중 가장 가까운 위치로 보정
    pos = quantize_position(pos)
    if pos in self.nav_graph:
        return pos
    # 없으면 전체 노드 중 최단거리
    all_reachable = list(self.nav_graph.keys())
    return closest_position(pos, all_reachable)


def _adjust_if_unreachable(
    pos: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """
    단순히 unreachable이면 한 번 adjust_func로 조정.
    필요하면 while문을 쓸 수도 있다.
    """
    while not _is_reachable(pos):
        pos = _adjust_to_reachable(pos)
    return pos


def closest_grid_point(pos):
    """Helper function to find the closest grid point to a given position."""
    return tuple(round(coord, 1) for coord in pos)


def closest_position(object_position, reachable_positions):
    """Find the closest reachable position to the given object."""
    min_distance = float("inf")
    closest = reachable_positions[0]
    for pos in reachable_positions:
        dist = euclidean_distance(object_position, pos)
        if dist < min_distance:
            min_distance = dist
            closest = pos
    return closest


def quantize_position(pos):
    return tuple(round(coord / GRID_SIZE) * GRID_SIZE for coord in pos)


def euclidean_distance(pointA, pointB):
    """Compute the Euclidean distance between two 3D points."""
    return (
        (pointA[0] - pointB[0]) ** 2
        + (pointA[1] - pointB[1]) ** 2
        + (pointA[2] - pointB[2]) ** 2
    ) ** 0.5


def calculate_rotation_angle(agent_position, object_position):
    agent_x = agent_position[0]
    agent_z = agent_position[2]
    obj_x = object_position[0]
    obj_z = object_position[2]

    a = euclidean_distance([agent_x, agent_z], [obj_x, obj_z])
    b = euclidean_distance([agent_x, agent_z], [agent_x - 2, agent_z])
    c = euclidean_distance([obj_x, obj_z], [agent_x - 2, agent_z])

    gamma = math.degrees(math.acos((a**2 + b**2 - c**2) / (2 * a * b)))
    return gamma
