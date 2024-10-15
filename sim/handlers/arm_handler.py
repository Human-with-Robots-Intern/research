from sim.utils.utils import *


class ArmHandler:
    def __init__(self, controller):
        self.controller = controller
        self.arm_position = {"x": 0, "y": 0, "z": 0}  # 초기값 설정
        self.update_arm_position()  # 초기 팔 위치 업데이트
        self.held_object_id = None

    def update_arm_position(self):
        """
        메타데이터에서 현재 팔의 위치를 업데이트합니다.
        """
        try:
            arm_metadata = self.controller.last_event.metadata["arm"]
            # 손목의 위치를 가져옵니다.
            wrist_joint = arm_metadata["joints"][-1]  # 마지막 조인트가 손목
            self.arm_position = wrist_joint["rootRelativePosition"]
        except Exception as e:
            print(f"팔 위치 업데이트 중 에러 발생: {str(e)}")

    def move_arm(
        self,
        delta_x=0,
        delta_y=0,
        delta_z=0,
        coordinate_space="wrist",
        restrict_movement=False,
        speed=1,
        return_to_start=True,
        fixed_delta_time=0.02,
    ):
        """
        팔을 현재 위치에서 상대적으로 이동시키는 메소드.

        :param delta_x: 이동할 x 변화량
        :param delta_y: 이동할 y 변화량
        :param delta_z: 이동할 z 변화량
        :param coordinate_space: 좌표계를 지정 ("wrist", "armBase", "world")
        :param restrict_movement: 팔이 제한된 범위 내에서만 이동하도록 설정
        :param speed: 팔의 움직임 속도 (미터/초)
        :param return_to_start: 충돌 시 시작 위치로 복귀할지 여부
        :param fixed_delta_time: 시뮬레이션에서 물리 단계 시간 간격
        """
        try:
            # 현재 팔 위치에서 변화량을 더하여 새로운 목표 위치 계산
            target_position = {"x": delta_x, "y": delta_y, "z": delta_z}

            event = self.controller.step(
                action="MoveArm",
                position=target_position,
                coordinateSpace=coordinate_space,
                restrictMovement=restrict_movement,
                speed=speed,
                returnToStart=return_to_start,
                fixedDeltaTime=fixed_delta_time,
            )

            if event.metadata["lastActionSuccess"]:
                self.update_arm_position()  # 팔 위치 업데이트
                print(
                    f"팔이 {coordinate_space} 좌표계에서 ({delta_x}, {delta_y}, {delta_z})만큼 이동했습니다."
                )
            else:
                print("팔을 지정된 위치로 이동할 수 없습니다.")

        except Exception as e:
            print(f"MoveArm 액션 중 에러 발생: {str(e)}")

    def move_arm_base(
        self, delta_y, speed=1, return_to_start=True, fixed_delta_time=0.02
    ):
        """
        팔의 기반 높이를 상대적으로 조정하는 메소드.

        :param delta_y: 이동할 y 변화량 (0과 1 사이의 값)
        :param speed: 팔의 기반 이동 속도 (미터/초)
        :param return_to_start: 충돌 시 시작 위치로 복귀할지 여부
        :param fixed_delta_time: 시뮬레이션에서 물리 단계 시간 간격
        """
        try:
            # 현재 팔 기반의 y 위치 가져오기
            arm_base_current_y = self.controller.last_event.metadata["arm"]["joints"][
                0
            ]["rootRelativePosition"]["y"]

            # 새로운 목표 y 위치 계산
            target_y = arm_base_current_y + delta_y
            # y 값은 0과 1 사이로 클램핑
            target_y = max(0.0, min(1.0, target_y))

            event = self.controller.step(
                action="MoveArmBase",
                y=target_y,
                speed=speed,
                returnToStart=return_to_start,
                fixedDeltaTime=fixed_delta_time,
            )

            if event.metadata["lastActionSuccess"]:
                print(f"팔의 기반이 높이 {target_y}로 이동했습니다.")
            else:
                print("팔의 기반을 지정된 높이로 이동할 수 없습니다.")

        except Exception as e:
            print(f"MoveArmBase 액션 중 에러 발생: {str(e)}")

    def pickup_object(self):
        """
        팔의 현재 위치에서 객체를 집는 메소드.
        """
        try:
            # 팔의 현재 위치에서 집을 수 있는 객체 목록 가져오기
            pickupable_objects = self.controller.last_event.metadata["arm"].get(
                "pickupableObjects", []
            )
            if not pickupable_objects:
                print("집을 수 있는 객체가 주변에 없습니다.")
                return

            # 첫 번째 객체 선택
            object_id = pickupable_objects[0]
            print("Picking up " + object_id)
            event = self.controller.step(action="PickupObject", objectId=object_id)

            if event.metadata["lastActionSuccess"]:
                self.held_object_id = event.metadata["arm"]["heldObjects"][0]
                print(f"객체를 집었습니다: {self.held_object_id}")
            else:
                print("객체를 집을 수 없습니다.")
        except Exception as e:
            print(f"PickupObject 액션 중 에러 발생: {str(e)}")

    def drop_object(self):
        """
        현재 들고 있는 객체를 놓는 메소드.
        """
        try:
            event = self.controller.step(action="ReleaseObject")
            if event.metadata["lastActionSuccess"]:
                print(f"객체를 놓았습니다: {self.held_object_id}")
                self.held_object_id = None
            else:
                print("객체를 놓을 수 없습니다.")
        except Exception as e:
            print(f"DropHandObject 액션 중 에러 발생: {str(e)}")
