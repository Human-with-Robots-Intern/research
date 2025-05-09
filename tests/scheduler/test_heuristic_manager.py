import math
from unittest.mock import MagicMock, PropertyMock, call, patch

import networkx as nx  # Needed for CP test setup
import numpy as np
import pytest

from scheduler.action_handler import ActionHandler
from scheduler.constraint_handler import ConstraintHandler

# 테스트 대상 모듈 임포트
from scheduler.heuristic_manager import HeuristicManager
from src.core.agent import Agent  # Agent 임포트 추가

# 필요한 데이터 클래스 및 핸들러 임포트
from src.core.dataclass import (
    ActionResult,
    Candidate,
    SchedulerState,
    SchedulingDue,
    SimulationNode,
)
from src.core.task import Duration, Execution, Subtask
from src.utils.config import EPSILON, LARGE_NUMBER


# Fixtures
@pytest.fixture
def mock_constraint_handler():
    """Mock ConstraintHandler"""
    return MagicMock(spec=ConstraintHandler)


@pytest.fixture
def mock_action_handler():
    """Mock ActionHandler with configurable get_actions_info and _find_shortest_path"""
    mock = MagicMock(spec=ActionHandler)

    # --- get_actions_info Mock ---
    def get_actions_info_side_effect(node, actions):
        action_str = actions[0]
        result = MagicMock(spec=ActionResult)
        result.success = True  # 기본 성공
        result.scene_positions = node.state.scene_positions.copy()  # 상태 복사
        result.held_object = node.state.held_object
        result.action_full_name = action_str
        result.action_type = action_str.split()[0] if action_str else "NO_ACTION"

        if action_str.startswith("NAVIGATE_TO"):
            target = (
                action_str.split()[1] if len(action_str.split()) > 1 else "DefaultDest"
            )
            if "NoPath" in target:  # 경로 없음 시뮬레이션
                result.action_duration = LARGE_NUMBER
                result.cumulative_time = LARGE_NUMBER
                result.success = False
            elif "NoNav" in target:  # 네비게이션 불필요 시뮬레이션
                result.action_duration = 0.0
                result.cumulative_time = 0.0
            else:
                result.action_duration = 1.5  # 기본 네비게이션 시간
                result.cumulative_time = 1.5
                # 실제로는 위치 업데이트도 필요하겠지만 여기서는 생략
        elif action_str == "DO_NOTHING":  # 액션 없는 경우
            result.action_duration = 0.0
            result.cumulative_time = 0.0
        else:  # 일반 서브태스크 실행 시간
            # 간단하게 액션 개수에 비례하도록 설정 (예시)
            duration = len(actions) * 2.0
            if "ShortTask" in action_str:
                duration = len(actions) * 1.0
            elif "FailTask" in action_str:  # 실패 시뮬레이션
                duration = 1.0
                result.success = False

            result.action_duration = (
                duration / len(actions) if actions else 0
            )  # 마지막 액션 시간 (근사치)
            result.cumulative_time = duration
            # 상태 변화 시뮬레이션 필요 시 추가 (예: held_object 변경)

        return result

    mock.get_actions_info.side_effect = get_actions_info_side_effect

    # --- _find_shortest_path Mock ---
    # 기본적으로 간단한 경로 반환, 특정 조건에서 빈 경로 또는 예외 발생
    def find_path_side_effect(pos1, pos2):
        if pos1 == pos2:
            return []
        if pos1 == (0, 0, 0) and pos2 == (1, 1, 0):  # 기본 경로
            return [(0, 0, 0), (0, 1, 0), (1, 1, 0)]  # 2 steps
        if pos1 == (0, 0, 0) and pos2 == (5, 5, 0):  # 긴 경로
            return [(i, i, 0) for i in range(6)]  # 5 steps
        if pos1 == (9, 9, 9):  # 경로 없음 예외 발생 시뮬레이션
            raise ValueError("No path found")
        return [(0, 0, 0), (0, 0, 1)]  # 기본 1 step

    mock._find_shortest_path.side_effect = find_path_side_effect

    return mock


@pytest.fixture
def mock_agent():
    """Mock Agent"""
    return MagicMock(spec=Agent)


