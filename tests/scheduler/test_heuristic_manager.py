import math
from unittest.mock import MagicMock, patch

import pytest

# 필요한 데이터 클래스 및 핸들러 임포트
from core.dataclass import (
    ActionResult,
    Candidate,
    Deadline,
    Duration,
    Execution,
    SchedulerState,
    SimulationNode,
    Subtask,
)
from scheduler.action_handler import ActionHandler
from scheduler.constraint_handler import ConstraintHandler

# 테스트 대상 모듈 임포트
from scheduler.heuristic_manager import HeuristicManager
from src.utils.config import EPSILON, LARGE_NUMBER


# Fixtures
@pytest.fixture
def mock_constraint_handler():
    """Mock ConstraintHandler"""
    return MagicMock(spec=ConstraintHandler)


@pytest.fixture
def mock_action_handler():
    """Mock ActionHandler with configurable get_actions_info"""
    mock = MagicMock(spec=ActionHandler)

    # 기본 반환값 설정 (ActionResult 모킹)
    default_nav_result = MagicMock(spec=ActionResult)
    default_nav_result.time_used = 1.0  # 기본 네비게이션 시간
    default_nav_result.action_duration = 1.0

    default_sub_result = MagicMock(spec=ActionResult)
    default_sub_result.time_used = 5.0  # 기본 서브태스크 총 시간
    default_sub_result.action_duration = 4.0  # 마지막 액션 시간

    # side_effect를 사용하여 호출 인자에 따라 다른 값 반환 가능하게 함
    def side_effect_func(node, actions):
        action_str = actions[0]
        if action_str.startswith("NAVIGATE_TO"):  # 네비게이션 시간 요청 시
            # nav_time 조정 필요 시 여기서 가능
            mock_nav_result = MagicMock(spec=ActionResult)
            mock_nav_result.time_used = 1.0
            mock_nav_result.action_duration = 1.0
            # 특정 목적지에 따라 다른 시간 반환 가능
            if "NoNav" in action_str:
                mock_nav_result.time_used = 0.0
            return mock_nav_result
        else:  # 전체 서브태스크 시간 요청 시
            # estimated_duration 조정 필요 시 여기서 가능
            mock_sub_result = MagicMock(spec=ActionResult)
            mock_sub_result.time_used = 5.0
            mock_sub_result.action_duration = 1.0  # 마지막 액션 시간 가정
            if "ShortTask" in actions[0]:
                mock_sub_result.time_used = 2.0
            return mock_sub_result

    mock.get_actions_info.side_effect = side_effect_func
    return mock


@pytest.fixture
def sample_sim_node():
    """테스트용 기본 SimulationNode"""
    state = SchedulerState(
        subtask=None,
        completed_subtasks=[],
        remaining_subtasks=[],
        constraints=MagicMock(),
        current_time=10.0,  # 현재 시간 10.0 가정
        scene_positions={"agent": (0, 0, 0)},
        held_object=None,
    )
    return SimulationNode(0.0, 0, 0, None, state)


@pytest.fixture
def sample_candidate(
    name="TestCandidate",
    is_crit=False,
    adj_start=10.0,
    log_start=11.0,
    deadline_due=20.0,
    nav_action="NAVIGATE_TO Dest",
):
    """테스트용 기본 Candidate 생성 헬퍼"""
    sub = Subtask(
        task_name="TestTask",
        name=name,
        repetition=1,
        type="Interaction",
        execution=Execution(objects={}, primitive_actions=[nav_action, "DO_SOMETHING"]),
        duration=Duration(type="Controllable", interval=4.0),  # interval은 참고용
    )
    deadline = Deadline(due_date=deadline_due, subtask_name="NextCrit")
    return Candidate(
        subtask=sub,
        is_critical=is_crit,
        adjusted_start_time=adj_start,
        logical_start_time=log_start,
        deadline=deadline,
    )


@pytest.fixture
def heuristic_manager(mock_constraint_handler, mock_action_handler):
    """테스트용 HeuristicManager 인스턴스 (기본 가중치 사용)"""
    # knowledge_base는 None으로 전달 (분산 항 제거됨)
    manager = HeuristicManager(
        mock_constraint_handler, mock_action_handler, knowledge_base=None
    )
    # 테스트의 일관성을 위해 기본 가중치 명시적 설정 (실제 __init__과 동일하게)
    manager.alpha = 1.0
    manager.beta = 1.5
    manager.zeta = 0.1
    manager.weight_remaining_count = 0.3
    manager.weight_remaining_duration = 0.7
    return manager


# 테스트 케이스
def test_heuristic_manager_initialization(
    heuristic_manager, mock_constraint_handler, mock_action_handler
):
    """HeuristicManager 초기화 및 기본 가중치 확인"""
    assert heuristic_manager.constraint_handler is mock_constraint_handler
    assert heuristic_manager.action_handler is mock_action_handler
    assert heuristic_manager.alpha == 1.0
    assert heuristic_manager.beta == 1.5
    assert heuristic_manager.zeta == 0.1


def test_estimate_remaining_cost_empty(heuristic_manager):
    """남은 작업 없을 때 _estimate_remaining_cost가 0 반환 확인"""
    cost = heuristic_manager._estimate_remaining_cost([])
    assert cost == 0.0


