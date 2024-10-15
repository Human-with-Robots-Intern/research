# input_handler.py

import pygame

from sim.utils.constants import *


class InputHandler:
    def __init__(self, controller, teleop):
        self.controller = controller
        self.teleop = teleop

    def process_events(self):
        running = True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_v:
                    self.teleop.camera_handler.toggle_view()
                if event.key == pygame.K_r:
                    self.teleop.teleport_to_initial_position()

        return running

    def handle_keys(self):
        keys = pygame.key.get_pressed()
        metadata = self.controller.last_event.metadata["agent"]

        run_mode = (
            keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        )  # Shift 키로 달리기 모드

        # 에이전트 이동 처리
        if keys[pygame.K_w]:
            self.teleop.move_handler.move_agent("MoveAhead", run_mode)
        if keys[pygame.K_s]:
            self.teleop.move_handler.move_agent("MoveBack", run_mode)
        if keys[pygame.K_a]:
            self.teleop.move_handler.rotate_agent("RotateLeft")
        if keys[pygame.K_d]:
            self.teleop.move_handler.rotate_agent("RotateRight")

        # 카메라 회전
        if keys[pygame.K_q]:
            self.controller.step(action="LookUp", degrees=ROTATE_STEP)
        if keys[pygame.K_e]:
            self.controller.step(action="LookDown", degrees=ROTATE_STEP)

        # Move Arm Base (팔 기반 높이 조절)
        if keys[pygame.K_p]:
            self.teleop.arm_handler.move_arm_base(delta_y=0.1)  # 팔 기반을 위로 이동
        if keys[pygame.K_SEMICOLON]:
            self.teleop.arm_handler.move_arm_base(delta_y=-0.1)  # 팔 기반을 아래로 이동

        # Manipulate Arm (팔 이동)
        if keys[pygame.K_RIGHT]:
            self.teleop.arm_handler.move_arm(delta_x=0.1)  # 팔을 오른쪽으로 이동
        if keys[pygame.K_LEFT]:
            self.teleop.arm_handler.move_arm(delta_x=-0.1)  # 팔을 왼쪽으로 이동
        if keys[pygame.K_UP]:
            self.teleop.arm_handler.move_arm(delta_y=0.1)  # 팔을 위로 이동
        if keys[pygame.K_DOWN]:
            self.teleop.arm_handler.move_arm(delta_y=-0.1)  # 팔을 아래로 이동
        if keys[pygame.K_PERIOD]:
            self.teleop.arm_handler.move_arm(delta_z=0.1)  # 팔을 앞으로 이동
        if keys[pygame.K_COMMA]:
            self.teleop.arm_handler.move_arm(delta_z=-0.1)  # 팔을 뒤로 이동

        # Pick and place
        if keys[pygame.K_SPACE]:
            if self.teleop.arm_handler.held_object_id:
                self.teleop.arm_handler.drop_object()
            else:
                self.teleop.arm_handler.pickup_object()