@pytest.fixture
def sample_sim_node_factory():
    """Factory for creating SimulationNode with configurable state"""

    def _create_node(
        current_time=10.0,
        agent_pos=(0.0, 0.0, 0.0),
        remaining_tasks=None,
        constraints=None,
    ):
        state = SchedulerState(
            subtask=None,
            completed_entries=[],
            remaining_subtasks=list(remaining_tasks) if remaining_tasks else [],
            constraints=constraints if constraints else nx.DiGraph(),  # 기본 빈 그래프
            current_time=current_time,
            scene_positions={
                "agent": list(agent_pos),
                "Dest1": [1.0, 1.0, 0.0],
                "Dest2": [5.0, 5.0, 0.0],
                "ObjA": [1.0, 0.0, 0.0],
                "ObjB": [0.0, 1.0, 0.0],
            },
            held_object=None,
        )
        # SimulationNode 생성 시 parent_node=None 으로 설정
        return SimulationNode(
            parent_node=None, heuristic_cost=0.0, depth=0, tie_breaker=0, state=state
        )

    return _create_node


@pytest.fixture
def sample_subtask_factory():
    """Factory for creating Subtask mocks"""

    def _create_subtask(
        name,
        duration_interval=4.0,
        nav_target="Dest1",
        interaction="INTERACT",
        objects=None,
    ):
        sub = MagicMock(spec=Subtask)
        sub.name = name
        primitive_actions = []
        if nav_target:
            primitive_actions.append(f"NAVIGATE_TO {nav_target}")
        if interaction:
            # 객체 ID 목록이 주어지면 첫 번째 객체를 사용, 없으면 이름 사용
            target_obj = objects[0] if objects else name
            primitive_actions.append(f"{interaction} {target_obj}")

        sub.execution = MagicMock(spec=Execution)
        sub.execution.primitive_actions = primitive_actions
        sub.execution.objects = objects if objects else [name]  # 객체 목록 설정

        sub.duration = MagicMock(spec=Duration)
        sub.duration.interval = duration_interval  # 순수 상호작용 시간으로 간주
        sub.subtask_type = "Interaction"  # 기본 타입 설정
        if interaction is None:
            sub.subtask_type = "NAVIGATE"  # 상호작용 없으면 네비게이션 타입으로 간주

        # PropertyMock을 사용하여 속성 접근 시 값 반환
        type(sub).name = PropertyMock(return_value=name)
        type(sub).subtask_type = PropertyMock(return_value=sub.subtask_type)
        type(sub).duration = PropertyMock(return_value=sub.duration)
        type(sub).execution = PropertyMock(return_value=sub.execution)

        return sub

    return _create_subtask


@pytest.fixture
def sample_candidate_factory(sample_subtask_factory):
    """Factory for creating Candidate objects"""

    def _create_candidate(
        name="TestCandidate",
        duration=4.0,
        nav_target="Dest1",
        interaction="INTERACT",
        is_crit=False,
        earliest_start=10.0,
        deadline_due=20.0,
        deadline_reason="NextCrit",
        objects=None,
    ):
        subtask = sample_subtask_factory(
            name, duration, nav_target, interaction, objects=objects
        )
        deadline = SchedulingDue(due_date=deadline_due, subtask_name=deadline_reason)
        return Candidate(
            subtask=subtask,
            is_critical=is_crit,
            earliest_start_time=earliest_start,
            deadline=deadline,
        )

    return _create_candidate


@pytest.fixture
def heuristic_manager(mock_constraint_handler, mock_action_handler, mock_agent):
    """테스트용 HeuristicManager 인스턴스 (실제 Config 값 사용 시도)"""
    # 실제 config 값을 사용하도록 수정
    manager = HeuristicManager(
        mock_constraint_handler, mock_action_handler, agent=mock_agent
    )
    # 실제 값 로드 시도 (테스트 환경에 따라 실패 가능성 있음)
    try:
        manager.alpha = ALPHA_HEURISTIC
        manager.beta = BETA_HEURISTIC
        manager.gamma = GAMMA_HEURISTIC
    except NameError:  # config 임포트 실패 시 기본값 사용
        print(
            "Warning: Failed to import heuristic weights from config. Using defaults for test."
        )
        manager.alpha = 1.0
        manager.beta = 1.5
        manager.gamma = 0.5
    return manager


# --- HeuristicManager 초기화 테스트 ---
def test_heuristic_manager_initialization(
    heuristic_manager, mock_constraint_handler, mock_action_handler, mock_agent
):
    """HeuristicManager 초기화 확인"""
    assert heuristic_manager.constraint_handler is mock_constraint_handler
    assert heuristic_manager.action_handler is mock_action_handler
    assert heuristic_manager.agent is mock_agent
    # pytest.approx 사용하여 부동소수점 비교
    assert heuristic_manager.alpha == pytest.approx(ALPHA_HEURISTIC)
    assert heuristic_manager.beta == pytest.approx(BETA_HEURISTIC)
    assert heuristic_manager.gamma == pytest.approx(GAMMA_HEURISTIC)


