from dataclasses import dataclass
from typing import List, NamedTuple, Optional

from networkx import DiGraph

from core.task import Subtask

# ! 대부분 모두 NamedTuple일 필요가 있는지 확인 필요


class CompletedEntry(NamedTuple):
    """
    완료된 Subtask에 대해, (Subtask, start_time, end_time)을 함께 저장
    """

    subtask: Subtask
    start_time: float
    end_time: float

    def __repr__(self):
        return f"({self.subtask.name}, {self.start_time} ~ {self.end_time})"


class SchedulerState(NamedTuple):
    """
    스케쥴 정보를 담는 NamedTuple
    """

    # 현재 subtask
    subtask: Subtask
    # 수행된 subtask들 (현재 subtask 포함)
    completed_subtasks: List[CompletedEntry]
    # 남은 subtask들
    remaining_subtasks: List[Subtask]
    # 현재 constraint
    constraints: DiGraph
    # 현재 절대 시간 및 위치
    current_time: float
    # 현재 agent 위치
    agent_location: str


class SimulationNode(NamedTuple):
    """
    우선순위 큐에서 사용할 탐색 노드.
    - heuristic_cost: 지금까지 누적된 비용 (높을수록 우선)
    - depth: 현재 탐색 깊이
    - tie_breaker: 우선순위가 같을 때 순서 결정용
    - state: 실제 스케줄 상태 (SchedulerState)
    """

    heuristic_cost: float
    depth: int
    tie_breaker: int
    parent_node: Optional["SimulationNode"]
    state: SchedulerState


class TimeSlot(NamedTuple):
    """
    Subtask 간의 제약 시간을 저장하는 NamedTuple
    """

    # 해당 subtask에서 in/out하는 제약 시간
    interval: int
    # 해당 subtask에서 in/out하는 제약 critical한지 여부
    is_critical: bool
    # 해당 subtask에서 in/out하는 제약과 연결된 subtask 이름
    related_subtask_name: Optional[str]

    def __repr__(self):
        return f"({self.interval}, {self.is_critical}, {self.related_subtask_name},)"


@dataclass
class Deadline:
    """
    Subtask의 데드라인을 저장하는 NamedTuple
    """

    # 해당 subtask의 데드라인 시간
    due_date: float
    # 해당 subtask의 이름
    subtask_name: str

    def __repr__(self):
        return f"({self.subtask_name=}, {self.due_date=})"


@dataclass
class Candidate:
    """
    Subtask의 실행 가능 여부를 판단하기 위한 NamedTuple
    """

    subtask: Subtask
    # subtask이 critical인지 여부
    is_critical: bool
    # subtask의 시작 시간
    earliest_start_time: float
    # 고려할 데드라인
    deadline: Deadline = float("inf")

    def __repr__(self):
        return f"({self.subtask.name}; duration : {self.subtask.duration.interval}, earliest_start_time = {self.earliest_start_time}, deadline = {self.deadline}, is_critical = {self.is_critical})"
