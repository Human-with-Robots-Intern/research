from typing import Optional

import pytest
from networkx import DiGraph

# 테스트 대상 모듈 임포트
from src.core.dataclass import (
    ActionResult,
    ActionSimulationLog,
    Candidate,
    CompletedEntry,
    SchedulerState,
    SchedulingDue,
    SimulationNode,
    TimeSlot,
)
from src.core.task import Duration, Execution, Subtask  # 경로 수정: src.core.task


# Fixtures (필요시 테스트 데이터 생성)
@pytest.fixture
def sample_subtask():
    # Duration과 Execution 객체 직접 생성
    duration = Duration(type="Controllable", interval=10.0)
    execution = Execution(objects={"obj1": 1}, primitive_actions=["ACTION obj1"])
    return Subtask(
        task_name="TestTask",
        name="TestSub",
        repetition=1,
        subtask_type="Interaction",  # type -> subtask_type 변경 가능성 고려 (Task 스키마 확인 필요)
        execution=execution,
        duration=duration,
    )


@pytest.fixture
def sample_scheduler_state(sample_subtask):
    # CompletedEntry 생성 시 subtask 객체 필요
    completed_entry = CompletedEntry(
        subtask=sample_subtask,
        schedule_start_time=0.0,
        schedule_end_time=10.0,
        sim_start_time=0.0,
        sim_end_time=10.0,
        execution_status=True,
    )
    constraints = DiGraph()
    constraints.add_node(sample_subtask.name)  # 그래프에 노드 추가
    return SchedulerState(
        subtask=sample_subtask,  # 현재 subtask 예시
        completed_entries=[
            completed_entry
        ],  # 필드 이름 확인: completed_subtasks -> completed_entries
        remaining_subtasks=[],
        constraints=constraints,  # 실제 DiGraph 객체 사용
        current_time=10.0,
        scene_positions={
            "agent": [0.0, 0.0, 0.0]
        },  # scene_positions 형식 확인 (list of float)
        held_object=None,
        agent_location="StartLocation",  # agent_location 필드 추가
    )


@pytest.fixture
def sample_deadline():
    return SchedulingDue(due_date=100.0, subtask_name="NextCriticalTask")


# 테스트 케이스
def test_candidate_creation(sample_subtask, sample_deadline):
    """Candidate 객체 생성 및 기본 필드 확인 테스트"""
    candidate = Candidate(
        subtask=sample_subtask,
        is_critical=False,
        earliest_start_time=0.0,  # 필드 이름 확인: adjusted_start_time -> earliest_start_time
        # logical_start_time 필드 존재 여부 확인 후 제거 또는 유지
        deadline=sample_deadline,
    )
    assert candidate.subtask.name == "TestSub"
    assert not candidate.is_critical
    assert candidate.earliest_start_time == 0.0
    assert candidate.scheduling_due.due_date == 100.0


def test_scheduler_state_creation(sample_subtask, sample_scheduler_state):
    """SchedulerState 객체 생성 테스트"""
    state = sample_scheduler_state  # fixture 사용
    assert state.current_time == 10.0
    assert len(state.completed_entries) == 1
    assert state.subtask == sample_subtask
    assert state.agent_location == "StartLocation"


# --- 추가된 테스트 케이스 ---


def test_simulation_node_creation(sample_scheduler_state):
    """SimulationNode 객체 생성 및 기본 필드 확인 테스트"""
    node = SimulationNode(
        heuristic_cost=15.5,
        depth=2,
        tie_breaker=10,
        parent_node=None,  # 루트 노드 가정
        state=sample_scheduler_state,
    )
    assert node.heuristic_cost == 15.5
    assert node.depth == 2
    assert node.tie_breaker == 10
    assert node.parent_node is None
    assert node.state == sample_scheduler_state


def test_time_slot_creation():
    """TimeSlot 객체 생성 및 기본 필드 확인 테스트"""
    ts = TimeSlot(interval=5.0, is_critical=True, related_subtask_name="PredTask")
    assert ts.interval == 5.0
    assert ts.is_critical is True
    assert ts.related_subtask_name == "PredTask"


def test_action_result_creation():
    """ActionResult 객체 생성 및 기본 필드 확인 테스트"""
    pos = {"agent": [0.0, 1.0, 0.0]}  # 값 형식을 list of float으로 통일
    ar = ActionResult(
        action_full_name="NAVIGATE_TO obj",
        action_type="NAVIGATE_TO",
        cumulative_time=5.5,  # 필드 이름 확인: time_used -> cumulative_time
        action_duration=1.5,
        scene_positions=pos,
        held_object="apple",
        success=True,
    )
    assert ar.action_full_name == "NAVIGATE_TO obj"
    assert ar.action_type == "NAVIGATE_TO"
    assert ar.cumulative_time == 5.5
    assert ar.action_duration == 1.5
    assert ar.scene_positions == pos
    assert ar.held_object == "apple"
    assert ar.success is True


def test_action_simulation_log_basic():
    """ActionSimulationLog 기본 기능 테스트 (추가, 시간 계산 등)"""
    log = ActionSimulationLog()
    pos1 = {"agent": [0.0, 1.0, 0.0]}
    pos2 = {"agent": [1.0, 1.0, 0.0]}
    # add_result 호출 시 필드 이름 확인
    log.add_result(
        action_full_name="NAVIGATE_TO A",
        action_type="NAVIGATE_TO",
        cumulative_time=1.5,
        action_duration=1.5,
        scene_positions=pos1,
        success=True,
    )
    log.add_result(
        action_full_name="INTERACT B",
        action_type="INTERACT",
        cumulative_time=2.0,
        action_duration=0.5,
        scene_positions=pos2,
        success=True,
    )
    log.add_result(
        action_full_name="NAVIGATE_TO C",
        action_type="NAVIGATE_TO",
        cumulative_time=4.0,
        action_duration=2.0,
        scene_positions=pos2,
        success=True,
    )

    assert len(log.results) == 3
    assert log.total_time_used() == 4.0
    assert log.total_navigate_duration() == pytest.approx(1.5 + 2.0)
    assert len(log.filter_by_action_type("NAVIGATE_TO")) == 2
    assert log.count_actions("INTERACT") == 1
    assert log.count_actions() == 3
    assert log.get_actions() == ["NAVIGATE_TO A", "INTERACT B", "NAVIGATE_TO C"]


def test_completed_entry_creation(sample_subtask):
    """CompletedEntry 객체 생성 및 기본 필드 확인 테스트"""
    # monitored_subtask는 __init__ 인자가 아님
    ce = CompletedEntry(
        subtask=sample_subtask,
        schedule_start_time=10.0,
        schedule_end_time=20.0,
        sim_start_time=11.0,
        sim_end_time=21.5,
        execution_status=True,
        # monitored_subtask=... # <<< 생성자에서 제거
    )
    # 생성 후 속성 설정
    monitor_data = {"updated_subtask_name": "task_a", "ground_truth_time": 12.0}
    ce.monitored_subtask = monitor_data  # <<< 속성 직접 설정

    assert ce.subtask == sample_subtask
    assert ce.schedule_start_time == 10.0
    assert ce.schedule_end_time == 20.0
    assert ce.sim_start_time == 11.0
    assert ce.sim_end_time == 21.5
    assert ce.execution_status is True
    assert ce.monitored_subtask == monitor_data
