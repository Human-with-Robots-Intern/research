from collections import deque

from ..utils.constants import GRID_SIZE
from ..utils.math_utils import (
    closest_position,
    quantize_position,
    calculate_rotation_angle,
)

import math
import time


class NavigationHandler:
    def __init__(self, controller, camera_handler):
        self.controller = controller
        self.camera_handler = camera_handler
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
            # print(f"teleport {position}")
            self.teleport_to_position(position)
            self.camera_handler.update_view()

        agent_position = self.get_agent_position()
        obj_angle, degree = self.agent_rotate_angle(
            agent_position, object_position
        )  # 회전각도 구하기

        for _ in range(3):  # 그냥 회전하는거 잘 보고싶어서 세 번에 나누어서 회전
            # 일단 회전하고
            self.controller.step(action="RotateRight", degrees=degree)
            success = self.controller.last_event.metadata["lastActionSuccess"]
            # 실패하면 움직여서 다시 한 번 더 도전. 여기는 while문을 써야할까?
            if not success:
                self.move_in_direction(-obj_angle, 0.2)
                self.controller.step(action="RotateRight", degrees=degree)
                self.camera_handler.update_view()
            self.controller.step(action="Pass")
            self.camera_handler.update_view()
            time.sleep(0.2)
        self.adjust_camera_to_object(object_id)
        self.controller.step(action="Pass")
        self.camera_handler.update_view()
        time.sleep(0.2)

    def adjust_camera_to_object(self, object):
        """
        Adjusts the camera's pitch (horizon) to focus on the object, within limits.
        """
        agent_position = self.get_agent_position()
        object_position = self.get_object_position(object)
        # Calculate relative height and distance
        height_diff = object_position[1] - agent_position[1]
        distance = (
            (object_position[0] - agent_position[0]) ** 2
            + (object_position[2] - agent_position[2]) ** 2
        ) ** 0.5

        # Calculate the required pitch angle in degrees
        if distance > 0:  # Avoid division by zero
            angle = math.degrees(math.atan(height_diff / distance))
        else:
            angle = 0  # Object is directly at the agent's position

        # Clamp the angle between 0 (looking straight) and 60 degrees
        clamped_angle = max(0, min(60, angle))
        # Determine the current camera pitch
        current_pitch = self.controller.last_event.metadata["agent"]["cameraHorizon"]

        # Calculate steps needed to reach the clamped angle
        steps = int(
            (clamped_angle - current_pitch) / 15
        )  # Assuming each step adjusts by 30 degrees
        # Adjust the camera pitch in steps
        for _ in range(abs(steps)):
            if steps > 0:  # Need to look up
                self.controller.step(action="LookUp")
                self.controller.step("Pass")
            elif steps < 0:  # Need to look down
                self.controller.step(action="LookDown")
                self.controller.step("Pass")

            # Update view after each step
            self.camera_handler.update_view()
            time.sleep(0.1)

    def shortest_path(self, start, end):

        start = quantize_position(start)
        end = quantize_position(end)
        if start == end:
            return [start]
        while not self.is_reachable(start):
            start = quantize_position(self.adjust_to_nearest_reachable(start))
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
        # return last_valid_path
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

    def get_agent_position(self):
        event = self.controller.step(action="Pass")
        agent_position = event.metadata["agent"]["position"]

        return tuple(agent_position.values())

    def get_object_position(self, object_id):
        event = self.controller.step(action="Pass")
        for obj in event.metadata["objects"]:
            if obj["objectId"] == object_id:
                return tuple(obj["position"].values())
        return None

    def get_agent_rotate(self):
        event = self.controller.step(action="Pass")
        agent_angle = event.metadata["agent"]["rotation"]["y"]

        return agent_angle

    def teleport_to_position(self, position):
        # 현재 위치
        current_position = self.get_agent_position()
        current_angle = self.get_agent_rotate()
        dx = position[0] - current_position[0]
        dz = position[2] - current_position[2]

        angle_radians = math.atan2(dx, dz)
        angle_degrees = math.degrees(angle_radians)
        if angle_degrees < 0:
            angle_degrees += 360

        # 4방향으로 제한
        if 45 <= angle_degrees < 135:
            face = 90
        elif 135 <= angle_degrees < 225:
            face = 180
        elif 225 <= angle_degrees < 315:
            face = 270
        else:
            face = 0
        if abs(face - current_angle) > 180:
            face = current_angle
        self.controller.step(
            action="Teleport",
            position=dict(
                x=position[0],
                y=position[1] + 0.05,
                z=position[2],
            ),
            rotation=dict(x=0, y=face, z=0),
            horizon=30,
            standing=True,
        )
        time.sleep(0.3)

    def agent_rotate_angle(self, agent_position, object_position):
        agent_angle = self.get_agent_rotate()

        dx = object_position[0] - agent_position[0]
        dz = object_position[2] - agent_position[2]

        object_angle = math.degrees(
            math.atan2(dz, dx)
        )  # 각도를 (-180, 180)로 반환, arctan(dz/dx)

        # Calculate the angle difference to align object and agent
        object_angle = (
            90 - object_angle
        ) % 360  # 이 부분에서 180도를 넘어서는 값을 0-360 범위로 맞춤
        if object_angle > 180:
            object_angle -= 360  # -180 ~ 180 범위로 만들기

        degree = object_angle - agent_angle
        if degree > 180:
            degree -= 360
        elif degree < -180:
            degree += 360

        return object_angle, degree / 3

    def move_in_direction(self, angle: float, distance: float):

        # Get the current agent position
        agent_position = self.get_agent_position()
        agent_rotation = self.get_agent_rotate()

        # Convert angle to radians
        angle_radians = math.radians(angle)

        # Calculate new position based on angle and distance
        new_x = agent_position[0] + distance * math.sin(angle_radians)
        new_z = agent_position[2] + distance * math.cos(angle_radians)

        quantized_position = quantize_position((new_x, agent_position[1], new_z))
        # Teleport the agent to the new position
        self.controller.step(
            action="Teleport",
            position=dict(
                x=quantized_position[0],
                y=agent_position[1],
                z=quantized_position[2],
            ),
            rotation=dict(x=0, y=agent_rotation, z=0),
            horizon=30,
            standing=True,
        )

        self.controller.step(action="Pass")
        self.camera_handler.update_view()
