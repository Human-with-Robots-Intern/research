# ros 기본 모듈
import rclpy
import rclpy.node

# ros 메시지 타입
from std_msgs.msg import Empty
from geometry_msgs.msg import Pose
from object_detect_interface.msg import ObjectData
from object_detect_interface.srv import DetectObjects

# 파이썬 기본 모듈
import math
import enum

# 파이썬 사용자 정의 모듈
from robot_manager_state_transition.process.process import Process # 서브 프로세스 추상 클래스
from robot_manager_state_transition.robot_entity.robot import Robot

class ObjectDetector(Process):
    def __init__(self, node_arg:rclpy.node.Node, robot_arg:Robot):
        super().__init__(node_arg, robot_arg)
        self.node = node_arg
        self.robot = robot_arg

        # <ros 기능 요소 선언>
        # do_plan service 선언
        self.cli_detect_objects = self.node.create_client(DetectObjects, 'detect_objects')

        # <ros2 콜백 관리용 요소 정의>

        # 서비스 request 퓨쳐
        self.future_detect_objects_request = None

        # 서비스 result 퓨쳐
        self.future_detect_objects_response = None

        # 서비스 결과 변수
        self.result_detect_objects = None

        # 프로세스 상태 정의 (각 개별 프로세스마다 다르게 정의됨)
        class Process_state_enum(enum.Enum):
            init = enum.auto()
            ready = enum.auto() # 명령이 아직 등록되지 않았거나, 명령이 종료되어 대기하는 상태
            request = enum.auto()
            wait_ack = enum.auto()#wait_acknowledgments
            working = enum.auto()
            complete = enum.auto()
            reset = enum.auto()
            error = enum.auto() # 오류를 처리중인 상태
            halt = enum.auto() # 오류가 발생하여 더 이상 진행할 수 없는 상태
        
        # 프로세스 상태값 초기화
        self.process_state_enum:Process_state_enum = Process_state_enum
        self.process_state:int = self.process_state_enum.error.value

        # self.request = None # 서비스가 request를 사용하지 않아, 변수를 사용하지 않을 예정

        # ros2 서비스 초기화
        while not self.cli_detect_objects.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info('detector service not available, waiting again...')

        #서비스 초기화가 완료되면 ready 상태로 전이
        self.process_state = self.process_state_enum.ready.value

    # sub process 구성요소 정의
    # 추상 클랫 메서드 오버라이딩
    def do_assign_request(self, request_arg:Empty):
        # 기존 작업에 관련된 값을 초기화
        self.flag_job_completed = False
        self.flag_job_set = False
        self.success = False
        self.result = None
        
        # 새로운 작업을 적용할 수 있는 상태인지 확인
        detector_properties = self.robot.get_detector_property_instance()
        if self.process_state == self.process_state_enum.ready.value:
            if detector_properties.get_state() == detector_properties.detector_state_enum.ready.value: 
                self.process_state = self.process_state_enum.request.value
                self.flag_job_set = True
        
        return self.flag_job_set

    def do_execute(self) -> None:
        if self.process_state == self.process_state_enum.ready.value:
            ...
        elif self.process_state == self.process_state_enum.request.value:
            print("request_send_plan")
            self.do_request_object_detect()# detect objects 요청
        elif self.process_state == self.process_state_enum.wait_ack.value:
            ...
        elif self.process_state == self.process_state_enum.working.value:
            ...
        elif self.process_state == self.process_state_enum.complete.value:
            ...
        elif self.process_state == self.process_state_enum.reset.value:
            # 서비스 request 퓨쳐
            self.future_detect_objects_request = None

            # 서비스 result 퓨쳐
            self.future_detect_objects_response = None

            # 서비스 결과 변수
            self.result_detect_objects = None

        elif self.process_state == self.process_state_enum.error.value:
            ...
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_update(self) -> None:
        self.do_log_state_trasition()
        # print("self.process_state      : {}".format(self.process_state))
        # print("self.flag_job_completed : {}".format(self.flag_job_completed))
        # print("self.flag_job_set       : {}".format(self.flag_job_set))
        # print("self.result             : {}".format(self.result))
        
        detector_properties = self.robot.get_detector_property_instance()
        # ready
        if self.process_state == self.process_state_enum.ready.value:# task 에서 명령이 들어온경우 ready 상태를 send_goal로 전환하여 명령 수행
            if self.flag_job_set == True:# 요청이 확인된 경우 다음 단계로 넘어감
                self.process_state = self.process_state_enum.request.value
                detector_properties.set_state(detector_properties.detector_state_enum.request.value)# 로봇의 상태를 request으로 변경
            ... # 명령이 등록되지 않은 경우는 단순 대기함 뜀
        # request_send_plan
        elif self.process_state == self.process_state_enum.request.value:
            self.process_state = self.process_state_enum.wait_ack.value# send_goal을 수행했다면 acknowlegements 를 대기 
            # 변수들을 확인하여 send_goal 이 수행 완료되었다면 다음 상태로 넘어감
            # 변수들의 상태를 update에서 감시해주는 이유는 
            # callback에서 변수의 상태변화를 일으키는 경우가 매 실행마다 반영되도록 하기 위함이다.

            # 해당 분기에서는 goal handle을 통해 전달된 goal이 accept 되었는지 확인해야 한다.
            # goal이 accept 되었다면 상태를 working으로 전이하고
            # 만약 accept 되지 못했다면 상태를 error로 전이시켜야 한다.
        # wait_ack_send_plan
        elif self.process_state == self.process_state_enum.wait_ack.value:
            # 변수 확인
            if self.future_detect_objects_request is not None:
                self.process_state = self.process_state_enum.working.value
                detector_properties.set_state(detector_properties.detector_state_enum.working.value)# 로봇의 상태를 request으로 변경
            else:
                self.process_state = self.process_state_enum.error.value
                detector_properties.set_state(detector_properties.detector_state_enum.error.value)# 로봇의 상태를 error으로 변경
                # 서비스의 경우 퓨쳐가 어떠한 방식으로 예외처리를 하는지 확인되지 않음...
                # 현재 상황으로는 future 자체의 python 예외를 통하여 예외처리가 되는 것으로 생각됨.
                # ... 어차피 발생한 예외를 처리하지 못하면 시스템이 종료되니, 잘못된 수행을 걱정할 필요는 없을 지도... 
                # futue 객체 예외 목록 링크 참고자료
                # https://docs.python.org/ko/3/library/concurrent.futures.html#exception-classes

        # working_send_plan
        elif self.process_state == self.process_state_enum.working.value:
            # 퓨쳐의 완료 여부를 확인하여 완료 상태로 전이
            if self.future_detect_objects_response is not None:
                if self.future_detect_objects_response.done() == True:
                    # 결과가 실패인지 성공인지 확인
                    print("self.result_detect_objects : {}".format(self.result_detect_objects))
                    if self.result_detect_objects is not None:
                        self.process_state = self.process_state_enum.complete.value
                        detector_properties.set_state(detector_properties.detector_state_enum.complete.value)# 로봇의 상태를 working으로 변경
                    else:
                        self.process_state = self.process_state_enum.error.value
                        detector_properties.set_state(detector_properties.detector_state_enum.error.value)# 로봇의 상태를 error으로 변경
        # complete_send_plan
        elif self.process_state == self.process_state_enum.complete.value:
            # 작업이 완료되면 reset 상태로 전이하여 각종 변수를 리셋
            self.process_state = self.process_state_enum.reset.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = True
        # reset
        elif self.process_state == self.process_state_enum.reset.value:
            # 각종 변수 및 상태를 초기화 한 후 ready 상태로 전이
            self.process_state = self.process_state_enum.ready.value
            detector_properties.set_state(detector_properties.detector_state_enum.ready.value)# 로봇의 상태를 ready으로 변경

        # error
        elif self.process_state == self.process_state_enum.error.value:
            # self.process_state_move_control = self.process_state_enum.error.value
            if self.flag_job_completed == False:
                self.flag_job_completed = True
                self.success = False
                self.result = None
        # halt
        elif self.process_state == self.process_state_enum.halt.value:
            ...

    def do_check_completion(self) -> bool:
        complete_bool_rtn = False
        if self.process_state == self.process_state_enum.ready.value or self.process_state == self.process_state_enum.error.value:
            # 모든 동작이 종료 및 정리되어서 ready 상태로 돌아 왔는지 확인
            # 혹은 error로 인하여 작업이 중단 되었는지 여부를 확인
            if self.flag_job_set == True:# 같은 ready 상태더라도 작업이 걸려있는 상태인지 확인
                if self.flag_job_completed == True:# 작업이 완료되었는지 여부 확인
                    complete_bool_rtn = True
                    self.flag_job_set = False
                    self.flag_job_completed = False
                    if self.process_state == self.process_state_enum.error.value:
                        self.process_state = self.process_state_enum.halt.value
        if self.process_state == self.process_state_enum.halt.value:
            complete_bool_rtn = True
            self.success = False
            self.result = None
        return complete_bool_rtn

    # ros 콜백 정의
    def do_request_object_detect(self):
        print("object_detector_process_test")
        reqest = DetectObjects.Request()# 빈 요청을 보내는 서비스
        self.future_detect_objects_request = self.cli_detect_objects.call_async(reqest)
        # add done callback
        self.future_detect_objects_request.add_done_callback(self.callback_object_detect_result)

    def callback_object_detect_result(self, future):
        self.future_detect_objects_response = future # 메모리 상에서는 self.future_send_plan_request 와 같은 객체를 가리킬 것임.
        self.result_detect_objects = self.future_detect_objects_response.result()
        if self.result_detect_objects != None:
            print("self.success True")
            self.success = True
            self.result = self.result_detect_objects
