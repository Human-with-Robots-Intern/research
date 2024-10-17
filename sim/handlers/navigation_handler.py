from collections import deque

from utils.constants import GRID_SIZE
from utils.math_utils import closest_position, quantize_position


class NavigationHandler:
    def __init__(self, controller):
        self.controller = controller
        self.grid_size = GRID_SIZE  # Ensure grid_size is defined
        self.neighbors = self.init_neighbors()

    def init_neighbors(self):
        neighbors = dict()
        positions = self.controller.step("GetReachablePositions").metadata[
            "actionReturn"
        ]
        positions_tuple = [
            quantize_position((p["x"], p["y"], p["z"])) for p in positions
        ]

        # Build neighbors with quantized positions
        for position in positions_tuple:
            position_neighbors = set()
            for p in positions_tuple:
                if position != p and all(
                    abs(position[i] - p[i]) <= self.grid_size for i in range(3)
                ):
                    position_neighbors.add(p)
            neighbors[position] = position_neighbors

        return neighbors

    def move_to(self, object_id: str):
        """
        Moves the agent to the nearest reachable point near the specified object.
        """
        # Get current agent position
        agent_position = self.get_agent_position()

        # Get object position from the object ID
        object_position = self.get_object_position(object_id)

        # Find the shortest path to the closest reachable position near the object
        path = self.shortest_path(agent_position, object_position)

        # Move agent step by step along the path
        for position in path:
            self.teleport_to_position(position)

    def shortest_path(self, start, end):
        start = quantize_position(start)
        end = quantize_position(end)

        if start == end:
            return [start]

        while not self.is_reachable(end):
            end = quantize_position(self.adjust_to_nearest_reachable(end))

        q = deque()
        q.append([start])
        visited = set()

        while q:
            path = q.popleft()
            pos = path[-1]

            if pos in visited:
                continue

            visited.add(pos)

            for neighbor in self.neighbors.get(pos, []):
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    q.append(path + [neighbor])

        raise Exception(f"No path found between {start} and {end}. Check reachability.")

    def is_reachable(self, target_position):
        """
        Checks if the target position is reachable by the agent.
        """
        reachable_positions = self.get_reachable_positions()
        target_position = quantize_position(target_position)
        return target_position in reachable_positions

    def adjust_to_nearest_reachable(self, target_position):
        """
        Adjusts the target position to the nearest reachable point if it's unreachable.
        """
        reachable_positions = self.get_reachable_positions()
        closest_reachable = closest_position(target_position, reachable_positions)
        return closest_reachable

    def get_reachable_positions(self):
        """Returns all reachable positions for the agent, quantized to the grid."""
        return [
            quantize_position((p["x"], p["y"], p["z"]))
            for p in self.controller.step("GetReachablePositions").metadata[
                "actionReturn"
            ]
        ]

    def get_object_position(self, object_id):
        """
        Retrieves the position of the object with the given ID.
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
        Retrieves the agent's current position.
        """
        agent_position = self.controller.last_event.metadata["agent"]["position"]
        return (agent_position["x"], agent_position["y"], agent_position["z"])

    def teleport_to_position(self, position):
        """
        Teleports the agent to the specified position.
        """
        self.controller.step(
            action="Teleport",
            position={"x": position[0], "y": position[1], "z": position[2]},
        )