def test_estimate_remaining_cost_calculation(heuristic_manager):
    """_estimate_remaining_cost 계산 (개수 + 총 예상 시간 가중 합) 확인"""
    sub1 = Subtask("Task", "Sub1", 1, "T", Execution(None, []), Duration("C", 10.0))
    sub2 = Subtask("Task", "Sub2", 1, "T", Execution(None, []), Duration("C", 5.0))
    sub3 = Subtask(
        "Task", "Sub3", 1, "T", Execution(None, []), Duration("C", None)
    )  # Duration 없는 경우
    remaining = [sub1, sub2, sub3]

    expected_count = 3.0
    expected_total_duration = 10.0 + 5.0  # sub3는 제외
    expected_cost = (
        heuristic_manager.weight_remaining_count * expected_count
        + heuristic_manager.weight_remaining_duration * expected_total_duration
    )

    cost = heuristic_manager._estimate_remaining_cost(remaining)
    assert abs(cost - expected_cost) < EPSILON


def test_calc_heuristic_basic(heuristic_manager, sample_sim_node, sample_candidate):
    """기본적인 휴리스틱 계산 확인"""
    candidate = sample_candidate()  # 기본값 사용 (adj_start=10, deadline=20)
    remaining = [sample_candidate("Rem1").subtask, sample_candidate("Rem2").subtask]
    # _estimate_remaining_cost 계산 (가정: 각 duration 4.0)
    est_rem_cost = (
        heuristic_manager.weight_remaining_count * 2.0
        + heuristic_manager.weight_remaining_duration * (4.0 + 4.0)
    )
    # calc_heuristic 내부에서 estimate_duration 계산 (mock_action_handler가 5.0 반환)
    estimated_duration = 5.0
    # 슬랙 계산: (20.0 - 10.0) - 5.0 = 5.0
    slack_val = 5.0
    urgency_term = -1.0 / math.sqrt(slack_val + EPSILON)
    # nav_time 계산 (mock_action_handler가 1.0 반환)
    nav_time = 1.0

    expected_cost = (
        heuristic_manager.alpha * nav_time
        + heuristic_manager.beta * urgency_term
        + heuristic_manager.zeta * est_rem_cost
    )

    cost = heuristic_manager.calc_heuristic(sample_sim_node, candidate, remaining)
    assert abs(cost - expected_cost) < EPSILON


def test_calc_heuristic_no_nav(heuristic_manager, sample_sim_node, sample_candidate):
    """네비게이션 없는 경우 확인"""
    candidate = sample_candidate(nav_action="DO_SOMETHING_FIRST")  # 첫 액션이 NAV 아님
    cost = heuristic_manager.calc_heuristic(sample_sim_node, candidate, [])
    # nav_cost = 0, urgency_cost와 remaining_cost만 계산됨 (remaining 없으므로 0)
    estimated_duration = 5.0  # mock_action_handler 반환값
    slack_val = (20.0 - 10.0) - 5.0
    urgency_term = -1.0 / math.sqrt(slack_val + EPSILON)
    expected_cost = heuristic_manager.beta * urgency_term
    assert abs(cost - expected_cost) < EPSILON


def test_calc_heuristic_high_urgency(
    heuristic_manager, sample_sim_node, sample_candidate
):
    """긴급도 높을 때 (슬랙 작을 때) 확인"""
    # deadline=15.5 -> slack = (15.5 - 10.0) - 5.0 = 0.5
    candidate = sample_candidate(deadline_due=15.5)
    cost = heuristic_manager.calc_heuristic(sample_sim_node, candidate, [])

    slack_val = 0.5
    urgency_term = -1.0 / math.sqrt(slack_val + EPSILON)
    nav_time = 1.0
    expected_cost = (
        heuristic_manager.alpha * nav_time + heuristic_manager.beta * urgency_term
    )
    assert abs(cost - expected_cost) < EPSILON
    # 슬랙 5.0일 때보다 비용이 낮아지는지 확인 (더 선호되어야 함)
    basic_candidate = sample_candidate(deadline_due=20.0)
    basic_cost = heuristic_manager.calc_heuristic(sample_sim_node, basic_candidate, [])
    assert cost < basic_cost


def test_calc_heuristic_infinite_deadline(
    heuristic_manager, sample_sim_node, sample_candidate
):
    """마감 시간 없을 때 urgency_term이 0인지 확인"""
    candidate = sample_candidate(deadline_due=float("inf"))
    cost = heuristic_manager.calc_heuristic(sample_sim_node, candidate, [])
    nav_time = 1.0
    expected_cost = heuristic_manager.alpha * nav_time  # urgency_cost = 0
    assert abs(cost - expected_cost) < EPSILON


def test_calc_heuristic_negative_slack(
    heuristic_manager, sample_sim_node, sample_candidate
):
    """슬랙 0 이하일 때 LARGE_NUMBER 반환 확인"""
    # deadline=14.5 -> slack = (14.5 - 10.0) - 5.0 = -0.5
    candidate = sample_candidate(deadline_due=14.5)
    cost = heuristic_manager.calc_heuristic(sample_sim_node, candidate, [])
    assert cost == LARGE_NUMBER


# calc_heuristic에서 action_handler.get_actions_info 실패 시 처리 테스트 추가 가능
# _estimate_remaining_cost에서 duration 없는 경우 처리 테스트 추가 가능
