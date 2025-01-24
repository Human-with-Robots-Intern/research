import json

from ai2thor.controller import Controller

from ithor.handlers.camera_handler import CameraHandler
from ithor.handlers.navigation_handler import NavigationHandler
from ithor.utils.constants import *
from utils.constants import KNOWLEDGE_PATH


def get_environment(controller):  # 최종 환경 추출
    scene_name = controller.step("Pass").metadata["sceneName"]
    objs = controller.step("Pass").metadata["objects"]
    openable = []
    openableID = []
    toggleable = []
    toggleableID = []
    pickupable = []
    pickupableID = []
    sliceable = []
    sliceableID = []
    receptacle = []
    receptacleID = []

    for obj in objs:
        if obj["openable"]:
            openable.append(obj["objectType"])
        if obj["toggleable"]:
            toggleable.append(obj["objectType"])
        if obj["pickupable"]:
            pickupable.append(obj["objectType"])
        if obj["sliceable"]:
            sliceable.append(obj["objectType"])
        if obj["receptacle"]:
            receptacle.append(obj["objectType"])

    openable = list(set(openable))
    toggleable = list(set(toggleable))
    pickupable = list(set(pickupable))
    sliceable = list(set(sliceable))
    receptacle = list(set(receptacle))

    objs = []

    for obj in openable:
        openable_ids = controller.step(
            action="ObjectTypeToObjectIds", objectType=obj
        ).metadata["actionReturn"]
        openableID.extend(openable_ids)
        objs.extend(openable_ids)
    for obj in toggleable:
        toggleable_ids = controller.step(
            action="ObjectTypeToObjectIds", objectType=obj
        ).metadata["actionReturn"]
        toggleableID.extend(toggleable_ids)
        objs.extend(toggleable_ids)
    for obj in pickupable:
        pickupable_ids = controller.step(
            action="ObjectTypeToObjectIds", objectType=obj
        ).metadata["actionReturn"]
        pickupableID.extend(pickupable_ids)
        objs.extend(pickupable_ids)
    for obj in sliceable:
        sliceable_ids = controller.step(
            action="ObjectTypeToObjectIds", objectType=obj
        ).metadata["actionReturn"]
        sliceableID.extend(sliceable_ids)
        objs.extend(sliceable_ids)
    for obj in receptacle:
        receptacle_ids = controller.step(
            action="ObjectTypeToObjectIds", objectType=obj
        ).metadata["actionReturn"]
        receptacleID.extend(receptacle_ids)
        objs.extend(receptacle_ids)
    # sliceable 추가하기
    env = {
        "OPEN": openableID,
        "CLOSE": openableID,
        "TOGGLE_ON": toggleableID,
        "TOGGLE_OFF": toggleableID,
        "GRASP": pickupableID,
        "SLICE": sliceableID,
        "RECEPTACLE": receptacleID,
    }

    objs = list(set(objs))
    with open(KNOWLEDGE_PATH / f"{scene_name}_environment.json", "w") as f:
        json.dump(env, f)
    return env, objs  # prompt 에 쓸 땐 str(env)로 바꿔줘야함


def get_move_time(controller, objs):
    ## 이건 다시 생각해보기
    move_time = {}
    camera_handler = CameraHandler(controller)
    Navi = NavigationHandler(controller, camera_handler)

    move_time["agent"] = {}
    agent_pos = Navi.get_agent_position()
    for to_obj in objs:
        to_obj_pos = Navi.get_object_position(to_obj)
        path = Navi.shortest_path(agent_pos, to_obj_pos)
        time = round(len(path) * 0.1, 2)
        move_time["agent"][to_obj] = time

    for obj1 in objs:
        move_time[obj1] = {}
        for obj2 in objs:
            print(f"{obj1} to {obj2}")
            obj1_pos = Navi.get_object_position(obj1)
            obj2_pos = Navi.get_object_position(obj2)
            path = Navi.shortest_path(obj1_pos, obj2_pos)
            time = round(len(path) * 0.1, 2)
            print(f"{time=}")
            move_time[obj1][obj2] = time

    scene_name = controller.last_event.metadata["sceneName"]

    with open(KNOWLEDGE_PATH / f"{scene_name}_navigation_time.json", "w") as f:
        json.dump(move_time, f)


if __name__ == "__main__":
    controller = Controller(
        agentMode="default",  # "default", "locobot", "drone", or "arm",
        massThreshold=0.04,  # 물리 엔진에서 물체를 움직이는 최소 질량
        scene="FloorPlan2_physics",  # Scene 이름
        gridSize=GRID_SIZE,  # Move Actions의 Mean
        movementGaussianSigma=0.005,  # Move Actions의 Sigma
        renderDepthImage=False,  # Depth Image 렌더링 여부 (오랜 시간 소요)
        renderInstanceSegmentation=False,  # Instance Segmentation 렌더링 여부 (오랜 시간 소요)
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
        renderThirdPartyCameras=False,
        fieldOfView=60,
    )
    env, objs = get_environment(controller)
    get_move_time(controller, objs)
