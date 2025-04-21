from typing import Optional

import pytest
from networkx import DiGraph

# 테스트 대상 모듈 임포트
from core.dataclass import (
    ActionResult,
    ActionSimulationLog,
    Candidate,
    CompletedEntry,
    Deadline,
    SchedulerState,
    SimulationNode,
    TimeSlot,
)
from core.task import Duration, Execution, Subtask  # 필요한 다른 클래스 임포트


# Fixtures (필요시 테스트 데이터 생성)
@pytest.fixture
def sample_subtask():
    return Subtask(
        task_name="TestTask",
        name="TestSub",
        repetition=1,
        type="Interaction",
        execution=Execution(objects={"obj1": 1}, primitive_actions=["ACTION obj1"]),
        duration=Duration(type="Controllable", interval=10.0),
    )


@pytest.fixture
def sample_deadline():
    return Deadline(due_date=100.0, subtask_name="NextCriticalTask")


# 테스트 케이스
def test_candidate_creation(sample_deadline):
    """Candidate 객체 생성 및 기본 필드 확인 테스트"""
    # Provide required args for Subtask
    mock_execution = Execution(objects={}, primitive_actions=["ACTION"])
    mock_duration = Duration(type="Controllable", interval=1.0)
    mock_subtask = Subtask(
        "Task", "Sub", 1, "Type", execution=mock_execution, duration=mock_duration
    )

    candidate = Candidate(
        subtask=mock_subtask,
        is_critical=False,
        adjusted_start_time=0.0,
        logical_start_time=0.0,
        deadline=sample_deadline,  # Use provided fixture or default
    )
    assert candidate.subtask.name == "Sub"
    assert not candidate.is_critical


def test_scheduler_state_creation(sample_subtask):
    """SchedulerState 객체 생성 테스트"""
    completed = [CompletedEntry(sample_subtask, 0.0, 10.0)]
    state = SchedulerState(
        subtask=sample_subtask,
        completed_subtasks=completed,
        remaining_subtasks=[],
        constraints=DiGraph(),
        current_time=10.0,
        scene_positions={"agent": (0, 0, 0)},
        held_object=None,
    )
    assert state.current_time == 10.0
    assert len(state.completed_subtasks) == 1


# 다른 데이터 클래스에 대한 테스트 추가...
# 예: SimulationNode, TimeSlot, ActionResult 등
