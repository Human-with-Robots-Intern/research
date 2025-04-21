from unittest.mock import MagicMock, patch

import pytest

# 필요한 데이터 클래스 임포트
from core.dataclass import Duration, Execution, Subtask

# 테스트 대상 모듈 임포트
from simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller


# Fixtures
@pytest.fixture
def mock_controller():
    """Mock AI2-THOR Controller."""
    controller = MagicMock()
    # last_event 및 metadata 모킹
    mock_event = MagicMock()
    mock_event.metadata = {
        "lastActionSuccess": True,
        "objects": [],  # 필요시 객체 정보 추가
        "agent": {
            "position": {"x": 0, "y": 0, "z": 0},
            "inventoryObjects": [],
        },  # 에이전트 정보
    }
    controller.last_event = mock_event
    # step 메소드가 mock_event 반환하도록 설정
    controller.step.return_value = mock_event
    return controller


@pytest.fixture
def sample_interaction_subtask():
    """테스트용 상호작용 Subtask."""
    return Subtask(
        task_name="Test",
        name="InteractTask",
        repetition=1,
        type="Interaction",
        execution=Execution(
            objects={"obj1": 1}, primitive_actions=["GRASP obj1", "PLACE_ON_TOP obj2"]
        ),
        duration=Duration(type="Controllable", interval=2.0),
    )


@pytest.fixture
def sample_wait_subtask():
    """테스트용 Wait Subtask."""
    return Subtask(
        task_name="Test",
        name="WaitTask",
        repetition=1,
        type="Wait",
        execution=Execution(objects=None, primitive_actions=["WAIT 3.0"]),
        duration=Duration(type="Controllable", interval=3.0),
    )


@pytest.fixture
def sample_init_subtask():
    """테스트용 Init Subtask."""
    return Subtask(
        task_name="Init",
        name="Init",
        repetition=1,
        type="Init",
        execution=Execution(None, []),
        duration=Duration("Fixed", 0.0),
    )


# 테스트 케이스
# --- init_ai2thor_controller 테스트 --- (선택적)
# 이 함수는 실제 Controller 객체를 생성하므로 통합 테스트 성격이 강함
# 여기서는 기본적인 호출 가능 여부만 확인하거나 생략 가능
@patch("simulation.runner_ai2thor.Controller")  # 실제 Controller 생성 방지
def test_init_ai2thor_controller(MockController):
    """init_ai2thor_controller 함수 호출 테스트"""
    controller_instance = init_ai2thor_controller(scene="TestScene")
    # Controller 생성자가 올바른 인자들로 호출되었는지 확인
    MockController.assert_called_once()
    call_args, call_kwargs = MockController.call_args
    assert call_kwargs.get("scene") == "TestScene"
    assert isinstance(controller_instance, MagicMock)  # Mock 객체 반환 확인


# --- execute_subtask 테스트 ---
# Action 클래스 및 내부 메소드 모킹 필요
@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_success(
    MockAction, mock_controller, sample_interaction_subtask
):
    """execute_subtask 성공 시나리오 테스트"""
    # Action 클래스의 인스턴스 및 메소드 모킹
    mock_action_instance = MockAction.return_value
    # 각 액션 타입에 대한 메소드가 특정 시간 반환하도록 설정
    mock_action_instance.pickup.return_value = 0.1  # GRASP
    mock_action_instance.put.return_value = 0.1  # PLACE_ON_TOP

    elapsed_time, success = execute_subtask(mock_controller, sample_interaction_subtask)

    assert success is True
    assert abs(elapsed_time - 0.2) < 1e-6  # 0.1 + 0.1
    # Action 메소드 호출 확인
    mock_action_instance.pickup.assert_called_once_with("obj1")
    mock_action_instance.put.assert_called_once_with("obj2")
    # controller.step은 객체 확인 시 한 번, 각 액션 후 성공 확인 위해 호출될 수 있음 (구현 따라 다름)
    # 여기서는 action 내부에서 처리한다고 가정하고 step 호출 확인은 생략하거나 상세 구현 확인 필요


