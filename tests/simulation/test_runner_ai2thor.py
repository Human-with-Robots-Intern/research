import logging
from unittest.mock import MagicMock, call, patch

import pytest

from ithor.handlers.action import Action as IThorAction  # Import for patching target

# 필요한 데이터 클래스 임포트
from src.core.task import Duration, Execution, Subtask

# 테스트 대상 모듈 임포트
from src.simulation.runner_ai2thor import execute_subtask, init_ai2thor_controller


# Fixtures
@pytest.fixture
def mock_controller():
    """Mock AI2-THOR Controller. 객체 목록 확인"""
    controller = MagicMock()
    mock_event = MagicMock()
    mock_event.metadata = {
        "lastActionSuccess": True,
        # 객체 검증 통과를 위해 obj1, obj2 포함
        "objects": [
            {"objectId": "obj1", "name": "Object1"},
            {"objectId": "obj2", "name": "Object2"},
            {
                "objectId": "obj_monitor",
                "name": "MonitorObj",
                "axisAlignedBoundingBox": {"center": {}, "size": {}},
            },  # bbox 유지
        ],
        "agent": {"position": {"x": 0, "y": 0, "z": 0}, "inventoryObjects": []},
        "actionReturn": [],
        "cameraPosition": {"x": 0.0, "y": 1.0, "z": 0.0},
    }
    controller.last_event = mock_event

    # step side_effect는 실패 시뮬레이션을 위해 유지
    call_count_tracker = {"count": 0}  # nonlocal 대신 dict 사용

    def step_side_effect_failure(*args, **kwargs):
        call_count_tracker["count"] += 1
        # call_count 1: step("Pass") 호출 시
        # call_count 2: 첫 액션(pickup) 후 step 호출 시
        # call_count 3: 두 번째 액션(put) 후 step 호출 시
        print(
            f"[Test Debug] Step call {call_count_tracker['count']}, Args: {args}, Kwargs: {kwargs}"
        )  # 디버깅 로그 강화
        if call_count_tracker["count"] <= 2:
            mock_event.metadata["lastActionSuccess"] = True
        else:  # 두 번째 액션 후 실패
            mock_event.metadata["lastActionSuccess"] = False
            print("[Test Debug] Setting lastActionSuccess to False")  # 디버깅 로그
        return mock_event  # 수정된 mock_event 반환

    controller.step.side_effect = step_side_effect_failure
    return controller


