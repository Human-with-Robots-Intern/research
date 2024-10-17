from collections import deque

from utils.constants import GRID_SIZE
from utils.math_utils import closest_position


class NavigationHandler:
    def __init__(self, controller):
        self.controller = controller
        self.neighbors = self.init_neighbors()

    def init_neighbors(self):
        """
        Initialize the neighbors dictionary for the grid.
        Neighbors are the positions reachable from a given position within one step.
        """
        neighbors = dict()
        # agent가 teleport할 수 있는 모든 position을 가져옴
        positions = self.controller.step("GetReachablePositions").metadata[
            "actionReturn"
        ]
        # position을 tuple 집합으로 변환
        positions_tuple = [(p["x"], p["y"], p["z"]) for p in positions]

        # Populate neighbors for each position
        for position in positions_tuple:
            position_neighbors = set()
            for p in positions_tuple:
                if position != p and (
                    abs(position[0] - p[0]) <= 2 * GRID_SIZE
                    and abs(position[2] - p[2]) <= 2 * GRID_SIZE
                ):
                    position_neighbors.add(p)
            neighbors[position] = position_neighbors

        return neighbors

    def is_reachable(self, target_position):
        """
        Checks if the target position is reachable by the agent.
        The target position should be in the form of (x, y, z).
        Returns True if reachable, False otherwise.
        """
        reachable_positions = self.get_reachable_positions()
        closest_target = self.closest_grid_point(target_position)
        return closest_target in reachable_positions

    def adjust_to_nearest_reachable(self, target_position):
        """
        Adjusts the target position to the nearest reachable point if the target is unreachable.
        Returns the nearest reachable position.
        """
        reachable_positions = self.get_reachable_positions()
        closest_reachable = closest_position(target_position, reachable_positions)
        print(
            f"Adjusted target position from {target_position} to nearest reachable {closest_reachable}"
        )
        return closest_reachable

    def shortest_path(self, start, end):
        """
        Finds the shortest path from start to end using BFS.
        Adjusts the target to the nearest reachable point if the original end is unreachable.
        """
        # Ignore the y-coordinate when calculating the path
        start = (start[0], start[2])  # Use only (x, z) for pathfinding
        end = (end[0], end[2])  # Use only (x, z) for pathfinding

        if start == end:
            return [(start[0], 0, start[1])]  # Return (x, y, z)

        # Check if the target end position is reachable
        if not self.is_reachable((end[0], 0, end[1])):
            # Adjust to the nearest reachable position if the target is unreachable
            end_reachable = self.adjust_to_nearest_reachable((end[0], 0, end[1]))
            end = (end_reachable[0], end_reachable[2])  # Only (x, z)

        q = deque()
        q.append([start])
        visited = set()

        while q:
            path = q.popleft()
            pos = path[-1]

            if pos in visited:
                continue

            visited.add(pos)

            for neighbor in self.neighbors.get((pos[0], 0, pos[1]), []):
                neighbor_2d = (neighbor[0], neighbor[2])
                if neighbor_2d == end:
                    return [(p[0], 0, p[1]) for p in path + [neighbor_2d]]
                if neighbor_2d not in visited:
                    q.append(path + [neighbor_2d])

        raise Exception(f"No path found between {start} and {end}. Check reachability.")

    def get_reachable_positions(self):
        """Helper function to get all reachable positions for the agent."""
        return [
            (p["x"], p["y"], p["z"])
            for p in self.controller.step("GetReachablePositions").metadata[
                "actionReturn"
            ]
        ]

    def closest_grid_point(self, pos):
        """Helper function to find the closest grid point to the given position."""
        return tuple(
            round(coord, 1) for coord in pos
        )  # Assuming grid points rounded to 1 decimal place

    def move_to(self, object_id: str):
        """
        Interface function that moves the agent to the nearest reachable point near the object.
        Handles unreachable positions by adjusting to the closest reachable position.
        """
        # Get reachable positions
        reachable_positions = self.get_reachable_positions()

        # Get object position from the object ID
        object_position = self.get_object_position(object_id)

        # Get current agent position
        agent_position = self.get_agent_position()

        # Find the shortest path to the closest reachable position near the object
        path = self.shortest_path(agent_position, object_position)

        # Move agent step by step along the path
        for position in path:
            self.teleport_to_position(position)

    def get_object_position(self, object_id):
        """
        Helper function to get the position of the object with the given ID.
        Raises an error if the object is not found.
        """
        for obj in self.controller.last_event.metadata["objects"]:
            if obj["objectId"] == object_id:
                return (
                    obj["position"]["x"],
                    obj["position"]["y"],
                    obj["position"]["z"],
                )
        raise ValueError(f"Object with ID {object_id} not found.")

    def get_agent_position(self):
        """
        Helper function to get the agent's current position.
        """
        agent_position = self.controller.last_event.metadata["agent"]["position"]
        return (agent_position["x"], agent_position["y"], agent_position["z"])

    def teleport_to_position(self, position):
        """
        Helper function to teleport the agent to the given position.
        """
        self.controller.step(
            action="Teleport",
            position={"x": position[0], "y": position[1], "z": position[2]},
        )
