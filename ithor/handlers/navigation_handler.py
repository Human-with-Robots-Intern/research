import heapq
import math
import time

from ithor.utils.constants import SMOOTH_LEVEL
from ithor.utils.math_utils import (
    closest_position,
    load_navigation_graph,
    quantize_position,
)


class NavigationHandler:
    def __init__(self, controller):
        self.controller = controller
        self.neighbors = load_navigation_graph(controller)

    def adjust_camera_to_object(self, object_id):
        """
        Adjusts the camera's pitch (horizon) to focus on the object within preset limits.

        Args:
            object_id (str): The identifier of the target object.
        """
        agent_pos = self.get_agent_position()
        object_pos = self.get_object_position(object_id)

        # Calculate horizontal distance and height difference
        horizontal_distance = math.hypot(
            object_pos[0] - agent_pos[0], object_pos[2] - agent_pos[2]
        )
        height_diff = agent_pos[1] - object_pos[1]

        # Calculate required pitch angle (in degrees)
        angle = (
            math.degrees(math.atan(height_diff / horizontal_distance))
            if horizontal_distance > 0
            else 0
        )

        # Clamp angle between -30 and 60 degrees
        clamped_angle = max(-30, min(60, angle))
        current_pitch = self.controller.last_event.metadata["agent"]["cameraHorizon"]

        diff = clamped_angle - current_pitch
        # Smoothly adjust camera pitch
        for _ in range(SMOOTH_LEVEL):
            current_pitch += diff / SMOOTH_LEVEL
            self.controller.step(action="Teleport", horizon=current_pitch)

    def find_shortest_path(self, start, end):
        """
        Finds the shortest path from start to end using a priority queue (A*-like).

        Args:
            start (tuple): Starting coordinates.
            end (tuple): Destination coordinates.

        Returns:
            list: List of positions representing the path.
        """
        start = quantize_position(start)
        end = quantize_position(end)

        if start == end:
            return [start]

        reachable = set(self.get_reachable_positions())
        if start not in reachable:
            start = quantize_position(self.adjust_to_nearest_reachable(start))
        if end not in reachable:
            end = quantize_position(self.adjust_to_nearest_reachable(end))

        def calculate_direction(p1, p2):
            return p2[0] - p1[0], p2[2] - p1[2]

        pq = []
        heapq.heappush(pq, (0, start, None, [start]))
        visited = {}

        while pq:
            turn_count, current, curr_dir, path = heapq.heappop(pq)
            if current == end:
                return path

            if current in visited and visited[current] <= turn_count:
                continue
            visited[current] = turn_count

            for neighbor in self.neighbors.get(current, []):
                if neighbor in path or neighbor not in reachable:
                    continue

                new_dir = calculate_direction(current, neighbor)
                new_turn_count = (
                    turn_count
                    if curr_dir is None or new_dir == curr_dir
                    else turn_count + 1
                )

                heapq.heappush(
                    pq, (new_turn_count, neighbor, new_dir, path + [neighbor])
                )

        raise Exception(f"No path found between {start} and {end}. Check reachability.")

    def is_reachable(self, target_position):
        """
        Checks if the target position is reachable by the agent.

        Args:
            target_position (tuple): The target coordinates.

        Returns:
            bool: True if reachable, False otherwise.
        """
        reachable = self.get_reachable_positions()
        return quantize_position(target_position) in reachable

    def adjust_to_nearest_reachable(self, target_position):
        """
        Adjusts the target position to the nearest reachable point if it's unreachable.

        Args:
            target_position (tuple): The target coordinates.

        Returns:
            tuple: The nearest reachable position.
        """
        reachable = self.get_reachable_positions()
        return closest_position(target_position, reachable)

    def get_reachable_positions(self):
        """
        Returns all reachable positions for the agent, quantized to the grid.

        Returns:
            list: Reachable positions as tuples.
        """
        positions = self.controller.step("GetReachablePositions").metadata[
            "actionReturn"
        ]
        return [quantize_position((p["x"], p["y"], p["z"])) for p in positions]

    def get_agent_position(self):
        """
        Retrieves the current position (camera) of the agent.

        Returns:
            tuple: (x, y, z) coordinates of the agent.
        """
        event = self.controller.step(action="Pass")
        pos = event.metadata["cameraPosition"]
        return tuple(pos.values())

    def get_object_position(self, object_id):
        """
        Retrieves the position of an object given its ID.

        Args:
            object_id (str): The unique identifier of the object.

        Returns:
            tuple: (x, y, z) coordinates of the object's center, or None if not found.
        """
        event = self.controller.step(action="Pass")
        for obj in event.metadata["objects"]:
            if obj["objectId"] == object_id:
                center = obj["axisAlignedBoundingBox"]["center"]
                return tuple(center.values())
        return None

    def get_agent_rotate(self):
        """
        Retrieves the current rotation angle (y-axis) of the agent.

        Returns:
            float: The agent's rotation angle in degrees.
        """
        event = self.controller.step(action="Pass")
        return event.metadata["agent"]["rotation"]["y"]

    def teleport_to_position(self, position):
        """
        Teleports the agent to a specified position with smooth rotation adjustment.

        Args:
            position (tuple): Target (x, y, z) coordinates.
        """
        current_pos = self.get_agent_position()
        current_rot = round(self.get_agent_rotate(), 1)
        dx = position[0] - current_pos[0]
        dz = position[2] - current_pos[2]

        rotation_angle = self._compute_required_rotation(current_rot, dx, dz)

        if rotation_angle:
            for _ in range(SMOOTH_LEVEL):
                self.controller.step(
                    action="RotateRight", degrees=rotation_angle / SMOOTH_LEVEL
                )
                self.controller.step(action="Pass")
        time.sleep(0.1)
        updated_angle = self.get_agent_rotate()
        self.controller.step(
            action="Teleport",
            position={"x": position[0], "y": position[1] + 0.05, "z": position[2]},
            rotation={"x": 0, "y": updated_angle, "z": 0},
            horizon=30,
            standing=True,
        )
        time.sleep(0.1)

    def _compute_required_rotation(self, current_rot, dx, dz):
        """
        Computes the rotation angle required based on directional differences.

        Args:
            current_rot (float): Current rotation angle of the agent.
            dx (float): Difference in x-coordinate.
            dz (float): Difference in z-coordinate.

        Returns:
            float: The computed rotation angle normalized to [-180, 180].
        """
        rotation_angle = 0
        if dx > 0 and dz == 0:
            if abs(current_rot - 90) > 2:
                rotation_angle = 90 - current_rot
        elif dx < 0 and dz == 0:
            if abs(current_rot - 270) > 2:
                rotation_angle = 270 - current_rot
        elif dx == 0 and dz > 0:
            if max(abs(current_rot), abs(current_rot - 360)) > 2:
                rotation_angle = 360 - current_rot
        elif dx == 0 and dz < 0:
            if abs(current_rot - 180) > 2:
                rotation_angle = 180 - current_rot

        return self._normalize_angle(rotation_angle)

    @staticmethod
    def _normalize_angle(angle):
        """
        Normalizes an angle to the range [-180, 180].

        Args:
            angle (float): Angle in degrees.

        Returns:
            float: Normalized angle.
        """
        while angle < -180:
            angle += 360
        while angle > 180:
            angle -= 360
        return angle

    def agent_rotate_angle(self, agent_pos, object_pos):
        """
        Calculates the angle difference between the agent's current forward direction and the direction to the object.

        Args:
            agent_pos (tuple): (x, y, z) of the agent.
            object_pos (tuple): (x, y, z) of the object.

        Returns:
            tuple: (object_angle, degree) where object_angle is the angle from the agent's forward direction
                   to the object (in degrees, normalized to [-180, 180]) and degree is the adjustment needed.
        """
        agent_angle = self.get_agent_rotate()
        dx = object_pos[0] - agent_pos[0]
        dz = object_pos[2] - agent_pos[2]

        raw_angle = math.degrees(math.atan2(dz, dx))
        # Adjust to a forward-facing frame: 90 degrees offset
        object_angle = (90 - raw_angle) % 360
        if object_angle > 180:
            object_angle -= 360

        degree = object_angle - agent_angle
        degree = self._normalize_angle(degree)
        return object_angle, degree

    def move_in_direction(self, angle, distance):
        """
        Moves the agent in a specified direction by a given distance.
        (For example, move backward when rotating while holding an object.)

        Args:
            angle (float): The angle between the agent and the object.
            distance (float): The distance to move.

        Returns:
            None
        """
        agent_pos = self.get_agent_position()
        agent_rot = self.get_agent_rotate()
        angle_rad = math.radians(angle)

        new_x = agent_pos[0] + distance * math.sin(angle_rad)
        new_z = agent_pos[2] + distance * math.cos(angle_rad)
        new_pos = quantize_position((new_x, agent_pos[1], new_z))

        self.controller.step(
            action="Teleport",
            position={"x": new_pos[0], "y": agent_pos[1], "z": new_pos[2]},
            rotation={"x": 0, "y": agent_rot, "z": 0},
            horizon=30,
            standing=True,
        )
