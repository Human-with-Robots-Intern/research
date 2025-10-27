from robot_manager_state_transition.robot_entity.robot import Robot

class Robot_manipulator(Robot):
    def __init__(self):
        super().__init__()

    def set_enable_robot(self) -> None:
        # self.mobilebase_properties.set_enable_property()
        self.manipulator_properties.set_enable_property()
        self.gripper_properties.set_enable_property()
        self.detector_properties.set_enable_property()

    def set_disable_robot(self) -> None:
        # self.mobilebase_properties.set_disable_property()
        self.manipulator_properties.set_disable_property()
        self.gripper_properties.set_disable_property()
        self.detector_properties.set_disable_property()

    def get_is_enabled(self) -> bool:
        # enable_mobile = self.mobilebase_properties.get_is_enabled()
        enable_manipulator = self.manipulator_properties.get_is_enabled()
        enable_gripper = self.gripper_properties.get_is_enabled()
        enable_detector = self.detector_properties.get_is_enabled()
        return enable_manipulator and enable_gripper and enable_detector

if __name__ == "__main__":
    robot = Robot_manipulator()
    robot.set_name("test_ur")# 테스트용 설정 코드
    robot.set_type("manipulator")
    robot.set_enable_robot()
    print(robot.get_mobilebase_property_instance().get_is_enabled())
    print(robot.get_manipulator_property_instance().get_is_enabled())
    print(robot.get_gripper_property_instance().get_is_enabled())
    print(robot.get_detector_property_instance().get_is_enabled())

    print(robot.get_worker_property_instance().get_state())
    print(robot.get_mobilebase_property_instance().get_state())
    print(robot.get_manipulator_property_instance().get_is_enabled())
    print(robot.get_gripper_property_instance().get_state())
    print(robot.get_detector_property_instance().get_state())