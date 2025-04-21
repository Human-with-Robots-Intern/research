import copy
from unittest.mock import MagicMock, patch

import pytest

# 필요한 데이터 클래스 임포트
from core.dataclass import (
    ActionResult,
    ActionSimulationLog,
    CompletedEntry,
    Duration,
    Execution,
    SchedulerState,
    SimulationNode,
    Subtask,
)

# 테스트 대상 모듈 임포트
from scheduler.action_handler import ActionHandler
from src.utils.config.constants import (
    MONITORING_DURATION,
    NAV_STEP_DURATION,
    PRIMITIVE_ACTION_DURATION,
)


# Fixtures
@pytest.fixture
def mock_nav_graph():
    """간단한 모의 네비게이션 그래프"""
    # 실제 그래프 구조는 더 복잡할 것임
    return {
        (0.0, 0.0, 0.0): [(0.0, 0.0, 1.0)],
        (0.0, 0.0, 1.0): [(0.0, 0.0, 0.0), (1.0, 0.0, 1.0)],
        (1.0, 0.0, 1.0): [(0.0, 0.0, 1.0)],
    }


@pytest.fixture
def sample_sim_node():
    """테스트용 기본 SimulationNode"""
    initial_state = SchedulerState(
        subtask=None,  # 초기 상태는 subtask 없음
        completed_subtasks=[],
        remaining_subtasks=[],
        constraints=MagicMock(),  # 모의 DiGraph
        current_time=0.0,
        scene_positions={
            "agent": (0.0, 0.0, 0.0),
            "objA": (0.0, 0.0, 1.0),
            "objB": (1.0, 0.0, 1.0),
            "receptacle": (1.0, 0.0, 0.0),  # 예시 위치
        },
        held_object=None,
    )
    return SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=initial_state,
    )


@pytest.fixture
def action_handler(mock_nav_graph):  # fixture 이름 변경
    """테스트용 ActionHandler 인스턴스"""
    return ActionHandler(nav_graph=mock_nav_graph)


# 테스트 케이스
def test_action_handler_initialization(action_handler, mock_nav_graph):
    """ActionHandler 초기화 확인"""
    assert action_handler.nav_graph == mock_nav_graph


