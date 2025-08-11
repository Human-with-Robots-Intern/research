import math
from unittest.mock import MagicMock, PropertyMock, call, patch

import networkx as nx
import pytest

# 필요한 데이터 클래스 임포트
from models.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SchedulingDue,
    SimulationNode,
    TimeSlot,
)
from models.task import Duration, Execution, Subtask
from src.scheduler.action_handler import ActionHandler

# 테스트 대상 모듈 임포트
from src.scheduler.constraint_handler import ConstraintHandler
from src.utils.config import EPSILON, LARGE_NUMBER


# Fixtures
@pytest.fixture
def mock_action_handler():
    """Mock ActionHandler."""
    mock = MagicMock(spec=ActionHandler)
    # 기본적으로 성공하고 1.0 시간 걸리는 ActionResult 반환 설정
    # 각 테스트에서 필요 시 side_effect 재정의 가능
    mock_nav_result = MagicMock(spec=ActionResult)
    mock_nav_result.cumulative_time = 1.0
    mock_nav_result.action_duration = 1.0
    mock_nav_result.success = True
    mock.get_actions_info.return_value = mock_nav_result
    return mock


@pytest.fixture
def sample_subtask_factory():
    def _create_subtask(name, est=0.0, crit=False, execution_status=True):
        mock_sub = MagicMock(spec=Subtask)
        mock_sub.name = name
        # execution 속성도 Mock 객체로 만들고 primitive_actions 설정
        mock_sub.execution = MagicMock(spec=Execution)
        mock_sub.execution.primitive_actions = [f"NAVIGATE_TO {name}"]
        mock_sub.duration = MagicMock(spec=Duration)
        mock_sub.duration.interval = 5.0  # 예시 duration
        # execution_status 설정 (테스트에서 필요시 None으로 설정 가능)
        # CompletedEntry 에는 execution_status가 있지만 Subtask 자체에는 없을 수 있음
        # 이 fixture는 Subtask mock을 만들므로, 여기서는 설정 불필요

        # name 속성을 읽을 수 있도록 설정
        type(mock_sub).name = PropertyMock(return_value=name)
        type(mock_sub).execution = PropertyMock(
            return_value=mock_sub.execution
        )  # execution 접근 가능하게
        return mock_sub

    return _create_subtask


@pytest.fixture
def create_test_node(request):  # fixture로 변경하고 request 사용 가능
    """테스트용 SimulationNode 생성 헬퍼 fixture"""

    def _create_node(current_time, completed, remaining, constraints):
        last_completed_sub = completed[-1].subtask if completed else None
        state = SchedulerState(
            subtask=last_completed_sub,
            completed_entries=completed,
            remaining_subtasks=remaining,
            constraints=constraints,
            current_time=current_time,
            scene_positions={"agent": [0.0, 0.0, 0.0]},
            held_object=None,
        )
        # SimulationNode 생성 시 parent_node=None 으로 설정
        return SimulationNode(
            parent_node=None, heuristic_cost=0.0, depth=0, tie_breaker=0, state=state
        )

    return _create_node


@pytest.fixture
def constraint_handler(mock_action_handler):
    """테스트용 ConstraintHandler 인스턴스"""
    return ConstraintHandler(mock_action_handler)


# --- get_earliest_start_time 테스트 (기존 테스트 유지, assert 수정) ---


def test_get_earliest_start_time_no_predecessor(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """선행 작업 없는 경우 테스트"""
    constraints = nx.DiGraph()
    sub = sample_subtask_factory("TaskA")
    constraints.add_node(sub.name)
    node = create_test_node(0.0, [], [sub], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, sub
    )
    assert start_time == 0.0
    assert is_critical is False
    assert status == "COMPLETED"


def test_get_earliest_start_time_predecessor_not_done(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """선행 작업 미완료 시 테스트"""
    constraints = nx.DiGraph()
    pred = sample_subtask_factory("Pred")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 0, "IsCritical": False}
    )
    node = create_test_node(
        0.0, [], [pred, succ], constraints
    )  # pred가 completed에 없음
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "NOT_READY"
    assert start_time is None


