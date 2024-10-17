import pygame
from handlers.arm_handler import ArmHandler
from handlers.camera_handler import CameraHandler
from handlers.interaction_handler import InteractionHandler
from handlers.move_handler import MoveHandler

from sim.utils.constants import *


class Teleoperation:
    def __init__(self, controller, agent_knowledge):
        self.controller = controller
        self.camera_handler = CameraHandler(controller)
        self.move_handler = MoveHandler(controller, self.camera_handler)
        self.arm_handler = ArmHandler(controller)
        self.interaction_handler = InteractionHandler(controller)

        self.initial_position = self.controller.last_event.metadata["agent"]["position"]
        self.initial_rotation = self.controller.last_event.metadata["agent"]["rotation"]
        self.radius_index = 0
        self.agent_knowledge = agent_knowledge

    def process_events(self):
        running = True

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if self.controller.last_event.metadata["lastActionSuccess"]:
                    obj_infos = self.interaction.get_obj_info()
                    self.agent_knowledge.update(obj_infos)
                # Reset and Escape
                if event.key == pygame.K_v:
                    self.camera_handler.toggle_view()
                if event.key == pygame.K_r:
                    self.controller.step(
                        action="Teleport",
                        position=self.initial_position,
                        rotation=self.initial_rotation,
                        horizon=self.controller.last_event.metadata["agent"][
                            "cameraHorizon"
                        ],
                        forceAction=True,
                    )

                    self.camera_handler.update_view()

                # Pick and place
                if event.key == pygame.K_SPACE:
                    if self.controller.last_event.metadata["arm"]["heldObjects"]:
                        self.arm_handler.drop_object()
                    else:
                        self.arm_handler.pickup_object()

                # set grasp radius
                if event.key == pygame.K_SLASH:
                    self.radius_index = (self.radius_index + 1) % len(HAND_RADIUS)
                    self.controller.step(
                        action="SetHandSphereRadius",
                        radius=HAND_RADIUS[self.radius_index],
                    )

        return running

    def handle_keys(self):
        keys = pygame.key.get_pressed()

        run_mode = (
            keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        )  # Shift 키로 달리기 모드

        # 에이전트 이동 처리
        if keys[pygame.K_w]:
            self.move_handler.move_agent("MoveAhead", run_mode)
        if keys[pygame.K_s]:
            self.move_handler.move_agent("MoveBack", run_mode)
        if keys[pygame.K_a]:
            self.move_handler.rotate_agent("RotateLeft")
        if keys[pygame.K_d]:
            self.move_handler.rotate_agent("RotateRight")

        # 카메라 회전
        if keys[pygame.K_q]:
            self.controller.step(action="LookUp", degrees=ROTATE_STEP)
        if keys[pygame.K_e]:
            self.controller.step(action="LookDown", degrees=ROTATE_STEP)

        # Move Arm Base (팔 기반 높이 조절)
        if keys[pygame.K_p]:
            self.arm_handler.move_arm_base(delta_y=ARM_MOVE_STEP)  # 팔 기반을 위로 이동
        if keys[pygame.K_SEMICOLON]:
            self.arm_handler.move_arm_base(
                delta_y=-ARM_MOVE_STEP
            )  # 팔 기반을 아래로 이동

        # Manipulate Arm (팔 이동)
        if keys[pygame.K_RIGHT]:
            self.arm_handler.move_arm(delta_x=ARM_MOVE_STEP)  # 팔을 오른쪽으로 이동
        if keys[pygame.K_LEFT]:
            self.arm_handler.move_arm(delta_x=-ARM_MOVE_STEP)  # 팔을 왼쪽으로 이동
        if keys[pygame.K_UP]:
            self.arm_handler.move_arm(delta_y=ARM_MOVE_STEP)  # 팔을 위로 이동
        if keys[pygame.K_DOWN]:
            self.arm_handler.move_arm(delta_y=-ARM_MOVE_STEP)  # 팔을 아래로 이동
        if keys[pygame.K_COMMA]:
            self.arm_handler.move_arm(delta_z=ARM_MOVE_STEP)  # 팔을 앞으로 이동
        if keys[pygame.K_PERIOD]:
            self.arm_handler.move_arm(delta_z=-ARM_MOVE_STEP)  # 팔을 뒤로 이동

    # Other methods can be added here as needed
    def get_current_frame(self):
        return self.camera_handler.get_current_frame()
