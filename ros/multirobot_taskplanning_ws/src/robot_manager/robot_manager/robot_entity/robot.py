from worker_properties import Worker_properties
from mobilebase_properties import Mobilebase_properties
from manipulator_properties import Manipulator_properties

class Robot:
    def __init__(self) -> None:
        self.name = None
        self.type = None

        self.worker_properties = Worker_properties()
        self.mobilebase_properties = Mobilebase_properties()
        self.manipulator_properties = Manipulator_properties()

    def set_name(self, name_arg:str) -> None:
        self.name = name_arg

    def get_name(self, name_arg:str) -> str:
        return self.name

    def set_type(self, type_arg:str) -> None:
        self.type = type_arg

    def get_type(self) -> str:
        return self.type

    def set_enable_robot(self) -> None:
        raise NotImplementedError("상속을 통해 로봇 타입에 따라 활성화할 속성을 정의해야 합니다.")
        
    def set_disable_robot(self) -> None:
        raise NotImplementedError("상속을 통해 로봇 타입에 따라 비활성화할 속성을 정의해야 합니다.")
    
    def get_is_enabled(self) -> bool:
        raise NotImplementedError("상속을 통해 로봇 타입에 따라 가지고 있는 속성을 정의해야 합니다.")

    def get_worker_property_instance(self) -> Worker_properties:
        return self.worker_properties

    def get_mobilebase_property_instance(self) -> Mobilebase_properties:
        # obj_rtn = None
        # if self.mobilebase_properties.get_is_enabled() == True:
        #     obj_rtn = self.mobilebase_properties
        # return obj_rtn # 속성이 활성화 되어있지 않은 경우 None을 반환 
        return self.mobilebase_properties
    
    def get_manipulator_property_instance(self) -> Manipulator_properties:
        # obj_rtn = None
        # if self.manipulator_properties.get_is_enabled() == True:
        #     obj_rtn = self.manipulator_properties
        # return obj_rtn # 속성이 활성화 되어있지 않은 경우 None을 반환 
        return self.manipulator_properties