def test_get_earliest_start_time_predecessor_failed(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """선행 작업 실패 시 테스트"""
    constraints = nx.DiGraph()
    pred_sub = sample_subtask_factory("Pred")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred_sub.name, succ.name, info={"Interval": 0, "IsCritical": False}
    )
    # CompletedEntry에 execution_status=False 설정
    completed = [CompletedEntry(pred_sub, 0.0, 5.0, execution_status=False)]
    node = create_test_node(5.0, completed, [succ], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "FAILED_PREDECESSOR"
    assert start_time is None


def test_get_earliest_start_time_non_critical(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """Non-critical 제약 조건 테스트"""
    constraints = nx.DiGraph()
    pred1 = sample_subtask_factory("Pred1")
    pred2 = sample_subtask_factory("Pred2")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred1.name, succ.name, info={"Interval": 2.0, "IsCritical": False}
    )
    constraints.add_edge(
        pred2.name, succ.name, info={"Interval": 3.0, "IsCritical": False}
    )
    # CompletedEntry 생성 시 schedule_end_time 지정
    completed = [
        CompletedEntry(pred1, schedule_start_time=0.0, schedule_end_time=5.0),
        CompletedEntry(pred2, schedule_start_time=1.0, schedule_end_time=7.0),
    ]
    node = create_test_node(7.0, completed, [succ], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "COMPLETED"
    assert start_time is not None
    # max(5.0 + 2.0, 7.0 + 3.0) = 10.0
    assert start_time == pytest.approx(10.0)
    assert is_critical is False


def test_get_earliest_start_time_critical(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """Critical 제약 조건 테스트"""
    constraints = nx.DiGraph()
    pred = sample_subtask_factory("Pred")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )
    completed = [CompletedEntry(pred, schedule_start_time=0.0, schedule_end_time=10.0)]
    node = create_test_node(10.0, completed, [succ], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "COMPLETED"
    assert start_time is not None
    assert start_time == pytest.approx(15.0)
    assert is_critical is True


def test_get_earliest_start_time_critical_conflict(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """Critical 시간 충돌 시 테스트 (Assert 수정)"""
    constraints = nx.DiGraph()
    pred1 = sample_subtask_factory("Pred1")
    pred2 = sample_subtask_factory("Pred2")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred1.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )  # 예상 시작: 15.0
    constraints.add_edge(
        pred2.name, succ.name, info={"Interval": 7.0, "IsCritical": True}
    )  # 예상 시작: 17.0 -> 충돌!
    completed = [
        CompletedEntry(pred1, schedule_start_time=0.0, schedule_end_time=10.0),
        CompletedEntry(pred2, schedule_start_time=0.0, schedule_end_time=10.0),
    ]
    node = create_test_node(10.0, completed, [succ], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "CONFLICT"  # FAILED_PREDECESSOR 제거
    assert start_time is None
    assert is_critical is True  # src 코드 로직 반영 (True 반환)


def test_get_earliest_start_time_mixed_constraints(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """Critical과 Non-critical 혼합 시 테스트 (Critical 우선)"""
    constraints = nx.DiGraph()
    pred_crit = sample_subtask_factory("PredCrit")
    pred_non = sample_subtask_factory("PredNon")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred_crit.name, succ.name, info={"Interval": 10.0, "IsCritical": True}
    )  # 예상 시작: 20.0
    constraints.add_edge(
        pred_non.name, succ.name, info={"Interval": 5.0, "IsCritical": False}
    )  # 예상 시작: 15.0
    completed = [
        CompletedEntry(pred_crit, schedule_start_time=0.0, schedule_end_time=10.0),
        CompletedEntry(pred_non, schedule_start_time=0.0, schedule_end_time=10.0),
    ]
    node = create_test_node(10.0, completed, [succ], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "COMPLETED"
    assert start_time is not None
    assert start_time == pytest.approx(20.0)
    assert is_critical is True


def test_get_earliest_start_time_mixed_conflict(
    constraint_handler, sample_subtask_factory, create_test_node
):
    """Critical과 Non-critical 혼합 시 충돌 테스트 (Assert 수정)"""
    constraints = nx.DiGraph()
    pred_crit = sample_subtask_factory("PredCrit")
    pred_non = sample_subtask_factory("PredNon")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred_crit.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )  # 예상 시작: 15.0
    constraints.add_edge(
        pred_non.name, succ.name, info={"Interval": 10.0, "IsCritical": False}
    )  # 예상 시작: 20.0 -> 충돌!
    completed = [
        CompletedEntry(pred_crit, schedule_start_time=0.0, schedule_end_time=10.0),
        CompletedEntry(pred_non, schedule_start_time=0.0, schedule_end_time=10.0),
    ]
    node = create_test_node(10.0, completed, [succ], constraints)
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )
    assert status == "CONFLICT"  # FAILED_PREDECESSOR 제거
    assert start_time is None
    assert is_critical is True  # src 코드 로직 반영


def test_get_earliest_start_time_predecessor_missing_status(
    constraint_handler, sample_subtask_factory, create_test_node, caplog
):
    """선행 작업 CompletedEntry에 execution_status 없을 때 성공 가정 테스트"""
    constraints = nx.DiGraph()
    pred_sub = sample_subtask_factory("Pred")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred_sub.name, succ.name, info={"Interval": 2.0, "IsCritical": False}
    )
    # execution_status 인자 없이 CompletedEntry 생성 (기본값 None 또는 True 가정)
    completed_entry_no_status = CompletedEntry(
        pred_sub, schedule_start_time=0.0, schedule_end_time=5.0
    )
    # 명시적으로 삭제하여 속성 부재 확인
    if hasattr(completed_entry_no_status, "execution_status"):
        delattr(completed_entry_no_status, "execution_status")

    node = create_test_node(5.0, [completed_entry_no_status], [succ], constraints)

    caplog.set_level(logging.WARNING)  # 경고 로그 캡처
    start_time, is_critical, status = constraint_handler.get_earliest_start_time(
        node, succ
    )

    # pred 완료(5.0) + interval(2.0) = 7.0
    assert start_time == pytest.approx(7.0)
    assert is_critical is False
    assert status == "COMPLETED"  # 성공으로 간주
    # 경고 로그 확인
    assert (
        f"Predecessor '{pred_sub.name}' completed but lacks 'execution_status' attribute"
        in caplog.text
    )


# --- get_feasible_candidates 테스트 (분리된 케이스) ---


@patch.object(ConstraintHandler, "_assign_deadlines")
def test_get_feasible_candidates_only_feasible(
    mock_assign,
    constraint_handler,
    mock_action_handler,
    sample_subtask_factory,
    create_test_node,
):
    """Feasible 후보만 있는 경우 테스트"""
    current_time = 10.0
    sub1 = sample_subtask_factory("F1")
    sub2 = sample_subtask_factory("F2_crit", crit=True)
    remaining = [sub1, sub2]
    node = create_test_node(current_time, [], remaining, nx.DiGraph())

    # get_earliest_start_time Mock 설정
    with patch.object(constraint_handler, "get_earliest_start_time") as mock_get_est:
        mock_get_est.side_effect = [
            (9.0, False, "COMPLETED"),  # F1: logical_start <= current_time
            (10.0, True, "COMPLETED"),  # F2_crit: logical_start <= current_time
        ]
        # action_handler mock은 기본적으로 성공/1.0초 반환

        feasible, not_yet = constraint_handler.get_feasible_candidates(node)

    assert len(feasible) == 2
    assert {c.subtask.name for c in feasible} == {"F1", "F2_crit"}
    assert len(not_yet) == 0
    assert mock_get_est.call_count == 2
    assert mock_action_handler.get_actions_info.call_count == 2  # 둘 다 COMPLETED 상태
    mock_assign.assert_called_once_with(feasible, not_yet, node)


@patch.object(ConstraintHandler, "_assign_deadlines")
def test_get_feasible_candidates_only_not_yet_time(
    mock_assign,
    constraint_handler,
    mock_action_handler,
    sample_subtask_factory,
    create_test_node,
):
    """Not-yet 후보만 있는 경우 (시간 미도래) 테스트"""
    current_time = 10.0
    sub1 = sample_subtask_factory("NY1")
    sub2 = sample_subtask_factory("NY2_crit", crit=True)
    remaining = [sub1, sub2]
    node = create_test_node(current_time, [], remaining, nx.DiGraph())

    with patch.object(constraint_handler, "get_earliest_start_time") as mock_get_est:
        mock_get_est.side_effect = [
            (12.0, False, "COMPLETED"),  # NY1: logical_start > current_time
            (11.0, True, "COMPLETED"),  # NY2_crit: logical_start > current_time
        ]

        feasible, not_yet = constraint_handler.get_feasible_candidates(node)

    assert len(feasible) == 0
    assert len(not_yet) == 2
    assert {c.subtask.name for c in not_yet} == {"NY1", "NY2_crit"}
    assert mock_get_est.call_count == 2
    assert mock_action_handler.get_actions_info.call_count == 2  # 둘 다 COMPLETED 상태
    mock_assign.assert_called_once_with(feasible, not_yet, node)


@patch.object(ConstraintHandler, "_assign_deadlines")
def test_get_feasible_candidates_only_not_yet_ready(
    mock_assign,
    constraint_handler,
    mock_action_handler,
    sample_subtask_factory,
    create_test_node,
):
    """Not-yet 후보만 있는 경우 (선행 미완료) 테스트"""
    current_time = 10.0
    sub1 = sample_subtask_factory("NR1")
    sub2 = sample_subtask_factory("NR2")
    remaining = [sub1, sub2]
    node = create_test_node(current_time, [], remaining, nx.DiGraph())

    with patch.object(constraint_handler, "get_earliest_start_time") as mock_get_est:
        mock_get_est.side_effect = [
            (None, False, "NOT_READY"),
            (None, False, "NOT_READY"),
        ]

        feasible, not_yet = constraint_handler.get_feasible_candidates(node)

    assert len(feasible) == 0
    assert len(not_yet) == 2
    assert {c.subtask.name for c in not_yet} == {"NR1", "NR2"}
    # NOT_READY 상태의 후보는 earliest_start_time이 None이어야 함
    assert not_yet[0].earliest_start_time is None
    assert not_yet[1].earliest_start_time is None
    assert mock_get_est.call_count == 2
    assert (
        mock_action_handler.get_actions_info.call_count == 0
    )  # NOT_READY는 action_info 호출 안함
    mock_assign.assert_called_once_with(feasible, not_yet, node)


@patch.object(ConstraintHandler, "_assign_deadlines")
def test_get_feasible_candidates_only_skipped(
    mock_assign,
    constraint_handler,
    mock_action_handler,
    sample_subtask_factory,
    create_test_node,
):
    """Skipped 후보만 있는 경우 (선행 실패/충돌) 테스트"""
    current_time = 10.0
    sub1 = sample_subtask_factory("FailPred")
    sub2 = sample_subtask_factory("Conflict")
    remaining = [sub1, sub2]
    node = create_test_node(current_time, [], remaining, nx.DiGraph())

    with patch.object(constraint_handler, "get_earliest_start_time") as mock_get_est:
        mock_get_est.side_effect = [
            (None, False, "FAILED_PREDECESSOR"),
            (None, True, "CONFLICT"),
        ]

        feasible, not_yet = constraint_handler.get_feasible_candidates(node)

    assert len(feasible) == 0
    assert len(not_yet) == 0  # 스킵된 후보는 not_yet에도 포함되지 않음
    assert mock_get_est.call_count == 2
    assert (
        mock_action_handler.get_actions_info.call_count == 0
    )  # 스킵된 후보는 action_info 호출 안함
    mock_assign.assert_called_once_with(feasible, not_yet, node)


@patch.object(ConstraintHandler, "_assign_deadlines")
def test_get_feasible_candidates_mixed(
    mock_assign,
    constraint_handler,
    mock_action_handler,
    sample_subtask_factory,
    create_test_node,
):
    """다양한 상태의 후보가 섞여 있는 경우 테스트"""
    current_time = 10.0
    sub_f1 = sample_subtask_factory("Feasible1")
    sub_ny1 = sample_subtask_factory("NotYetTime")
    sub_nr1 = sample_subtask_factory("NotReady")
    sub_skip1 = sample_subtask_factory("SkippedFail")
    remaining = [sub_f1, sub_ny1, sub_nr1, sub_skip1]
    node = create_test_node(current_time, [], remaining, nx.DiGraph())

    # Mock 설정 딕셔너리 사용
    est_results = {
        "Feasible1": (9.0, False, "COMPLETED"),
        "NotYetTime": (12.0, False, "COMPLETED"),
        "NotReady": (None, False, "NOT_READY"),
        "SkippedFail": (None, False, "FAILED_PREDECESSOR"),
    }

    def est_side_effect(node, sub):
        return est_results.get(sub.name, (None, False, "UNKNOWN"))

    with patch.object(
        constraint_handler, "get_earliest_start_time", side_effect=est_side_effect
    ) as mock_get_est:
        # action_handler는 기본 mock 사용 (성공/1.0초)
        feasible, not_yet = constraint_handler.get_feasible_candidates(node)

    assert len(feasible) == 1
    assert feasible[0].subtask.name == "Feasible1"
    assert len(not_yet) == 2
    assert {c.subtask.name for c in not_yet} == {"NotYetTime", "NotReady"}
    assert mock_get_est.call_count == 4
    assert (
        mock_action_handler.get_actions_info.call_count == 2
    )  # Feasible1, NotYetTime만 호출
    mock_assign.assert_called_once()
    call_args, _ = mock_assign.call_args
    assert len(call_args[0]) == 1  # feasible
    assert len(call_args[1]) == 2  # not_yet
    assert call_args[2] is node


# --- _assign_deadlines 테스트 (반환값 처리 수정 및 node 인자 추가) ---


def test_assign_deadlines_no_crit(constraint_handler, sample_subtask_factory):
    """Not-yet에 critical 없을 때 무한대 deadline 할당 테스트"""
    # Candidate 생성 시 불필요한 est, adjusted 인자 제거
    feasible = [
        Candidate(sample_subtask_factory("F1"), False, 5.0),
        Candidate(sample_subtask_factory("F2"), False, 7.0),
    ]
    not_yet = [Candidate(sample_subtask_factory("NY1"), False, 10.0)]
    # 테스트용 Mock 노드 전달
    mock_node = MagicMock(spec=SimulationNode)

    constraint_handler._assign_deadlines(
        feasible, not_yet, mock_node
    )  # 반환값 받지 않음, node 전달

    # feasible 리스트의 Candidate 객체 직접 확인
    assert feasible[0].deadline.due_date == float("inf")
    assert feasible[1].deadline.due_date == float("inf")


def test_assign_deadlines_with_crit(constraint_handler, sample_subtask_factory):
    """Not-yet에 critical 있을 때 deadline 할당 테스트"""
    feasible = [Candidate(sample_subtask_factory("F1"), False, 5.0)]
    # Not-yet 후보들의 earliest_start_time 사용
    not_yet = [
        Candidate(sample_subtask_factory("NY_NonCrit"), False, 15.0),
        Candidate(sample_subtask_factory("NY_Crit2"), True, 20.0),  # EST = 20.0
        Candidate(
            sample_subtask_factory("NY_Crit1"), True, 18.0
        ),  # EST = 18.0 (이것이 다음 critical)
    ]
    mock_node = MagicMock(spec=SimulationNode)

    constraint_handler._assign_deadlines(
        feasible, not_yet, mock_node
    )  # 반환값 받지 않음, node 전달

    # feasible 리스트의 Candidate 객체 직접 확인
    assert abs(feasible[0].deadline.due_date - 18.0) < EPSILON  # NY_Crit1의 EST
    assert feasible[0].deadline.subtask_name == "NY_Crit1"
