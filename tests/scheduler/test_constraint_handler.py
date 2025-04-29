import math
from unittest.mock import MagicMock, PropertyMock, call, patch

import networkx as nx
import pytest

# 필요한 데이터 클래스 임포트
from src.core.dataclass import (
    ActionResult,
    Candidate,
    CompletedEntry,
    Deadline,
    SchedulerState,
    SimulationNode,
    TimeSlot,
)
from src.core.task import Duration, Execution, Subtask
from src.scheduler.action_handler import ActionHandler

# 테스트 대상 모듈 임포트
from src.scheduler.constraint_handler import ConstraintHandler
from src.utils.config import EPSILON, LARGE_NUMBER


# Fixtures
@pytest.fixture
def mock_action_handler():
    """Mock ActionHandler."""
    mock = MagicMock(spec=ActionHandler)
    mock_nav_result = MagicMock(spec=ActionResult)
    mock_nav_result.cumulative_time = 1.0  # cumulative_time
    mock_nav_result.action_duration = 1.0  # action_duration
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
        if execution_status is not None:
            setattr(mock_sub, "execution_status", execution_status)
        else:
            if hasattr(mock_sub, "execution_status"):  # Ensure deletion is safe
                delattr(mock_sub, "execution_status")

        # name 속성을 읽을 수 있도록 설정
        type(mock_sub).name = PropertyMock(return_value=name)
        return mock_sub

    return _create_subtask


# Fixture 대신 일반 함수로 변경 (또는 fixture 그대로 두고 test 함수에서 파라미터로 받기)
def create_test_node_helper(current_time, completed, remaining, constraints):
    """테스트용 SimulationNode 생성 헬퍼"""
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
    return SimulationNode(0.0, 0, 0, None, state)


# 테스트 케이스
def test_get_earliest_start_time_no_predecessor(
    mock_action_handler, sample_subtask_factory
):
    """선행 작업 없는 경우 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    sub = sample_subtask_factory("TaskA")
    constraints.add_node(sub.name)
    # Helper 함수 직접 호출
    node = create_test_node_helper(0.0, [], [sub], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, sub)

    assert start_time == 0.0
    assert is_critical is False
    assert status == "COMPLETED"


def test_get_earliest_start_time_predecessor_not_done(
    mock_action_handler, sample_subtask_factory
):
    """선행 작업 미완료 시 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred = sample_subtask_factory("Pred")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 0, "IsCritical": False}
    )
    node = create_test_node_helper(
        0.0, [], [pred, succ], constraints
    )  # pred가 completed에 없음

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status == "NOT_READY"
    assert start_time is None