@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_failure(
    MockAction, mock_controller, sample_interaction_subtask
):
    """execute_subtask 실패 시나리오 테스트"""
    # Action 클래스의 인스턴스 모킹
    mock_action_instance = MockAction.return_value
    mock_action_instance.pickup.return_value = 0.1
    mock_action_instance.put.return_value = 0.1

    # 두 번째 액션(PLACE) 실행 후 실패하도록 Controller 상태 설정
    mock_fail_event = MagicMock()
    mock_fail_event.metadata = {"lastActionSuccess": False}

    # controller.step이 두 번째 호출에서 실패 이벤트 반환하도록 설정
    # 또는 Action 메소드 내에서 last_event를 직접 설정? -> Action 모킹을 더 상세히
    def step_side_effect(*args, **kwargs):
        # 첫 액션 후 성공 반환 가정 (pickup 후)
        if mock_action_instance.put.call_count == 0:  # 아직 put 호출 전
            mock_controller.last_event.metadata["lastActionSuccess"] = True
        # 두 번째 액션 후 실패 반환 (put 후)
        else:
            mock_controller.last_event.metadata["lastActionSuccess"] = False
        return mock_controller.last_event

    mock_controller.step.side_effect = step_side_effect
    # Action 메소드가 내부적으로 controller.step을 호출한다고 가정

    elapsed_time, success = execute_subtask(mock_controller, sample_interaction_subtask)

    assert success is False
    assert abs(elapsed_time - 0.2) < 1e-6  # 시간은 실패 지점까지 누적
    mock_action_instance.pickup.assert_called_once()
    mock_action_instance.put.assert_called_once()


@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_wait(MockAction, mock_controller, sample_wait_subtask):
    """Wait 서브태스크 실행 테스트"""
    mock_action_instance = MockAction.return_value
    mock_action_instance.wait.return_value = 3.0  # wait 메소드가 시간 반환 가정

    elapsed_time, success = execute_subtask(mock_controller, sample_wait_subtask)

    assert success is True
    assert abs(elapsed_time - 3.0) < 1e-6
    mock_action_instance.wait.assert_called_once_with("3.0")  # 문자열로 전달됨 확인


@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_init(MockAction, mock_controller, sample_init_subtask):
    """Init 서브태스크 실행 시 즉시 성공 반환 테스트"""
    elapsed_time, success = execute_subtask(mock_controller, sample_init_subtask)
    assert success is True
    assert elapsed_time == 0.0
    MockAction.assert_not_called()  # Action 객체 생성 안 함


@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_unknown_action(MockAction, mock_controller):
    """알 수 없는 액션 타입 포함 시 경고 로깅 및 스킵 확인 (선택적)"""
    # 로그 캡처 설정 (pytest caplog fixture 사용)
    # def test_execute_subtask_unknown_action(MockAction, mock_controller, caplog):
    #    ... (로깅 테스트 로직) ...
    # 현재는 로깅 테스트 생략
    mock_action_instance = MockAction.return_value
    mock_action_instance.pickup.return_value = 0.1

    unknown_action_subtask = Subtask(
        "Test",
        "UnknownAction",
        1,
        "Interaction",
        Execution(None, ["GRASP obj1", "UNKNOWN_ACTION target"]),
        Duration("C", 1.0),
    )

    elapsed_time, success = execute_subtask(mock_controller, unknown_action_subtask)

    assert success is True  # 알 수 없는 액션은 무시하고 나머지가 성공하면 성공
    assert abs(elapsed_time - 0.1) < 1e-6  # GRASP 시간만 누적
    mock_action_instance.pickup.assert_called_once()


@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_invalid_format(MockAction, mock_controller):
    """잘못된 액션 형식 포함 시 ValueError 발생 확인"""
    invalid_format_subtask = Subtask(
        "Test",
        "InvalidFormat",
        1,
        "Interaction",
        Execution(None, ["INVALID ACTION FORMAT"]),
        Duration("C", 1.0),
    )
    with pytest.raises(ValueError, match="Invalid action format"):
        execute_subtask(mock_controller, invalid_format_subtask)


# 객체 ID 검증 로직 테스트 (선택적)
# controller.last_event.metadata["objects"] 모킹 필요
@patch("simulation.runner_ai2thor.Action")
def test_execute_subtask_object_not_found(MockAction, mock_controller):
    """존재하지 않는 객체 참조 시 ValueError 발생 확인"""
    subtask_missing_obj = Subtask(
        "Test",
        "MissingObj",
        1,
        "Interaction",
        Execution(objects={"nonexistent": 1}, primitive_actions=["GRASP nonexistent"]),
        Duration("C", 1.0),
    )
    # controller 메타데이터에 nonexistent 객체가 없도록 설정
    mock_controller.last_event.metadata["objects"] = [
        {"objectId": "obj1", "position": {"x": 0, "y": 0, "z": 0}}
    ]

    with pytest.raises(ValueError, match="Object 'nonexistent' not found"):
        execute_subtask(mock_controller, subtask_missing_obj)