# --- 내부 도우미 함수 테스트 ---


def test_calculate_navigation_cost_needed(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """네비게이션 비용 계산 (이동 필요한 경우)"""
    current_node = sample_sim_node_factory()
    candidate = sample_candidate_factory(nav_target="Dest1")  # 기본 mock은 1.5초 반환
    cost = heuristic_manager._calculate_navigation_cost(current_node, candidate)
    assert cost == pytest.approx(1.5)
    heuristic_manager.action_handler.get_actions_info.assert_called_once_with(
        current_node, ["NAVIGATE_TO Dest1"]
    )


def test_calculate_navigation_cost_not_needed(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """네비게이션 비용 계산 (이동 불필요 - 첫 액션이 NAVIGATE 아님)"""
    current_node = sample_sim_node_factory()
    candidate = sample_candidate_factory(
        nav_target=None, interaction="INTERACT"
    )  # NAV 없음
    cost = heuristic_manager._calculate_navigation_cost(current_node, candidate)
    assert cost == pytest.approx(0.0)
    heuristic_manager.action_handler.get_actions_info.assert_not_called()  # 네비게이션 없으므로 호출 안됨


def test_calculate_navigation_cost_failed(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """네비게이션 비용 계산 (경로 탐색 실패)"""
    current_node = sample_sim_node_factory()
    candidate = sample_candidate_factory(
        nav_target="NoPath"
    )  # Mock이 실패 반환하도록 설정됨
    cost = heuristic_manager._calculate_navigation_cost(current_node, candidate)
    assert cost == pytest.approx(LARGE_NUMBER)
    heuristic_manager.action_handler.get_actions_info.assert_called_once_with(
        current_node, ["NAVIGATE_TO NoPath"]
    )


def test_calculate_urgency_cost_normal_slack(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """긴급도 비용 계산 (일반적인 슬랙)"""
    # current=10, deadline=20, exec_time=5 -> slack = (20-10)-5 = 5
    current_node = sample_sim_node_factory(current_time=10.0)
    candidate = sample_candidate_factory(
        deadline_due=20.0, duration=4.0
    )  # exec_time=5.0 mock 반환
    heuristic_manager.action_handler.get_actions_info.reset_mock()  # 이전 호출 초기화
    # 서브태스크 실행 시간 mock 설정 (candidate.subtask.execution.primitive_actions 사용)
    mock_exec_result = MagicMock(spec=ActionResult, success=True, cumulative_time=5.0)
    heuristic_manager.action_handler.get_actions_info.return_value = mock_exec_result

    urgency_cost, slack_val = heuristic_manager._calculate_urgency_cost(
        current_node, candidate
    )

    expected_slack = (20.0 - 10.0) - 5.0
    expected_urgency = 1.0 / (expected_slack + EPSILON)
    assert slack_val == pytest.approx(expected_slack)
    assert urgency_cost == pytest.approx(expected_urgency)
    heuristic_manager.action_handler.get_actions_info.assert_called_once_with(
        current_node, candidate.subtask.execution.primitive_actions
    )


def test_calculate_urgency_cost_low_slack(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """긴급도 비용 계산 (슬랙 작을 때)"""
    # current=10, deadline=15.5, exec_time=5 -> slack = (15.5-10)-5 = 0.5
    current_node = sample_sim_node_factory(current_time=10.0)
    candidate = sample_candidate_factory(
        deadline_due=15.5, duration=4.0
    )  # exec_time=5.0 mock 반환
    heuristic_manager.action_handler.get_actions_info.reset_mock()
    mock_exec_result = MagicMock(spec=ActionResult, success=True, cumulative_time=5.0)
    heuristic_manager.action_handler.get_actions_info.return_value = mock_exec_result

    urgency_cost, slack_val = heuristic_manager._calculate_urgency_cost(
        current_node, candidate
    )

    expected_slack = (15.5 - 10.0) - 5.0
    expected_urgency = 1.0 / (expected_slack + EPSILON)
    assert slack_val == pytest.approx(expected_slack)
    assert urgency_cost == pytest.approx(expected_urgency)
    assert urgency_cost > 1.0  # 슬랙 5일때보다 커야 함


def test_calculate_urgency_cost_negative_slack(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """긴급도 비용 계산 (음수 슬랙)"""
    # current=10, deadline=12, exec_time=5 -> slack = (12-10)-5 = -3
    current_node = sample_sim_node_factory(current_time=10.0)
    candidate = sample_candidate_factory(
        deadline_due=12.0, duration=4.0
    )  # exec_time=5.0 mock 반환
    heuristic_manager.action_handler.get_actions_info.reset_mock()
    mock_exec_result = MagicMock(spec=ActionResult, success=True, cumulative_time=5.0)
    heuristic_manager.action_handler.get_actions_info.return_value = mock_exec_result

    urgency_cost, slack_val = heuristic_manager._calculate_urgency_cost(
        current_node, candidate
    )

    expected_slack = (12.0 - 10.0) - 5.0
    assert slack_val == pytest.approx(expected_slack)
    assert urgency_cost == pytest.approx(
        LARGE_NUMBER
    )  # 음수 슬랙 시 LARGE_NUMBER 반환 확인


def test_calculate_urgency_cost_infinite_deadline(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """긴급도 비용 계산 (마감 시간 없음)"""
    current_node = sample_sim_node_factory()
    candidate = sample_candidate_factory(deadline_due=float("inf"))
    urgency_cost, slack_val = heuristic_manager._calculate_urgency_cost(
        current_node, candidate
    )
    assert slack_val == float("inf")
    assert urgency_cost == pytest.approx(0.0)
    # 실행 시간 추정 위한 get_actions_info는 여전히 호출될 수 있음 (구현 따라 다름)
    # heuristic_manager.action_handler.get_actions_info.assert_called()


def test_calculate_urgency_cost_execution_fail(
    heuristic_manager, sample_sim_node_factory, sample_candidate_factory
):
    """긴급도 비용 계산 (실행 시간 추정 실패)"""
    current_node = sample_sim_node_factory()
    candidate = sample_candidate_factory()
    heuristic_manager.action_handler.get_actions_info.reset_mock()
    mock_exec_result = MagicMock(
        spec=ActionResult, success=False, cumulative_time=1.0
    )  # 실패 반환
    heuristic_manager.action_handler.get_actions_info.return_value = mock_exec_result

    urgency_cost, slack_val = heuristic_manager._calculate_urgency_cost(
        current_node, candidate
    )
    assert slack_val == -float("inf")  # 실패 시 슬랙
    assert urgency_cost == pytest.approx(LARGE_NUMBER)  # 실패 시 비용


# --- calc_heuristic 메인 함수 테스트 ---
# 내부 도우미 함수들을 모킹하여 가중합 로직 검증
@patch.object(HeuristicManager, "_calculate_navigation_cost")
@patch.object(HeuristicManager, "_calculate_urgency_cost")
@patch.object(HeuristicManager, "_calculate_critical_path_duration")
@patch.object(HeuristicManager, "_calculate_mst_nav_time")
def test_calc_heuristic_weighting_logic(
    mock_mst,
    mock_cp,
    mock_urgency,
    mock_nav,  # Mock 객체들
    heuristic_manager,
    sample_sim_node_factory,
    sample_candidate_factory,
    sample_subtask_factory,  # Fixtures
):
    """calc_heuristic의 가중합 로직 검증"""
    # Mock 설정
    mock_nav.return_value = 1.5  # nav_cost_candidate
    mock_urgency.return_value = (0.2, 4.0)  # (urgency_cost_candidate, slack_val)
    mock_cp.return_value = 8.0  # critical_interaction_duration
    mock_mst.return_value = 2.5  # mst_nav_time

    # 테스트 데이터 준비
    current_node = sample_sim_node_factory()
    candidate_sub = sample_subtask_factory("Cand", duration=4.0)  # 실행 시간 5.0 가정
    candidate = sample_candidate_factory(subtask=candidate_sub)
    rem_sub1 = sample_subtask_factory("Rem1")
    rem_sub2 = sample_subtask_factory("Rem2")
    current_node.state.remaining_subtasks = [
        candidate_sub,
        rem_sub1,
        rem_sub2,
    ]  # 현재 남은 task 설정

    # 가상 다음 상태 시뮬레이션 Mock 설정 (ActionHandler Mock 사용)
    mock_sim_result = MagicMock(spec=ActionResult, success=True)
    mock_sim_result.scene_positions = {
        "agent": [1.0, 1.0, 0.0]
    }  # 에이전트 위치 변경 가정
    heuristic_manager.action_handler.get_actions_info.return_value = mock_sim_result

    # calc_heuristic 호출
    cost = heuristic_manager.calc_heuristic(current_node, candidate)

    # 예상 비용 계산
    nav_cost_val = 1.5
    urgency_cost_val = 0.2
    future_cost_val = 8.0 + 2.5
    expected_cost = (
        heuristic_manager.alpha * nav_cost_val
        + heuristic_manager.beta * urgency_cost_val
        + heuristic_manager.gamma * future_cost_val
    )

    # 호출 검증
    mock_nav.assert_called_once_with(current_node, candidate)
    mock_urgency.assert_called_once_with(current_node, candidate)
    # future cost 계산 위해 get_actions_info 호출 확인 (가상 다음 상태 생성용)
    heuristic_manager.action_handler.get_actions_info.assert_called_once_with(
        current_node, candidate.subtask.execution.primitive_actions
    )
    # future cost 계산 함수 호출 확인 (가상 다음 상태 정보와 함께 호출되어야 함)
    expected_next_remaining = {rem_sub1, rem_sub2}  # candidate 제외
    mock_cp.assert_called_once()
    # mock_cp 호출 인자 검증 (set 비교는 순서 무관하게)
    assert mock_cp.call_args[0][0] == expected_next_remaining
    assert (
        mock_cp.call_args[0][1] is current_node.state.constraints
    )  # 제약조건은 그대로 전달 가정

    mock_mst.assert_called_once()
    assert mock_mst.call_args[0][0] == tuple(
        mock_sim_result.scene_positions["agent"]
    )  # 변경된 에이전트 위치
    assert mock_mst.call_args[0][1] == expected_next_remaining
    assert (
        mock_mst.call_args[0][2] is mock_sim_result.scene_positions
    )  # 다음 scene position

    # 최종 비용 검증
    assert cost == pytest.approx(expected_cost)


@patch.object(HeuristicManager, "_calculate_navigation_cost")
@patch.object(HeuristicManager, "_calculate_urgency_cost")
def test_calc_heuristic_candidate_fail(
    mock_urgency,
    mock_nav,
    heuristic_manager,
    sample_sim_node_factory,
    sample_candidate_factory,
    sample_subtask_factory,
):
    """calc_heuristic 후보 자체 실패 시 LARGE_NUMBER 반환 확인 (예: 네비 실패)"""
    mock_nav.return_value = LARGE_NUMBER  # 네비 실패
    mock_urgency.return_value = (0.2, 4.0)  # 긴급도는 정상

    current_node = sample_sim_node_factory()
    candidate = sample_candidate_factory()

    cost = heuristic_manager.calc_heuristic(current_node, candidate)
    assert cost == pytest.approx(LARGE_NUMBER)
    # 네비/긴급도 계산 후 바로 반환하므로 future cost 계산 안 함
    heuristic_manager.action_handler.get_actions_info.assert_not_called()


@patch.object(HeuristicManager, "_calculate_navigation_cost")
@patch.object(HeuristicManager, "_calculate_urgency_cost")
@patch.object(HeuristicManager, "_calculate_critical_path_duration")
@patch.object(HeuristicManager, "_calculate_mst_nav_time")
def test_calc_heuristic_future_fail(
    mock_mst,
    mock_cp,
    mock_urgency,
    mock_nav,
    heuristic_manager,
    sample_sim_node_factory,
    sample_candidate_factory,
    sample_subtask_factory,
):
    """calc_heuristic 미래 비용 계산 실패 시 LARGE_NUMBER 반환 확인"""
    mock_nav.return_value = 1.5
    mock_urgency.return_value = (0.2, 4.0)
    mock_cp.return_value = LARGE_NUMBER  # CP 계산 실패
    mock_mst.return_value = 2.5

    current_node = sample_sim_node_factory()
    candidate_sub = sample_subtask_factory("Cand")
    candidate = sample_candidate_factory(subtask=candidate_sub)
    current_node.state.remaining_subtasks = [
        candidate_sub,
        sample_subtask_factory("Rem1"),
    ]

    mock_sim_result = MagicMock(spec=ActionResult, success=True)
    mock_sim_result.scene_positions = {"agent": [1.0, 1.0, 0.0]}
    heuristic_manager.action_handler.get_actions_info.return_value = mock_sim_result

    cost = heuristic_manager.calc_heuristic(current_node, candidate)
    assert cost == pytest.approx(LARGE_NUMBER)


# TODO: _calculate_critical_path_duration 테스트 케이스 추가
# 예: def test_calculate_critical_path_duration_linear(): ...
# 예: def test_calculate_critical_path_duration_parallel(): ...
# 예: def test_calculate_critical_path_duration_cycle_detection(): ...

# TODO: _calculate_mst_nav_time 테스트 케이스 추가
# 예: def test_calculate_mst_nav_time_basic(): ...
# 예: def test_calculate_mst_nav_time_no_path(): ... (ActionHandler mock 활용)
# 예: def test_calculate_mst_nav_time_scipy_unavailable(): ... (ImportError mock 필요)

# TODO: _get_estimated_interaction_time, _get_task_start_location, _estimate_nav_time 에 대한 단위 테스트 추가
