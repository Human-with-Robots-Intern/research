import enum

# 로봇 상태에 대한 기본 추상클래스
# 모든 로봇이 작업과정에서 공통적으로 가지는 성질에 대하여 정의한 클래스
# 로봇의 상세한 특성은 해당 클래스를 상속받아 작성
class Gripper_properties:
    def __init__(self):
        self.enable = False 
        # 기능을 비활성화 해둔 상태로 개체를 초기화
        # 필요에 따라서 기능을 활성화 하는 방식으로 활용

        class Gripper_state_enum_class(enum.Enum):
            ready = enum.auto()
            working = enum.auto()
            open = enum.auto()
            close = enum.auto()
            hold = enum.auto()
            error = enum.auto()
            halt = enum.auto()

        self.gripper_state_enum = Gripper_state_enum_class
        self.state_gripper = self.gripper_state_enum.ready.value

        class Gripper_type_enum_class(enum.Enum):
            panda = enum.auto()
            robotiq = enum.auto()

        self.gripper_type_enum = Gripper_type_enum_class
        self.gripper_type = None

        self.holding_object_id = None

    def set_enable_property(self) -> None:
        self.enable = True

    def set_disable_property(self) -> None:
        self.enable = False
        
    def get_is_enabled(self) -> bool:
        return self.enable
    
    def get_state_enum_instance(self):
        return self.gripper_state_enum
    
    def set_state(self, state_arg:int):
        self.state_gripper = state_arg

    def get_state(self) -> int:
        return self.state_gripper

    def get_gripper_type_enum_instance(self):
        return self.gripper_type_enum

    def set_gripper_type(self, type_arg:int) -> None:
        self.gripper_type = type_arg

    def get_gripper_type(self) -> int:
        return self.gripper_type

    def set_holding_object_id(self, id_arg:int):
        self.holding_object_id = id_arg
    
    def get_holding_object_id(self) -> int:
        return self.holding_object_id
    
    def clear_holding_object_id(self) -> None:
        self.holding_object_id = None
        