# --- _find_shortest_path 테스트 ---
# 실제 경로 탐색 알고리즘 테스트는 복잡하므로 여기서는 간단한 케이스만 확인
def test_find_shortest_path_same_pos(action_handler):
    """출발지와 목적지가 같을 때 경로 확인"""
    path = action_handler._find_shortest_path((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert path == [(0.0, 0.0, 0.0)]


@patch(
    "scheduler.action_handler.adjust_if_unreachable", side_effect=lambda g, p: p
)  # adjust 함수 모킹
def test_find_shortest_path_simple(mock_adjust, action_handler):
    """간단한 경로 탐색 확인 (모의 그래프 기반)"""
    path = action_handler._find_shortest_path((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert path == [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    path2 = action_handler._find_shortest_path((0.0, 0.0, 1.0), (1.0, 0.0, 1.0))
    assert path2 == [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0)]


# --- _simulate_actions 테스트 ---
@patch.object(
    ActionHandler, "_find_shortest_path", return_value=[(0, 0, 0), (0, 0, 1)]
)  # 경로 탐색 모킹
def test_simulate_actions_nav(mock_find_path, action_handler, sample_sim_node):
    """네비게이션 액션 시뮬레이션 테스트"""
    actions = ["NAVIGATE_TO objA"]
    log = action_handler._simulate_actions(sample_sim_node, actions)

    assert len(log.results) == 1
    result = log.results[0]
    assert result.action_type == "NAVIGATE_TO"
    # 경로 길이 2 * NAV_STEP_DURATION
    expected_duration = 2 * NAV_STEP_DURATION
    assert abs(result.action_duration - expected_duration) < 1e-6
    assert (
        abs(result.time_used - expected_duration) < 1e-6
    )  # 첫 액션이므로 누적 시간 = 소요 시간
    assert result.scene_positions["agent"] == (0.0, 0.0, 1.0)  # 에이전트 위치 변경 확인
    assert result.held_object is None
    mock_find_path.assert_called_once()


@patch.object(
    ActionHandler, "_find_shortest_path", return_value=[(0, 0, 0)]
)  # 이동 없는 경우 가정
def test_simulate_actions_grasp_place(mock_find_path, action_handler, sample_sim_node):
    """Grasp, Place 액션 시뮬레이션 테스트"""
    actions = ["GRASP objA", "PLACE_ON_TOP receptacle"]
    # 초기 상태 복사 (held_object 변경 테스트 위해)
    node_copy = copy.deepcopy(sample_sim_node)

    log = action_handler._simulate_actions(node_copy, actions)

    assert len(log.results) == 2
    grasp_res = log.results[0]
    place_res = log.results[1]

    # Grasp 확인
    assert grasp_res.action_type == "GRASP"
    assert grasp_res.action_duration == PRIMITIVE_ACTION_DURATION
    assert grasp_res.time_used == PRIMITIVE_ACTION_DURATION
    assert grasp_res.held_object == "objA"

    # Place 확인
    assert place_res.action_type == "PLACE_ON_TOP"
    assert place_res.action_duration == PRIMITIVE_ACTION_DURATION
    expected_time = PRIMITIVE_ACTION_DURATION * 2
    assert abs(place_res.time_used - expected_time) < 1e-6
    assert place_res.held_object is None  # 객체 내려놓음
    # 객체 위치 변경 확인 (objA가 receptacle 위치로)
    assert (
        place_res.scene_positions["objA"]
        == sample_sim_node.state.scene_positions["receptacle"]
    )


def test_simulate_actions_wait(action_handler, sample_sim_node):
    """WAIT 액션 시뮬레이션 테스트"""
    actions = ["WAIT 3.5"]
    log = action_handler._simulate_actions(sample_sim_node, actions)
    assert len(log.results) == 1
    result = log.results[0]
    assert result.action_type == "WAIT"
    assert abs(result.action_duration - 3.5) < 1e-6
    assert abs(result.time_used - 3.5) < 1e-6
    # 상태 변화 없음 확인
    assert result.scene_positions == sample_sim_node.state.scene_positions
    assert result.held_object == sample_sim_node.state.held_object


# --- get_actions_info 테스트 ---
# 이 메소드는 _simulate_actions를 호출하고 마지막 결과를 반환
@patch.object(ActionHandler, "_simulate_actions")
def test_get_actions_info(mock_simulate, action_handler, sample_sim_node):
    """get_actions_info가 _simulate_actions 호출 및 마지막 결과 반환 확인"""
    # 모의 ActionSimulationLog 생성
    mock_log = ActionSimulationLog()
    mock_result1 = ActionResult(
        "ACTION1", "TYPE1", 1.0, 1.0, {"agent": (0, 0, 0)}, None
    )
    mock_result2 = ActionResult(
        "ACTION2", "TYPE2", 2.5, 1.5, {"agent": (0, 0, 1)}, "obj"
    )
    mock_log.results = [mock_result1, mock_result2]
    mock_simulate.return_value = mock_log

    actions = ["ACTION1", "ACTION2"]
    last_action_result = action_handler.get_actions_info(sample_sim_node, actions)

    mock_simulate.assert_called_once()
    assert last_action_result is mock_result2  # 마지막 결과 반환 확인


def test_get_actions_info_empty(action_handler, sample_sim_node):
    """액션 리스트가 비었을 때 None 반환 확인"""
    result = action_handler.get_actions_info(sample_sim_node, [])
    assert result is None


# --- split_subtask_by_cutoff_time 테스트 ---
@patch.object(ActionHandler, "_simulate_actions")
def test_split_subtask_no_correction(mock_simulate, action_handler, sample_sim_node):
    """Grasp/Place 보정이 필요 없는 경우의 분할 테스트"""
    # _simulate_actions 모의 결과 설정
    full_log = ActionSimulationLog()
    full_log.add_result("NAVIGATE_TO A", "NAVIGATE_TO", 2.0, 2.0, {}, None)
    full_log.add_result("ACTION A", "TYPE_A", 3.0, 1.0, {}, None)
    full_log.add_result("NAVIGATE_TO B", "NAVIGATE_TO", 5.0, 2.0, {}, None)
    full_log.add_result("ACTION B", "TYPE_B", 6.0, 1.0, {}, None)
    mock_simulate.side_effect = [
        full_log,  # 첫 번째 호출 (전체 시뮬레이션)
        # 이후 호출은 분할된 리스트 시뮬레이션 결과 (여기선 단순화)
        ActionSimulationLog(results=full_log.results[:2]),
        ActionSimulationLog(results=full_log.results[2:]),
    ]

    primitive_actions = [res.action_full_name for res in full_log.results]
    cutoff_time = 3.5  # ACTION A와 NAV B 사이

    pre_info, post_info = action_handler.split_subtask_by_cutoff_time(
        sample_sim_node, primitive_actions, cutoff_time
    )

    assert mock_simulate.call_count == 3  # 전체, pre, post 시뮬레이션
    assert len(pre_info.results) == 2
    assert pre_info.results[0].action_full_name == "NAVIGATE_TO A"
    assert pre_info.results[1].action_full_name == "ACTION A"
    assert len(post_info.results) == 2
    assert post_info.results[0].action_full_name == "NAVIGATE_TO B"
    assert post_info.results[1].action_full_name == "ACTION B"


@patch.object(ActionHandler, "_simulate_actions")
def test_split_subtask_with_correction(mock_simulate, action_handler, sample_sim_node):
    """Grasp/Place 보정이 필요한 경우의 분할 테스트"""
    full_log = ActionSimulationLog()
    full_log.add_result(
        "NAVIGATE_TO A", "NAVIGATE_TO", 2.0, 2.0, {"agent": (0, 0, 1)}, None
    )
    full_log.add_result(
        "GRASP A", "GRASP", 3.0, 1.0, {"agent": (0, 0, 1)}, "A"
    )  # Grasp
    full_log.add_result(
        "NAVIGATE_TO R", "NAVIGATE_TO", 5.0, 2.0, {"agent": (1, 0, 1)}, "A"
    )
    full_log.add_result(
        "PLACE_ON_TOP R", "PLACE_ON_TOP", 6.0, 1.0, {"agent": (1, 0, 1)}, None
    )  # Place
    full_log.add_result("FINAL ACTION", "TYPE_F", 7.0, 1.0, {"agent": (1, 0, 1)}, None)

    # Grasp까지만 pre에 포함되도록 cutoff 설정
    cutoff_time = 3.5
    primitive_actions = [res.action_full_name for res in full_log.results]

    # 재시뮬레이션 결과 모킹 (보정 후 결과 반영)
    # 보정 후: pre = [NAV A, GRASP A, NAV R, PLACE R], post = [FINAL ACTION]
    mock_pre_results = full_log.results[:4]
    mock_post_results = full_log.results[4:]
    mock_simulate.side_effect = [
        full_log,
        ActionSimulationLog(results=mock_pre_results),
        ActionSimulationLog(results=mock_post_results),
    ]

    pre_info, post_info = action_handler.split_subtask_by_cutoff_time(
        sample_sim_node, primitive_actions, cutoff_time
    )

    assert mock_simulate.call_count == 3
    assert len(pre_info.results) == 4  # NAV, GRASP, NAV, PLACE 포함
    assert len(post_info.results) == 1  # FINAL ACTION만 포함
    assert pre_info.results[-1].action_type == "PLACE_ON_TOP"
    assert post_info.results[0].action_full_name == "FINAL ACTION"