@pytest.fixture
def sample_interaction_subtask():
    """테스트용 상호작용 Subtask. objects 키 확인"""
    return Subtask(
        task_name="Test",
        name="InteractTask",
        repetition=1,
        type="Interaction",
        # objects 목록과 primitive_actions의 타겟이 일치해야 함
        execution=Execution(
            objects=["obj1", "obj2"],
            primitive_actions=["GRASP obj1", "PLACE_ON_TOP obj2"],
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


@pytest.fixture
def sample_monitoring_subtask():
    """테스트용 Monitoring Subtask."""
    return Subtask(
        task_name="Test",
        name="MonitorTask",
        repetition=1,
        type="Monitor",
        execution=Execution(
            objects=["obj_monitor"], primitive_actions=["MONITORING obj_monitor"]
        ),
        duration=Duration(type="Fixed", interval=0.1),
    )


# 테스트 케이스
# --- init_ai2thor_controller 테스트 --- (선택적)
# 이 함수는 실제 Controller 객체를 생성하므로 통합 테스트 성격이 강함
# 여기서는 기본적인 호출 가능 여부만 확인하거나 생략 가능
@patch("src.simulation.runner_ai2thor.Controller")  # 실제 Controller 생성 방지
def test_init_ai2thor_controller(MockController):
    """init_ai2thor_controller 함수 호출 테스트"""
    controller_instance = init_ai2thor_controller(scene="TestScene")
    # Controller 생성자가 올바른 인자들로 호출되었는지 확인
    MockController.assert_called_once()
    call_args, call_kwargs = MockController.call_args
    assert call_kwargs.get("scene") == "TestScene"
    assert isinstance(controller_instance, MagicMock)  # Mock 객체 반환 확인


# --- execute_subtask 테스트 ---
# Action 클래스 mocking: 각 메서드가 호출되는지만 확인하고, 시간/성공 여부는 controller mock으로 제어
@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_success(
    MockAction, mock_controller, sample_interaction_subtask
):
    """execute_subtask 성공 시나리오 테스트"""
    mock_action_instance = MockAction.return_value
    # 각 Action 메서드는 시간을 반환하지 않는다고 가정 (실제 시간은 controller 상태로 관리)
    mock_action_instance.pickup.return_value = (
        0.1  # 임의 시간 (실제로는 controller가 시간 관리)
    )
    mock_action_instance.put.return_value = 0.1

    # Controller가 항상 성공 반환하도록 설정
    mock_controller.last_event.metadata["lastActionSuccess"] = True

    # 객체 검증 로직 통과하도록 metadata 설정
    mock_controller.last_event.metadata["objects"] = [
        {"objectId": "obj1"},
        {"objectId": "obj2"},
    ]

    elapsed_time, success = execute_subtask(mock_controller, sample_interaction_subtask)

    assert success is True
    # elapsed_time은 Action 메서드가 반환하는 시간 합계. 이 mock 방식에서는 부정확할 수 있음.
    # 더 나은 방법: controller.step 호출 시 시간을 증가시키거나, Action mock이 시간을 관리.
    # 여기서는 Action 메서드 반환 시간 합계를 테스트.
    assert abs(elapsed_time - 0.2) < 1e-6
    mock_action_instance.pickup.assert_called_once_with("obj1")
    mock_action_instance.put.assert_called_once_with("obj2")
    # 객체 ID 검증 위해 controller.step("Pass") 호출되었는지 확인
    assert call("Pass") in mock_controller.step.call_args_list


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_action_failure(
    MockAction, mock_controller, sample_interaction_subtask
):
    mock_action_instance = MockAction.return_value
    # Action 메서드는 예외 없이 시간을 반환하도록 설정
    mock_action_instance.pickup.return_value = 0.1
    mock_action_instance.put.return_value = 0.1

    # 객체 목록은 mock_controller fixture에서 설정됨

    elapsed_time, success = execute_subtask(mock_controller, sample_interaction_subtask)

    assert (
        success is False
    ), f"Expected success=False, but got True. Final call count: {mock_controller.step.call_count}"
    assert abs(elapsed_time - 0.2) < 1e-6  # 시간은 여전히 누적될 수 있음
    mock_action_instance.pickup.assert_called_once_with("obj1")
    mock_action_instance.put.assert_called_once_with("obj2")
    assert mock_controller.step.call_count >= 3  # Pass + Action1 + Action2


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_wait(MockAction, mock_controller, sample_wait_subtask):
    """Wait 서브태스크 실행 테스트"""
    mock_action_instance = MockAction.return_value
    mock_action_instance.wait.return_value = 3.0
    elapsed_time, success = execute_subtask(mock_controller, sample_wait_subtask)

    assert success is True
    assert abs(elapsed_time - 3.0) < 1e-6
    mock_action_instance.wait.assert_called_once_with(3.0)


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_init(MockAction, mock_controller, sample_init_subtask):
    """Init 서브태스크 실행 시 즉시 성공 반환 테스트"""
    elapsed_time, success = execute_subtask(mock_controller, sample_init_subtask)
    assert success is True
    assert elapsed_time == 0.0
    MockAction.assert_not_called()  # Should work now


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_unknown_action_skips(MockAction, mock_controller, caplog):
    """알 수 없는 액션 타입 경고 로깅 및 스킵 확인"""
    mock_action_instance = MockAction.return_value
    mock_action_instance.pickup.return_value = 0.1  # GRASP 시간

    unknown_action_subtask = Subtask(
        "Test",
        "UnknownAction",
        1,
        "Interaction",
        execution=Execution(
            objects=["obj1"],
            primitive_actions=["GRASP obj1", "UNKNOWN_ACTION target", "WAIT 1.0"],
        ),
        duration=Duration("C", 1.0),
    )
    # 객체 검증 통과
    mock_controller.last_event.metadata["objects"] = [{"objectId": "obj1"}]
    # WAIT 액션 mock 추가
    mock_action_instance.wait.return_value = 1.0

    # Ensure logging level is captured (e.g., via pytest config or command line)
    caplog.set_level(logging.WARNING)

    elapsed_time, success = execute_subtask(mock_controller, unknown_action_subtask)

    assert success is True
    # Check the specific log message text
    expected_msg = "Unknown action type: UNKNOWN_ACTION. Skipping."
    assert (
        expected_msg in caplog.text
    ), f"Log '{expected_msg}' not found in logs: {caplog.text}"
    assert abs(elapsed_time - 1.1) < 1e-6
    mock_action_instance.pickup.assert_called_once_with("obj1")
    mock_action_instance.wait.assert_called_once_with(1.0)
    # UNKNOWN_ACTION에 해당하는 메서드 호출은 없어야 함 (여기서는 특정 메서드 지정 불가)


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_invalid_format(MockAction, mock_controller, caplog):
    """잘못된 액션 형식은 없고, 알 수 없는 타입 처리 확인"""
    caplog.set_level(logging.WARNING)
    # Use an action with valid format but unknown type
    invalid_type_subtask = Subtask(
        "Test",
        "InvalidType",
        1,
        "Interaction",
        execution=Execution(
            objects=["obj1"], primitive_actions=["INVALID obj1"]
        ),  # Valid format, unknown type "INVALID"
        duration=Duration("C", 1.0),
    )
    mock_controller.last_event.metadata["objects"] = [{"objectId": "obj1"}]

    # This should NOT raise ValueError anymore, but log a warning
    elapsed_time, success = execute_subtask(mock_controller, invalid_type_subtask)

    assert success is True
    assert elapsed_time == 0.0
    # More robust log checking
    expected_msg = "Unknown action type: INVALID. Skipping."
    assert (
        expected_msg in caplog.text
    ), f"Log '{expected_msg}' not found in logs: {caplog.text}"


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_object_not_found(MockAction, mock_controller):
    """존재하지 않는 객체 참조 시 ValueError 발생 확인"""
    subtask_missing_obj = Subtask(
        "Test",
        "MissingObj",
        1,
        "Interaction",
        execution=Execution(
            objects=["nonexistent"], primitive_actions=["GRASP nonexistent"]
        ),
        duration=Duration("C", 1.0),
    )
    # controller 메타데이터에 nonexistent 객체가 없도록 설정
    mock_controller.last_event.metadata["objects"] = [
        {"objectId": "obj1", "position": {"x": 0, "y": 0, "z": 0}}
    ]

    with pytest.raises(ValueError, match="Object 'nonexistent' not found"):
        execute_subtask(mock_controller, subtask_missing_obj)
    # 객체 검증 위해 controller.step("Pass") 호출되었는지 확인
    assert call("Pass") in mock_controller.step.call_args_list


@patch("src.simulation.runner_ai2thor.Action")
def test_execute_subtask_monitoring(
    MockAction, mock_controller, sample_monitoring_subtask
):
    """MONITORING 액션 실행 테스트"""
    mock_action_instance = MockAction.return_value
    mock_action_instance.monitoring.return_value = 0.05  # 예시 시간

    # 객체 검증 통과
    mock_controller.last_event.metadata["objects"] = [{"objectId": "obj_monitor"}]

    elapsed_time, success = execute_subtask(mock_controller, sample_monitoring_subtask)

    assert success is True
    assert abs(elapsed_time - 0.05) < 1e-6
    mock_action_instance.monitoring.assert_called_once_with("obj_monitor")
    assert call("Pass") in mock_controller.step.call_args_list  # 객체 검증 호출 확인
