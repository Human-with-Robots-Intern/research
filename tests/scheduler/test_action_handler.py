import copy
import logging
import math
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest

# 필요한 데이터 클래스 임포트
from src.core.dataclass import (
    ActionResult,
    ActionSimulationLog,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from src.core.task import Duration, Execution, Subtask

# 테스트 대상 모듈 임포트
from src.scheduler.action_handler import ActionHandler
from src.utils.config.constants import (
    EPSILON,
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
    REACHABLE_DISTANCE_THRESHOLD,
)


# Fixtures
@pytest.fixture
def mock_nav_graph():
    """간단한 모의 네비게이션 그래프"""
    # 테스트 시나리오에 맞게 확장 가능
    return {
        (0.0, 0.0, 0.0): [(0.0, 0.0, 1.0)],
        (0.0, 0.0, 1.0): [(0.0, 0.0, 0.0), (1.0, 0.0, 1.0)],
        (1.0, 0.0, 1.0): [(0.0, 0.0, 1.0)],
        (5.0, 5.0, 5.0): [],  # 도달 불가능 지점
        # _find_shortest_path 테스트용 추가
        (0.0, 0.0, 2.0): [(1.0, 0.0, 2.0)],
        (1.0, 0.0, 2.0): [(0.0, 0.0, 2.0)],
    }


@pytest.fixture
def sample_sim_node():
    """테스트용 기본 SimulationNode"""
    initial_state = SchedulerState(
        subtask=None,
        completed_entries=[],
        remaining_subtasks=[],
        constraints=MagicMock(),
        current_time=0.0,
        scene_positions={
            "agent": (0.0, 0.0, 0.0),
            "objA": (0.0, 0.0, 1.0),
            "objB": (1.0, 0.0, 1.0),
            "receptacle": (1.0, 0.0, 0.0),
            "unreachable_obj": (5.0, 5.0, 5.0),
            "no_path_target": (9.0, 9.0, 9.0),  # 경로 없음 테스트용
            "target": (2.0, 0.0, 0.0),
        },
        held_object=None,
    )
    # parent_node=None 추가
    return SimulationNode(
        parent_node=None,
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        state=initial_state,
    )


@pytest.fixture
def action_handler(mock_nav_graph):
    """테스트용 ActionHandler 인스턴스"""
    return ActionHandler(nav_graph=mock_nav_graph)


# --- _find_shortest_path 테스트 ---
# adjust_if_unreachable은 실제 함수를 사용한다고 가정 (필요 시 별도 테스트)
# 또는 이전처럼 모킹 유지 가능


def test_find_shortest_path_same_pos(action_handler):
    """출발지와 목적지가 같을 때 빈 경로 반환 확인"""
    # 동일 위치일 때 빈 리스트 반환 (src 코드 로직 확인 필요)
    path = action_handler._find_shortest_path((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert path == []  # 빈 리스트 기대 (step 0)


# adjust_if_unreachable 모킹 제거 (실제 로직 사용 가정)
def test_find_shortest_path_simple(action_handler):
    """간단한 경로 탐색 확인 (모의 그래프 기반)"""
    # 경로: (0,0,0) -> (0,0,1) (1 step)
    path = action_handler._find_shortest_path((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert path == [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    # 경로: (0,0,1) -> (1,0,1) (1 step)
    path2 = action_handler._find_shortest_path((0.0, 0.0, 1.0), (1.0, 0.0, 1.0))
    assert path2 == [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0)]


# adjust_if_unreachable 모킹 제거
def test_find_shortest_path_no_path(action_handler):
    """경로가 없을 때 ValueError 발생 확인"""
    with pytest.raises(ValueError, match="No path found"):
        # mock_nav_graph에 (0,0,0) -> (5,5,5) 경로는 없음
        action_handler._find_shortest_path((0.0, 0.0, 0.0), (5.0, 5.0, 5.0))


# --- _simulate_actions 테스트 ---


# _simulate_navigate 시간을 정확히 테스트하기 위해 _find_shortest_path 모킹
@patch.object(
    ActionHandler, "_find_shortest_path", return_value=[(0, 0, 0), (0, 0, 1), (1, 0, 1)]
)  # 2 steps
def test_simulate_actions_nav_success(action_handler, sample_sim_node):
    """성공적인 네비게이션 액션 시뮬레이션 테스트 (시간 계산 수정)"""
    actions = ["NAVIGATE_TO objB"]  # objB 위치는 (1.0, 0.0, 1.0)
    log = action_handler._simulate_actions(sample_sim_node, actions)

    assert log is not None and len(log.results) == 1
    result = log.results[0]
    assert result.success is True
    assert result.action_type == "NAVIGATE_TO"
    # 예상 시간: 경로 스텝 수 * NAV_STEP_DURATION (len=3 -> 2 steps)
    expected_duration = 2 * NAV_STEP_DURATION
    assert result.cumulative_time == pytest.approx(expected_duration)
    assert result.action_duration == pytest.approx(
        expected_duration
    )  # 단일 액션이므로 동일
    assert result.scene_positions["agent"] == (1.0, 0.0, 1.0)  # 최종 목적지
    assert result.held_object is None
    # find_shortest_path 호출 인자 확인
    mock_find_path.assert_called_once_with((0.0, 0.0, 0.0), (1.0, 0.0, 1.0))


# _simulate_navigate가 경로 없음 시 ValueError를 처리하고 실패/0시간 반환 가정
@patch.object(
    ActionHandler, "_find_shortest_path", side_effect=ValueError("No path found")
)
def test_simulate_actions_nav_no_path_handled(
    mock_find_path, action_handler, sample_sim_node, caplog
):
    """네비게이션 경로 없을 때 핸들러가 처리하고 실패 반환 확인"""
    actions = ["NAVIGATE_TO no_path_target"]
    caplog.set_level(logging.WARNING)  # 경고 로그 캡처

    log = action_handler._simulate_actions(sample_sim_node, actions)

    assert log is not None and len(log.results) == 1
    result = log.results[0]
    assert result.success is False  # 네비게이션 실패
    assert result.action_duration == pytest.approx(0.0)  # 시간 0
    assert result.cumulative_time == pytest.approx(0.0)
    # 에이전트 위치는 그대로
    assert result.scene_positions["agent"] == (0.0, 0.0, 0.0)
    # 경고 로그 확인 (_simulate_navigate 내부에서 발생 가정)
    # 실제 로그 메시지는 src 코드 확인 필요
    assert "Pathfinding failed between" in caplog.text
    mock_find_path.assert_called_once()


# _simulate_navigate가 잘못된 시간 형식 시 ValueError 발생 가정
def test_simulate_actions_nav_invalid_partial_time_exception(
    action_handler, sample_sim_node
):
    """부분 네비게이션 시간 잘못되었을 때 ValueError 발생 확인"""
    actions = ["NAVIGATE_TO objA invalid_time"]
    # _simulate_actions 내부의 _simulate_navigate에서 ValueError 발생 예상
    with pytest.raises(ValueError, match="could not convert string to float"):
        action_handler._simulate_actions(sample_sim_node, actions)


# GRASP/PLACE 등 오류 상황은 ValueError 발생으로 테스트 수정
def test_simulate_actions_grasp_place_success(action_handler, sample_sim_node):
    """성공적인 Grasp, Place 액션 시뮬레이션 테스트"""
    # 이 테스트에서는 네비게이션이 없다고 가정 (mock_find_path 불필요)
    actions = ["GRASP objA", "PLACE_ON_TOP receptacle"]
    node_copy = copy.deepcopy(sample_sim_node)

    log = action_handler._simulate_actions(node_copy, actions)

    assert log is not None and len(log.results) == 2
    grasp_res = log.results[0]
    place_res = log.results[1]

    assert grasp_res.success is True
    assert grasp_res.action_type == "GRASP"
    assert grasp_res.cumulative_time == pytest.approx(PRIMITIVE_ACTION_DURATION)
    assert grasp_res.held_object == "objA"

    assert place_res.success is True
    assert place_res.action_type == "PLACE_ON_TOP"
    expected_time = PRIMITIVE_ACTION_DURATION * 2
    assert place_res.cumulative_time == pytest.approx(expected_time)
    assert place_res.held_object is None
    assert place_res.scene_positions["objA"] == pytest.approx(
        sample_sim_node.state.scene_positions["receptacle"]
    )


def test_simulate_actions_grasp_while_holding_exception(
    action_handler, sample_sim_node
):
    """객체를 들고 있을 때 GRASP 시도 시 ValueError 발생 확인"""
    node_holding = copy.deepcopy(sample_sim_node)
    node_holding.state.held_object = "objB"
    actions = ["GRASP objA"]
    # _simulate_actions 내부의 _simulate_grasp에서 ValueError 발생 예상
    with pytest.raises(ValueError, match="Agent already holding"):
        action_handler._simulate_actions(node_holding, actions)


def test_simulate_actions_place_while_empty_exception(action_handler, sample_sim_node):
    """들고 있는 객체가 없을 때 PLACE 시도 시 ValueError 발생 확인"""
    actions = ["PLACE_ON_TOP receptacle"]
    # _simulate_actions 내부의 _simulate_place에서 ValueError 발생 예상
    with pytest.raises(ValueError, match="Agent not holding anything"):
        action_handler._simulate_actions(sample_sim_node, actions)


def test_simulate_actions_target_not_in_scene_exception(
    action_handler, sample_sim_node
):
    """존재하지 않는 객체를 타겟으로 할 때 ValueError 발생 확인"""
    actions = ["GRASP non_existent_obj"]
    # 각 액션 함수(_simulate_grasp 등) 시작 시 객체 존재 확인 가정
    with pytest.raises(ValueError, match="target 'non_existent_obj' not found"):
        action_handler._simulate_actions(sample_sim_node, actions)


def test_simulate_actions_wait(action_handler, sample_sim_node):
    """WAIT 액션 시뮬레이션 테스트"""
    actions = ["WAIT 3.5"]
    log = action_handler._simulate_actions(sample_sim_node, actions)
    assert log is not None and len(log.results) == 1
    result = log.results[0]
    assert result.success is True
    assert result.action_type == "WAIT"
    assert result.cumulative_time == pytest.approx(3.5)
    assert result.action_duration == pytest.approx(3.5)
    assert result.scene_positions == sample_sim_node.state.scene_positions
    assert result.held_object == sample_sim_node.state.held_object


def test_simulate_actions_wait_invalid_duration_exception(
    action_handler, sample_sim_node
):
    """WAIT 액션 시간 형식이 잘못되었을 때 ValueError 발생 확인"""
    actions = ["WAIT invalid"]
    # _simulate_actions 내부의 _simulate_wait에서 ValueError 발생 예상
    with pytest.raises(ValueError, match="Invalid WAIT duration"):
        action_handler._simulate_actions(sample_sim_node, actions)


def test_simulate_actions_unknown_action_skips(action_handler, sample_sim_node, caplog):
    """알 수 없는 액션 타입일 때 경고 로깅 및 스킵 확인"""
    actions = ["GRASP objA", "UNKNOWN_ACTION target", "WAIT 1.0"]
    caplog.set_level(logging.WARNING)  # 경고 로그 캡처

    log = action_handler._simulate_actions(sample_sim_node, actions)

    assert log is not None
    # GRASP, WAIT 결과만 있어야 함
    assert len(log.results) == 2
    assert log.results[0].action_type == "GRASP"
    assert log.results[1].action_type == "WAIT"
    # 경고 로그 확인
    assert "Unknown action type: UNKNOWN_ACTION. Skipping." in caplog.text
    # 최종 시간은 GRASP 시간 + WAIT 시간
    expected_time = PRIMITIVE_ACTION_DURATION + 1.0
    assert log.results[-1].cumulative_time == pytest.approx(expected_time)
    assert log.results[-1].success is True  # 마지막 액션 성공


# --- get_actions_info 테스트 ---
@patch.object(ActionHandler, "_simulate_actions")
def test_get_actions_info(mock_simulate, action_handler, sample_sim_node):
    """get_actions_info가 _simulate_actions 호출 및 마지막 결과 반환 확인"""
    mock_log = ActionSimulationLog()
    mock_result1 = ActionResult(
        "ACTION1", "TYPE1", 1.0, 1.0, {"agent": (0, 0, 0)}, None, True
    )
    mock_result2 = ActionResult(
        "ACTION2", "TYPE2", 2.5, 1.5, {"agent": (0, 0, 1)}, "obj", True
    )
    mock_log.results = [mock_result1, mock_result2]
    mock_simulate.return_value = mock_log

    actions = ["ACTION1", "ACTION2"]
    last_action_result = action_handler.get_actions_info(sample_sim_node, actions)

    mock_simulate.assert_called_once_with(sample_sim_node, actions)
    assert last_action_result is mock_result2


def test_get_actions_info_empty(action_handler, sample_sim_node):
    """액션 리스트가 비었을 때 None 반환 확인"""
    result = action_handler.get_actions_info(sample_sim_node, [])
    assert result is None
    # _simulate_actions는 호출되지 않아야 함
    # assert action_handler._simulate_actions.call_count == 0 # 직접 mock 없이는 불가


@patch.object(ActionHandler, "_simulate_actions", side_effect=ValueError("Sim failed"))
def test_get_actions_info_handles_simulation_error(
    mock_simulate, action_handler, sample_sim_node
):
    """_simulate_actions에서 오류 발생 시 get_actions_info가 예외 재발생 확인"""
    with pytest.raises(ValueError, match="Sim failed"):
        action_handler.get_actions_info(sample_sim_node, ["ACTION"])
    mock_simulate.assert_called_once_with(sample_sim_node, ["ACTION"])


# --- split_subtask_by_cutoff_time 테스트 (Mock 방식 수정) ---
@patch.object(ActionHandler, "_simulate_actions")
def test_split_subtask_no_correction(mock_simulate, action_handler, sample_sim_node):
    """Grasp/Place 보정이 필요 없는 경우의 분할 테스트 (Mock 방식 수정)"""
    # 전체 시뮬레이션 결과 설정
    full_log = ActionSimulationLog()
    full_log.add_result("NAVIGATE_TO A", "NAVIGATE_TO", 2.0, 2.0, {}, None, True)
    full_log.add_result(
        "ACTION A", "TYPE_A", 3.0, 1.0, {}, None, True
    )  # cutoff=3.5 여기 포함
    full_log.add_result("NAVIGATE_TO B", "NAVIGATE_TO", 5.0, 2.0, {}, None, True)
    full_log.add_result("ACTION B", "TYPE_B", 6.0, 1.0, {}, None, True)
    mock_simulate.return_value = full_log  # 단일 반환값 설정

    primitive_actions = [res.action_full_name for res in full_log.results]
    # cutoff_time은 상대 시간이므로 node.state.current_time(0.0) 기준으로 3.5
    cutoff_time = 3.5

    pre_info, post_info = action_handler.split_subtask_by_cutoff_time(
        sample_sim_node, primitive_actions, cutoff_time
    )

    mock_simulate.assert_called_once_with(
        sample_sim_node, primitive_actions
    )  # _simulate_actions는 한번만 호출됨
    assert len(pre_info.results) == 2
    assert pre_info.results[0].action_full_name == "NAVIGATE_TO A"
    assert pre_info.results[1].action_full_name == "ACTION A"
    assert len(post_info.results) == 2
    assert post_info.results[0].action_full_name == "NAVIGATE_TO B"
    assert post_info.results[1].action_full_name == "ACTION B"


@patch.object(ActionHandler, "_simulate_actions")
def test_split_subtask_with_correction(mock_simulate, action_handler, sample_sim_node):
    """Grasp/Place 보정이 필요한 경우의 분할 테스트 (Mock 방식 수정)"""
    full_log = ActionSimulationLog()
    full_log.add_result("NAVIGATE_TO A", "NAVIGATE_TO", 2.0, 2.0, {}, None, True)
    full_log.add_result(
        "GRASP A", "GRASP", 3.0, 1.0, {}, "A", True
    )  # Grasp (cutoff=3.5 여기 포함)
    full_log.add_result("NAVIGATE_TO R", "NAVIGATE_TO", 5.0, 2.0, {}, "A", True)
    full_log.add_result(
        "PLACE_ON_TOP R", "PLACE_ON_TOP", 6.0, 1.0, {}, None, True
    )  # Place (보정되어 pre에 포함)
    full_log.add_result("FINAL ACTION", "TYPE_F", 7.0, 1.0, {}, None, True)
    mock_simulate.return_value = full_log  # 단일 반환값 설정

    # cutoff_time은 GRASP 직후
    cutoff_time = 3.5
    primitive_actions = [res.action_full_name for res in full_log.results]

    pre_info, post_info = action_handler.split_subtask_by_cutoff_time(
        sample_sim_node, primitive_actions, cutoff_time
    )

    mock_simulate.assert_called_once_with(sample_sim_node, primitive_actions)
    assert len(pre_info.results) == 4  # NAV, GRASP, NAV, PLACE 포함 (보정됨)
    assert pre_info.results[-1].action_type == "PLACE_ON_TOP"
    assert len(post_info.results) == 1  # FINAL ACTION만 포함
    assert post_info.results[0].action_full_name == "FINAL ACTION"


@patch.object(
    ActionHandler,
    "_simulate_actions",
    side_effect=ValueError("Initial simulation failed"),
)
def test_split_subtask_simulation_error(mock_simulate, action_handler, sample_sim_node):
    """분할 중 _simulate_actions 오류 발생 시 ValueError 발생 확인"""
    actions = ["ACTION A", "ACTION B"]
    cutoff_time = 1.0

    with pytest.raises(ValueError, match="Initial simulation failed"):
        action_handler.split_subtask_by_cutoff_time(
            sample_sim_node, actions, cutoff_time
        )
    mock_simulate.assert_called_once_with(sample_sim_node, actions)


# 재시뮬레이션 실패 테스트는 split_subtask_by_cutoff_time 내부 로직이
# _simulate_actions를 여러 번 호출하지 않으므로 제거하거나 수정 필요.
# 현재 로직(한번만 호출)에서는 이 시나리오가 발생하지 않음.
# test_split_subtask_resimulation_error 제거
