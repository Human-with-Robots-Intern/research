import enum

# 로봇 상태에 대한 기본 추상클래스
# 모든 로봇이 작업과정에서 공통적으로 가지는 성질에 대하여 정의한 클래스
# 로봇의 상세한 특성은 해당 클래스를 상속받아 작성
class Mobilebase_properties:
    def __init__(self):
        self.enable = False 
        # 기능을 비활성화 해둔 상태로 개체를 초기화
        # 필요에 따라서 기능을 활성화 하는 방식으로 활용

        class Mobilebase_state_enum_class(enum.Enum):
            not_set = enum.auto()
            safe_zone = enum.auto() # 안전 지역에 있을 때
            danger_zone = enum.auto() # 위험 지역에 있을 때
            moving = enum.auto() # 이동과 함께 상태가 변화하는 중간 상태
            error = enum.auto() # 상태 전이 과정에서 실패한 경우

        self.mobilebase_state_enum = Mobilebase_state_enum_class
        self.state_mobilebase = self.mobilebase_state_enum.not_set.value

    def set_enable_property(self):
        self.enable = True

    def set_disable_property(self):
        self.enable = False
        
    def get_is_enabled(self):
        return self.enable
    
    def get_state_enum_instance(self):
        return self.mobilebase_state_enum
    
    def set_state(self, state_arg:int):
        self.state_mobilebase = state_arg

    def get_state(self) -> int:
        return self.state_mobilebase
    
