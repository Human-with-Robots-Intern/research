# math_utils.py
import json
import math
from typing import Dict, Set, Tuple

from src.utils.common import create_module_logger
from src.utils.config.constants import GRID_SIZE, SCENE_KNOWLEDGE_PATH

log = create_module_logger(module_name=__name__, module_log=True)


def load_navigation_graph(
    controller,
) -> Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]]:
    """
    씬의 모든 문을 연 상태의 '마스터 네비게이션 그래프'를 생성하고 캐싱합니다.

    - 캐시 파일이 있으면 그래프를 파일에서 로드합니다.
    - 없으면, 모든 문을 열고 그래프를 생성한 뒤 파일로 저장하고,
      문의 상태는 원래대로 복원합니다.
    """
    scene_name = controller.scene
    cache_file = SCENE_KNOWLEDGE_PATH / f"{scene_name}_master_graph.json"

    if cache_file.exists():
        log.info(f"캐시에서 네비게이션 그래프 로드: {cache_file}")
        with open(cache_file, "r") as f:
            # JSON은 튜플 키를 지원하지 않으므로, 문자열로 저장된 키를 다시 튜플로 변환
            graph_str_keys = json.load(f)
            return {
                tuple(map(float, key.strip("()").split(","))): set(
                    tuple(map(float, v.strip("()").split(","))) for v in values
                )
                for key, values in graph_str_keys.items()
            }

    log.info(f"'{scene_name}' 씬의 마스터 네비게이션 그래프를 새로 생성합니다...")

    # 1. 모든 열 수 있는 객체의 원래 상태 저장
    openable_objects = [
        o for o in controller.last_event.metadata["objects"] if o["openable"]
    ]
    original_states = {
        o["objectId"]: {"isOpen": o["isOpen"], "isDirty": o["isDirty"]}
        for o in openable_objects
    }

    # 2. 모든 문과 서랍을 강제로 열기
    for obj in openable_objects:
        if not obj["isOpen"]:
            controller.step(
                action="OpenObject",
                objectId=obj["objectId"],
                openness=1.0,
                forceAction=True,
            )

    # 3. 맵이 최대로 개방된 상태에서 그래프 생성
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
            if (dx + dy + dz) < GRID_SIZE * 1.5:  # 약간의 허용 오차를 줌
                neighbors[pos].add(other)

    # 4. 생성된 그래프를 파일에 저장
    with open(cache_file, "w") as f:
        # JSON 저장을 위해 튜플 키와 값을 문자열로 변환
        graph_str_keys = {str(k): [str(v) for v in vs] for k, vs in neighbors.items()}
        json.dump(graph_str_keys, f, indent=4)
    log.info(f"네비게이션 그래프를 캐시에 저장했습니다: {cache_file}")

    # 5. 모든 객체를 원래 상태로 복원
    for obj_id, state in original_states.items():
        if state["isOpen"]:
            controller.step(
                action="OpenObject",
                objectId=obj_id,
                openness=1.0,
                forceAction=True,
            )
        else:
            controller.step(action="CloseObject", objectId=obj_id, forceAction=True)

    return neighbors


def adjust_if_unreachable(
    nav_graph: Dict[Tuple[float, float, float], Set[Tuple[float, float, float]]],
    pos: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    qpos = quantize_position(pos)
    while qpos not in nav_graph:
        qpos = _adjust_to_reachable(nav_graph, qpos)

    return qpos


def _adjust_to_reachable(nav_graph, pos):
    # unreachable이면 nav_graph 중 가장 가까운 위치로 보정
    pos = quantize_position(pos)
    if pos in nav_graph:
        return pos
    # 없으면 전체 노드 중 최단거리
    all_reachable = list(nav_graph.keys())
    return closest_position(pos, all_reachable)


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
