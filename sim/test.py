# main.py

import numpy as np
import pygame
from ai2thor.controller import Controller
from handlers.input_handler import InputHandler
from teleoperation import Teleoperation


def main():
    # 화면 크기 설정
    width, height = 800, 600

    # Pygame 초기화
    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("AI2-THOR Control")

    # AI2-THOR 컨트롤러 초기화
    controller = Controller(
        agentMode="arm",  # "default", "locobot", "drone", or "arm",
        massThreshold=0.04,  # 물리 엔진에서 물체를 움직이는 최소 질량
        scene="FloorPlan1_physics",
        gridSize=0.125,  # Move Actions의 Mean
        movementGaussianSigma=0.005,  # Move Actions의 Sigma
        renderDepthImage=False,  # Depth Image 렌더링 여부 (오랜 시간 소요)
        renderInstanceSegmentation=False,  # Instance Segmentation 렌더링 여부 (오랜 시간 소요)
        width=width,
        height=height,
        renderThirdPartyCameras=True,
        fieldOfView=60,
    )

    # Teleoperation 및 InputHandler 객체 생성
    teleop = Teleoperation(controller)
    input_handler = InputHandler(controller, teleop)

    # 초기 위치 저장
    teleop.save_initial_position()

    running = True
    while running:
        # 이벤트 처리
        running = input_handler.process_events()

        # 키 입력 처리
        input_handler.handle_keys()

        # 이미지 렌더링
        image = teleop.get_current_frame()

        # 이미지 변환 및 화면에 그리기
        image = np.flip(np.rot90(image), axis=0)
        surface = pygame.surfarray.make_surface(image)
        screen.blit(surface, (0, 0))

        # pygame에 display 업데이트
        pygame.display.flip()

    # 프로그램 종료
    pygame.quit()
    controller.stop()


if __name__ == "__main__":
    main()
