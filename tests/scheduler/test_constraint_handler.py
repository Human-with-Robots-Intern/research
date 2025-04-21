from unittest.mock import MagicMock, PropertyMock, patch

import networkx as nx
import pytest

# 필요한 데이터 클래스 임포트
from core.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    Deadline,
    Duration,
    Execution,
    SchedulerState,
    SimulationNode,
    Subtask,
    TimeSlot,
)
from scheduler.action_handler import ActionHandler

# 테스트 대상 모듈 임포트
from scheduler.constraint_handler import ConstraintHandler
from src.utils.config import EPSILON


# Fixtures
@pytest.fixture
def mock_action_handler():
    """Mock ActionHandler."""
    mock = MagicMock(spec=ActionHandler)
    # get_actions_info가 ActionResult 또는 None 반환하도록 설정
    mock_nav_result = MagicMock(spec=ActionResult)
    mock_nav_result.time_used = 1.0  # 예시 네비게이션 시간
    mock.get_actions_info.return_value = mock_nav_result
    return mock


@pytest.fixture
def sample_subtask(name, est=0.0, crit=False):
    """간단한 Subtask 객체 생성 헬퍼"""
    # 테스트 편의를 위해 Subtask 모킹 또는 간단한 객체 생성
    mock_sub = MagicMock(spec=Subtask)
    mock_sub.name = name
    mock_sub.execution.primitive_actions = [
        f"NAVIGATE_TO {name}"
    ]  # 네비게이션 시간 계산 위해 필요
    # 실제로는 Duration 등 다른 속성도 필요할 수 있음
    mock_sub.duration = Duration(type="Controllable", interval=5.0)  # 예시 duration
    return mock_sub


@pytest.fixture
def create_test_node(current_time, completed, remaining, constraints):
    """테스트용 SimulationNode 생성 헬퍼"""
    # 마지막 완료된 subtask 설정 (없으면 None)
    last_completed_sub = completed[-1].subtask if completed else None
    state = SchedulerState(
        subtask=last_completed_sub,
        completed_subtasks=completed,
        remaining_subtasks=remaining,
        constraints=constraints,
        current_time=current_time,
        scene_positions={"agent": (0, 0, 0)},  # 기본 위치
        held_object=None,
    )
    return SimulationNode(0.0, 0, 0, None, state)


# 테스트 케이스
def test_get_earliest_start_time_no_predecessor(mock_action_handler, sample_subtask):
    """선행 작업 없는 경우 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    sub = sample_subtask("TaskA")
    constraints.add_node(sub.name)
    node = create_test_node(0.0, [], [sub], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, sub)

    assert start_time == 0.0
    assert is_critical is False
    assert status == "COMPLETED"


def test_get_earliest_start_time_predecessor_not_done(
    mock_action_handler, sample_subtask
):
    """선행 작업 미완료 시 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred = sample_subtask("Pred")
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 0, "IsCritical": False}
    )
    node = create_test_node(
        0.0, [], [pred, succ], constraints
    )  # pred가 completed에 없음

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert start_time is None
    assert status is None  # 미완료


