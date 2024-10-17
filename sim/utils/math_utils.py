# math_utils.py

import math

from sim.utils.constants import GRID_SIZE


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
    agent_x = agent_position["x"]
    agent_z = agent_position["z"]
    obj_x = object_position["x"]
    obj_z = object_position["z"]

    a = euclidean_distance([agent_x, agent_z], [obj_x, obj_z])
    b = euclidean_distance([agent_x, agent_z], [agent_x - 2, agent_z])
    c = euclidean_distance([obj_x, obj_z], [agent_x - 2, agent_z])

    gamma = math.degrees(math.acos((a**2 + b**2 - c**2) / (2 * a * b)))
    return gamma
