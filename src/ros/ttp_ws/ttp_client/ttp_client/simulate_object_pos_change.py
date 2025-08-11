import json
from typing import Dict, Optional, Tuple, TypeAlias
from src.utils.common import create_module_logger
Position: TypeAlias = Tuple[float, float, float]


log = create_module_logger(module_name=__name__, module_log=True)

class SimulateObjectPosChange:
    def __init__(self):
        self.object_positions = json.load(open("src/ros/ttp_ws/data/object_positions.json"))
        self.held_object = None
        self.agent_location = [0,0,0]

    def _simulate_grasp(
        self,
        target_obj_id: Optional[str],
    ) -> Optional[str]:
        self.held_object = target_obj_id

    def _simulate_place(
        self,
        receptacle_id: Optional[str],
    ) -> None:
        """PLACE_INSIDE 또는 PLACE_ON_TOP 액션을 시뮬레이션합니다."""

        if not self.held_object:
            log.warning(f"Agent not holding anything. Cannot place. Action FAILED.")
            success = False
        elif not receptacle_id or receptacle_id.lower() not in self.object_positions:
            raise ValueError(
                f"Place target receptacle '{receptacle_id}' not found in scene positions."
            )
        else:   
   
            log.debug(f"  Placing '{self.held_object}' on/in '{receptacle_id}'.")
            # 객체 상태 업데이트 (시뮬레이션 모델에 따라 달라짐)
            # 여기서는 단순히 손을 비우는 것으로 처리
            if self.held_object in self.object_positions:
                self.object_positions[self.held_object] = self.object_positions[
                    receptacle_id.lower()
                ]
            # Update object_positions.json with new positions
            with open("src/ros/ttp_ws/data/object_positions.json", "w") as f:
                json.dump(self.object_positions, f, indent=4)
            self.held_object = None
    def _get_object_pos(
        self,
        object_name: Optional[str],
    ) -> Optional[Position]:
        return self.object_positions[object_name]