def test_get_earliest_start_time_predecessor_failed(
    mock_action_handler, sample_subtask
):
    """선행 작업 실패 시 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred = sample_subtask("Pred")
    pred.execution_status = False  # 선행 작업 실패 상태 설정
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 0, "IsCritical": False}
    )
    completed = [CompletedEntry(pred, 0.0, 5.0)]
    node = create_test_node(5.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert start_time is None
    assert status == "FAILED"


def test_get_earliest_start_time_non_critical(mock_action_handler, sample_subtask):
    """Non-critical 제약 조건 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred1 = sample_subtask("Pred1")
    pred2 = sample_subtask("Pred2")
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred1.name, succ.name, info={"Interval": 2.0, "IsCritical": False}
    )
    constraints.add_edge(
        pred2.name, succ.name, info={"Interval": 3.0, "IsCritical": False}
    )
    completed = [CompletedEntry(pred1, 0.0, 5.0), CompletedEntry(pred2, 1.0, 7.0)]
    node = create_test_node(7.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    # pred1 완료(5.0) + interval(2.0) = 7.0
    # pred2 완료(7.0) + interval(3.0) = 10.0
    # 둘 중 max 값 사용
    assert abs(start_time - 10.0) < EPSILON
    assert is_critical is False
    assert status == "COMPLETED"


def test_get_earliest_start_time_critical(mock_action_handler, sample_subtask):
    """Critical 제약 조건 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred = sample_subtask("Pred")
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )
    completed = [CompletedEntry(pred, 0.0, 10.0)]
    node = create_test_node(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    # pred 완료(10.0) + interval(5.0) = 15.0
    assert abs(start_time - 15.0) < EPSILON
    assert is_critical is True
    assert status == "COMPLETED"


def test_get_earliest_start_time_critical_conflict(mock_action_handler, sample_subtask):
    """Critical 시간 충돌 시 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred1 = sample_subtask("Pred1")
    pred2 = sample_subtask("Pred2")
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred1.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )  # 예상 시작: 15.0
    constraints.add_edge(
        pred2.name, succ.name, info={"Interval": 7.0, "IsCritical": True}
    )  # 예상 시작: 17.0 -> 충돌!
    completed = [CompletedEntry(pred1, 0.0, 10.0), CompletedEntry(pred2, 0.0, 10.0)]
    node = create_test_node(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert start_time is None
    assert status == "FAILED"  # 충돌은 실패로 간주


def test_get_earliest_start_time_mixed_constraints(mock_action_handler, sample_subtask):
    """Critical과 Non-critical 혼합 시 테스트 (Critical 우선)"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred_crit = sample_subtask("PredCrit")
    pred_non = sample_subtask("PredNon")
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred_crit.name, succ.name, info={"Interval": 10.0, "IsCritical": True}
    )  # 예상 시작: 20.0
    constraints.add_edge(
        pred_non.name, succ.name, info={"Interval": 5.0, "IsCritical": False}
    )  # 예상 시작: 15.0
    completed = [
        CompletedEntry(pred_crit, 0.0, 10.0),
        CompletedEntry(pred_non, 0.0, 10.0),
    ]
    node = create_test_node(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert abs(start_time - 20.0) < EPSILON
    assert is_critical is True
    assert status == "COMPLETED"


def test_get_earliest_start_time_mixed_conflict(mock_action_handler, sample_subtask):
    """Critical과 Non-critical 혼합 시 충돌 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred_crit = sample_subtask("PredCrit")
    pred_non = sample_subtask("PredNon")
    succ = sample_subtask("Succ")
    constraints.add_edge(
        pred_crit.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )  # 예상 시작: 15.0
    constraints.add_edge(
        pred_non.name, succ.name, info={"Interval": 10.0, "IsCritical": False}
    )  # 예상 시작: 20.0 -> 충돌!
    completed = [
        CompletedEntry(pred_crit, 0.0, 10.0),
        CompletedEntry(pred_non, 0.0, 10.0),
    ]
    node = create_test_node(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert start_time is None
    assert status == "FAILED"


# --- get_feasible_candidates 테스트 ---
# 이 테스트는 get_earliest_start_time 결과에 의존하므로 mocking 또는 실제 호출 결합
@patch.object(ConstraintHandler, "get_earliest_start_time")
def test_get_feasible_candidates_logic(mock_get_est, mock_action_handler):
    """get_feasible_candidates의 분류 로직 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    # Mock ActionHandler의 get_actions_info 설정 (네비게이션 시간 예측용)
    mock_nav_result = MagicMock(spec=ActionResult)
    mock_nav_result.time_used = 1.0
    mock_action_handler.get_actions_info.return_value = mock_nav_result

    # 테스트용 서브태스크 생성
    sub_feasible_non_crit = sample_subtask("FeasibleNonCrit")
    sub_feasible_crit = sample_subtask("FeasibleCrit", crit=True)
    sub_not_yet_non_crit = sample_subtask("NotYetNonCrit")
    sub_not_yet_crit = sample_subtask("NotYetCrit", crit=True)
    sub_failed = sample_subtask("FailedPred")
    sub_not_done = sample_subtask("NotDonePred")

    remaining = [
        sub_feasible_non_crit,
        sub_feasible_crit,
        sub_not_yet_non_crit,
        sub_not_yet_crit,
        sub_failed,
        sub_not_done,
    ]

    current_time = 10.0
    # get_earliest_start_time 모의 반환값 설정
    # (logical_start_time, is_critical, status)
    mock_get_est.side_effect = [
        (9.0, False, "COMPLETED"),  # FeasibleNonCrit (logical=9, adjusted=8, feasible)
        (11.0, True, "COMPLETED"),  # FeasibleCrit (logical=11, adjusted=10, feasible)
        (15.0, False, "COMPLETED"),  # NotYetNonCrit (logical=15, adjusted=14, not_yet)
        (13.0, True, "COMPLETED"),  # NotYetCrit (logical=13, adjusted=12, not_yet)
        (None, False, "FAILED"),  # FailedPred
        (None, False, None),  # NotDonePred
    ]

    node = create_test_node(current_time, [], remaining, nx.DiGraph())
    feasible, not_yet = handler.get_feasible_candidates(node)

    assert len(feasible) == 2
    assert len(not_yet) == 2

    feasible_names = {c.subtask.name for c in feasible}
    not_yet_names = {c.subtask.name for c in not_yet}

    assert "FeasibleNonCrit" in feasible_names
    assert "FeasibleCrit" in feasible_names
    assert "NotYetNonCrit" in not_yet_names
    assert "NotYetCrit" in not_yet_names

    # 각 후보의 adjusted_start_time 확인
    fc_non_crit = next(c for c in feasible if c.subtask.name == "FeasibleNonCrit")
    fc_crit = next(c for c in feasible if c.subtask.name == "FeasibleCrit")
    nyc_non_crit = next(c for c in not_yet if c.subtask.name == "NotYetNonCrit")
    nyc_crit = next(c for c in not_yet if c.subtask.name == "NotYetCrit")

    assert abs(fc_non_crit.adjusted_start_time - 8.0) < EPSILON  # 9.0 - 1.0
    assert abs(fc_crit.adjusted_start_time - 10.0) < EPSILON  # 11.0 - 1.0
    assert abs(nyc_non_crit.adjusted_start_time - 14.0) < EPSILON  # 15.0 - 1.0
    assert abs(nyc_crit.adjusted_start_time - 12.0) < EPSILON  # 13.0 - 1.0


# --- _assign_deadlines 테스트 ---
def test_assign_deadlines_no_crit(mock_action_handler):
    """Not-yet에 critical 없을 때 무한대 deadline 할당 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    feasible = [
        Candidate(sample_subtask("F1"), False, 5.0, 5.0),
        Candidate(sample_subtask("F2"), False, 7.0, 7.0),
    ]
    not_yet = [Candidate(sample_subtask("NY1"), False, 10.0, 10.0)]

    result = handler._assign_deadlines(feasible, not_yet)

    assert result[0].deadline.due_date == float("inf")
    assert result[1].deadline.due_date == float("inf")


def test_assign_deadlines_with_crit(mock_action_handler):
    """Not-yet에 critical 있을 때 deadline 할당 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    feasible = [Candidate(sample_subtask("F1"), False, 5.0, 5.0)]
    # adjusted_start_time 기준 정렬 확인 위해 순서 섞음
    not_yet = [
        Candidate(sample_subtask("NY_NonCrit"), False, 15.0, 15.0),
        Candidate(sample_subtask("NY_Crit2"), True, 20.0, 21.0),  # Adjusted=20
        Candidate(sample_subtask("NY_Crit1"), True, 18.0, 19.0),
    ]  # Adjusted=18 (이것이 다음 critical)

    result = handler._assign_deadlines(feasible, not_yet)

    assert (
        abs(result[0].deadline.due_date - 18.0) < EPSILON
    )  # NY_Crit1의 adjusted_start_time
    assert result[0].deadline.subtask_name == "NY_Crit1"


# get_time_slots 테스트는 비교적 간단하여 생략 가능 또는 추가
