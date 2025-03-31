### simulation/controller_factory.py
from ai2thor.controller import Controller

from ithor.utils.constants import GRID_SIZE, SCREEN_HEIGHT, SCREEN_WIDTH


def create_default_controller(scene: str = "FloorPlan1_physics") -> Controller:
    """
    기본 설정으로 AI2-THOR Controller 객체 생성

    Args:
        scene (str): 로드할 씬 이름

    Returns:
        Controller: 초기화된 AI2-THOR 컨트롤러
    """
    return Controller(
        agentMode="default",
        massThreshold=0.04,
        scene=scene,
        gridSize=GRID_SIZE,
        movementGaussianSigma=0.005,
        renderDepthImage=False,
        renderInstanceSegmentation=False,
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
        renderThirdPartyCameras=False,
        fieldOfView=60,
    )
