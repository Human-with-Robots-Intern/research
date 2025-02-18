import json

from ai2thor.controller import Controller

from ithor.utils.constants import *
from utils.constants import KNOWLEDGE_PATH

controller = Controller(
    agentMode="default",  # "default", "locobot", "drone", or "arm",
    massThreshold=0.04,  # 물리 엔진에서 물체를 움직이는 최소 질량
    scene="FloorPlan1_physics",  # Scene 이름
    gridSize=GRID_SIZE,  # Move Actions의 Mean
    movementGaussianSigma=0.005,  # Move Actions의 Sigma
    renderDepthImage=False,  # Depth Image 렌더링 여부 (오랜 시간 소요)
    renderInstanceSegmentation=False,  # Instance Segmentation 렌더링 여부 (오랜 시간 소요)
    width=SCREEN_WIDTH,
    height=SCREEN_HEIGHT,
    renderThirdPartyCameras=False,
    fieldOfView=60,
)

objects = controller.step("Pass").metadata["objects"]
obj_position = {}
obj_position["agent"] = (
    controller.step("Pass").metadata["agent"]["position"]["x"],
    controller.step("Pass").metadata["agent"]["position"]["y"],
    controller.step("Pass").metadata["agent"]["position"]["z"],
)
for object in objects:
    position = (
        object["position"]["x"],
        object["position"]["y"],
        object["position"]["z"],
    )
    obj_position[object["objectId"]] = position


scene_name = controller.last_event.metadata["sceneName"]

with open(KNOWLEDGE_PATH / f"{scene_name}_object_init_positions.json", "a") as f:
    json.dump(obj_position, f, indent=4)
    f.write("\n")
