import enum

# 로봇 상태에 대한 기본 추상클래스
# 모든 로봇이 작업과정에서 공통적으로 가지는 성질에 대하여 정의한 클래스
# 로봇의 상세한 특성은 해당 클래스를 상속받아 작성
class Worker_properties:
    def __init__(self):
        class Job_state_enum_class(enum.Enum):# 작업 관리에 관한 변수
            ready = enum.auto()
            working = enum.auto()
            complete = enum.auto()
            pause = enum.auto()
            error = enum.auto()
        self.job_state_enum = Job_state_enum_class
        self.state_job = self.job_state_enum.pause.value

    def get_state_enum_instance(self) -> enum.Enum:
        return self.state_job
    
    def set_state(self, state_arg:int):
        self.state_job = state_arg

    def get_state(self) -> int:
        return self.state_job