def test_get_earliest_start_time_predecessor_failed(
    mock_action_handler, sample_subtask_factory
):
    """선행 작업 실패 시 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred = sample_subtask_factory("Pred")
    pred.execution_status = False  # 선행 작업 실패 상태 설정
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 0, "IsCritical": False}
    )
    completed = [CompletedEntry(pred, 0.0, 5.0)]
    node = create_test_node_helper(5.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status == "FAILED_PREDECESSOR"
    assert start_time is None


def test_get_earliest_start_time_non_critical(
    mock_action_handler, sample_subtask_factory
):
    """Non-critical 제약 조건 테스트"""
    handler = ConstraintHandler(mock_action_handler)
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
    completed = [CompletedEntry(pred1, 0.0, 5.0), CompletedEntry(pred2, 1.0, 7.0)]
    node = create_test_node_helper(7.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status == "COMPLETED"
    assert start_time is not None
    assert start_time == pytest.approx(10.0)
    assert is_critical is False


def test_get_earliest_start_time_critical(mock_action_handler, sample_subtask_factory):
    """Critical 제약 조건 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    pred = sample_subtask_factory("Pred")
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 5.0, "IsCritical": True}
    )
    completed = [CompletedEntry(pred, 0.0, 10.0)]
    node = create_test_node_helper(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status == "COMPLETED"
    assert start_time is not None
    assert start_time == pytest.approx(15.0)
    assert is_critical is True


def test_get_earliest_start_time_critical_conflict(
    mock_action_handler, sample_subtask_factory
):
    """Critical 시간 충돌 시 테스트"""
    handler = ConstraintHandler(mock_action_handler)
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
    completed = [CompletedEntry(pred1, 0.0, 10.0), CompletedEntry(pred2, 0.0, 10.0)]
    node = create_test_node_helper(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status in ["FAILED_PREDECESSOR", "CONFLICT"]
    assert start_time is None


def test_get_earliest_start_time_mixed_constraints(
    mock_action_handler, sample_subtask_factory
):
    """Critical과 Non-critical 혼합 시 테스트 (Critical 우선)"""
    handler = ConstraintHandler(mock_action_handler)
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
        CompletedEntry(pred_crit, 0.0, 10.0),
        CompletedEntry(pred_non, 0.0, 10.0),
    ]
    node = create_test_node_helper(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status == "COMPLETED"
    assert start_time is not None
    assert start_time == pytest.approx(20.0)
    assert is_critical is True


def test_get_earliest_start_time_mixed_conflict(
    mock_action_handler, sample_subtask_factory
):
    """Critical과 Non-critical 혼합 시 충돌 테스트"""
    handler = ConstraintHandler(mock_action_handler)
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
        CompletedEntry(pred_crit, 0.0, 10.0),
        CompletedEntry(pred_non, 0.0, 10.0),
    ]
    node = create_test_node_helper(10.0, completed, [succ], constraints)

    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    assert status in ["FAILED_PREDECESSOR", "CONFLICT"]
    assert start_time is None


def test_get_earliest_start_time_predecessor_missing_status(
    mock_action_handler, sample_subtask_factory
):
    """선행 작업에 execution_status 없을 때 성공 가정 테스트 (src 로직 변경 반영)"""
    handler = ConstraintHandler(mock_action_handler)
    constraints = nx.DiGraph()
    # execution_status=None으로 설정하여 속성 부재 시뮬레이션
    pred = sample_subtask_factory("Pred", execution_status=None)
    succ = sample_subtask_factory("Succ")
    constraints.add_edge(
        pred.name, succ.name, info={"Interval": 2.0, "IsCritical": False}
    )
    completed = [CompletedEntry(pred, 0.0, 5.0)]  # pred는 완료됨
    node = create_test_node_helper(5.0, completed, [succ], constraints)

    # 경고 로그가 발생하는지 확인 (pytest caplog fixture 사용 가능)
    # 여기서는 반환값만 확인
    start_time, is_critical, status = handler.get_earliest_start_time(node, succ)

    # pred 완료(5.0) + interval(2.0) = 7.0
    assert abs(start_time - 7.0) < EPSILON
    assert is_critical is False
    assert status == "COMPLETED"  # 성공으로 간주되어야 함


# --- get_feasible_candidates 테스트 ---
@patch.object(ConstraintHandler, "get_earliest_start_time")
@patch.object(ConstraintHandler, "_assign_deadlines")
def test_get_feasible_candidates_logic(
    mock_assign_deadlines, mock_get_est, mock_action_handler, sample_subtask_factory
):
    """get_feasible_candidates의 분류 로직 테스트 (기존 테스트 확장)"""
    handler = ConstraintHandler(mock_action_handler)
    # Mock ActionHandler 설정
    mock_nav_result = MagicMock(spec=ActionResult)
    mock_nav_result.cumulative_time = 1.0
    mock_nav_result.action_duration = 1.0
    mock_action_handler.get_actions_info.return_value = mock_nav_result

    # 테스트용 서브태스크 (이름으로 구분)
    sub_feasible = sample_subtask_factory("FeasibleNonCrit")
    sub_feasible_crit = sample_subtask_factory(
        "FeasibleCritNow", crit=True
    )  # 지금 시작해야 함
    sub_notyet = sample_subtask_factory("NotYetNonCrit")
    sub_notyet_crit = sample_subtask_factory("NotYetCrit", crit=True)  # 나중에 시작
    sub_failed_pred = sample_subtask_factory("FailedPred")  # 선행 실패
    sub_not_done_pred = sample_subtask_factory("NotDonePred")  # 선행 미완료
    sub_crit_missed = sample_subtask_factory("CritMissed", crit=True)  # 시작 시간 놓침
    sub_nav_fail = sample_subtask_factory("NavFail")  # 네비게이션 시간 예측 실패

    remaining = [
        sub_feasible,
        sub_feasible_crit,
        sub_notyet,
        sub_notyet_crit,
        sub_failed_pred,
        sub_not_done_pred,
        sub_crit_missed,
        sub_nav_fail,
    ]

    current_time = 10.0
    # get_earliest_start_time 모의 반환값 설정 (logical_start_time, is_critical, status)
    # 네비게이션 시간은 1.0으로 가정 (adjusted = logical - 1.0)
    mock_get_est.side_effect = [
        (9.0, False, "COMPLETED"),  # adjusted=8.0 (feasible)
        (11.0, True, "COMPLETED"),  # adjusted=10.0 (feasible, critical now)
        (15.0, False, "COMPLETED"),  # adjusted=14.0 (not_yet)
        (13.0, True, "COMPLETED"),  # adjusted=12.0 (not_yet)
        (None, False, "FAILED"),  # skipped
        (None, False, None),  # skipped
        (9.0, True, "COMPLETED"),  # adjusted=8.0 (missed, skipped)
        (12.0, False, "COMPLETED"),  # adjusted 계산 중 실패 예상 (skipped)
    ]

    # NavFail 시나리오를 위해 action_handler mock 재설정
    def action_info_side_effect(node, actions):
        sub_name = actions[0].split()[-1]  # 액션에서 서브태스크 이름 추출 가정
        if sub_name == "NavFail":
            return None  # NavFail일 때 None 반환
        else:
            mock_res = MagicMock(spec=ActionResult)
            mock_res.cumulative_time = 1.0  # 기본 네비 시간
            mock_res.action_duration = 1.0  # action_duration 추가
            return mock_res

    mock_action_handler.get_actions_info.side_effect = action_info_side_effect

    # 테스트 노드 생성
    node = create_test_node_helper(current_time, [], remaining, nx.DiGraph())
    # get_feasible_candidates 호출
    feasible, not_yet = handler.get_feasible_candidates(node)

    # 결과 검증
    feasible_names = {c.subtask.name for c in feasible}
    not_yet_names = {c.subtask.name for c in not_yet}

    print(f"Feasible: {feasible_names}")  # 디버깅용 출력
    print(f"Not Yet: {not_yet_names}")  # 디버깅용 출력

    assert len(feasible) == 2
    assert "FeasibleNonCrit" in feasible_names
    assert "FeasibleCritNow" in feasible_names

    assert len(not_yet) == 2
    assert "NotYetNonCrit" in not_yet_names
    assert "NotYetCrit" in not_yet_names

    # 제외된 후보들 확인
    skipped_names = {"FailedPred", "NotDonePred", "CritMissed", "NavFail"}
    all_returned_names = feasible_names.union(not_yet_names)
    assert skipped_names.isdisjoint(all_returned_names)

    # get_earliest_start_time 호출 횟수 확인 (실패/미완료 후보 포함)
    assert mock_get_est.call_count == len(remaining)
    # action_handler 호출 횟수 확인 (실패/미완료 제외한 후보 수)
    expected_action_calls = len(remaining) - 2  # FailedPred, NotDonePred 제외
    assert mock_action_handler.get_actions_info.call_count == expected_action_calls

    # _assign_deadlines 호출 확인
    mock_assign_deadlines.assert_called_once()
    # 첫번째 인자 (feasible 리스트), 두번째 인자 (not_yet 리스트) 확인
    call_args, _ = mock_assign_deadlines.call_args
    assert len(call_args[0]) == 2
    assert len(call_args[1]) == 2
    assert call_args[2] == node  # node 객체 전달 확인

    # feasible 후보는 earliest_start_time이 float이어야 함
    assert isinstance(feasible[0].earliest_start_time, float)
    assert feasible[0].earliest_start_time <= node.state.current_time + EPSILON
    # not_yet 후보는 float 이거나 None 일 수 있음
    assert isinstance(not_yet[0].earliest_start_time, float)
    assert not_yet[0].earliest_start_time > node.state.current_time + EPSILON
    # not_ready 후보는 earliest_start_time이 None 이어야 함 (Candidate 생성 로직 확인)
    assert not_yet[1].earliest_start_time is None


# --- _assign_deadlines 테스트 ---
def test_assign_deadlines_no_crit(mock_action_handler, sample_subtask_factory):
    """Not-yet에 critical 없을 때 무한대 deadline 할당 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    feasible = [
        Candidate(sample_subtask_factory("F1"), False, 5.0, 5.0),
        Candidate(sample_subtask_factory("F2"), False, 7.0, 7.0),
    ]
    not_yet = [Candidate(sample_subtask_factory("NY1"), False, 10.0, 10.0)]

    result = handler._assign_deadlines(feasible, not_yet)

    assert result[0].deadline.due_date == float("inf")
    assert result[1].deadline.due_date == float("inf")


def test_assign_deadlines_with_crit(mock_action_handler, sample_subtask_factory):
    """Not-yet에 critical 있을 때 deadline 할당 테스트"""
    handler = ConstraintHandler(mock_action_handler)
    feasible = [Candidate(sample_subtask_factory("F1"), False, 5.0, 5.0)]
    # adjusted_start_time 기준 정렬 확인 위해 순서 섞음
    not_yet = [
        Candidate(sample_subtask_factory("NY_NonCrit"), False, 15.0, 15.0),
        Candidate(sample_subtask_factory("NY_Crit2"), True, 20.0, 21.0),  # Adjusted=20
        Candidate(sample_subtask_factory("NY_Crit1"), True, 18.0, 19.0),
    ]  # Adjusted=18 (이것이 다음 critical)

    result = handler._assign_deadlines(feasible, not_yet)

    assert (
        abs(result[0].deadline.due_date - 18.0) < EPSILON
    )  # NY_Crit1의 adjusted_start_time
    assert result[0].deadline.subtask_name == "NY_Crit1"


# get_time_slots 테스트는 비교적 간단하여 생략 가능 또는 추가
