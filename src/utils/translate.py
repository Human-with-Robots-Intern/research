"""Action translation utilities for ROS communication.

This module resides in the TTP container and translates high-level
primitive actions into the ROS-side action parts payload. By performing
translation client-side, the ROS container no longer needs to access
``object_positions.json`` or mapping files.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


class InstructionTranslator:
    """Translates primitive actions into ROS action parts.

    The translator loads action/object mappings and the latest object positions
    and converts a string instruction (e.g., "GRASP banana") into the list of
    parts consumed by the ROS bridge (e.g., ``[robot_model, action_id, object_id, position]``).
    """

    def __init__(self) -> None:
        """Initialize mappings for action/object translation.

        Raises:
            FileNotFoundError: If required mapping files are missing.
            json.JSONDecodeError: If mapping files contain invalid JSON.
        """
        # Static config lives under assets/ros/static
        self.action_mapping: Dict[str, int] = json.load(
            open("assets/ros/static/action_mapping.json", "r", encoding="utf-8")
        )
        # object_init_positions replaces the previous object_mapping
        self.object_mapping: Dict[str, int] = json.load(
            open("assets/ros/static/object_init_positions.json", "r", encoding="utf-8")
        )

    def translate(self, instruction: str) -> List[Any]:
        """Translate a primitive instruction string to ROS action parts.

        Args:
            instruction: A primitive action string like "NAVIGATE_TO banana" or
                "GRASP banana".

        Returns:
            A list of action parts: ``[robot_model, action_id, object_id, position]``.

        Raises:
            KeyError: If the action or object name is not found in mappings.
            FileNotFoundError: If the positions file is missing.
            json.JSONDecodeError: If the positions file is invalid JSON.
            IndexError: If the instruction does not contain the expected parts.
        """
        # Dynamic state lives under assets/ros/dynamic
        object_positions: Dict[str, Any] = json.load(
            open("assets/ros/dynamic/object_positions.json", "r", encoding="utf-8")
        )

        parts = instruction.split(" ")
        action_name = parts[0]
        object_name = parts[1]

        action_id = self.action_mapping[action_name]
        object_id = self.object_mapping[object_name.lower()]
        object_position = object_positions[object_name.lower()]

        # robot_model is currently fixed to 0 in existing pipeline
        return [0, action_id, object_id, object_position]


