import enum

# 로봇 상태에 대한 기본 추상클래스
# 모든 로봇이 작업과정에서 공통적으로 가지는 성질에 대하여 정의한 클래스
# 로봇의 상세한 특성은 해당 클래스를 상속받아 작성
class Detector_properties:
    def __init__(self):
        self.enable = False 
        # 기능을 비활성화 해둔 상태로 개체를 초기화
        # 필요에 따라서 기능을 활성화 하는 방식으로 활용

        class Detector_state_enum_class(enum.Enum):
            ready = enum.auto()
            request = enum.auto()
            working = enum.auto()
            complete = enum.auto()
            pause = enum.auto()
            error = enum.auto()
            halt = enum.auto()
        
        # 로봇이 기억해야 할 상태는 테스크의 수행 단계보다 
        # 물건 잡는 여부 
        # 로봇의 자세 등등에 대한 정보가 더 필요한 듯 

        self.detector_state_enum = Detector_state_enum_class
        self.state_detector = self.detector_state_enum.pause.value

    def set_enable_property(self):
        self.enable = True

    def set_disable_property(self):
        self.enable = False
        
    def get_is_enabled(self) -> bool:
        return self.enable
    
    def get_state_enum_instance(self):
        return self.detector_state_enum
    
    def set_state(self, state_arg:int):
        self.state_detector = state_arg

    def get_state(self) -> int:
        return self.state_detector