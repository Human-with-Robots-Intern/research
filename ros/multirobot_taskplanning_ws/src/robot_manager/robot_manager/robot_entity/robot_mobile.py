from robot import Robot

class Robot_mobile_manipulator(Robot):
    def __init__(self):
        super().__init__()

    def set_enable_robot(self) -> None:
        self.mobilebase_properties.set_enable_property()
        # self.manipulator_properties.set_enable_property()

    def set_disable_robot(self) -> None:
        self.mobilebase_properties.set_enable_property()
        # self.manipulator_properties.set_enable_property()

    def get_is_enabled(self) -> bool:
        enable_mobile = self.mobilebase_properties.get_is_enabled()
        # enable_manipulation = self.manipulator_properties.get_is_enabled()
        return enable_mobile

if __name__ == "__main__":
    robot = Robot_mobile_manipulator()
    robot.set_name("test_jackal")# 테스트용 설정 코드
    robot.set_type("mobile")
    robot.set_enable_robot()
    print(robot.get_mobilebase_property_instance().get_is_enabled())
    print(robot.get_manipulator_property_instance().get_is_enabled())
    print(robot.get_worker_property_instance().get_state())
    print(robot.get_mobilebase_property_instance().get_state())
    print(robot.get_manipulator_property_instance().get_state())
