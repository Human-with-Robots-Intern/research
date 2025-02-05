from typing import List, NamedTuple, Optional

from networkx import DiGraph

from core.task import Subtask


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
    state: SchedulerState


class TemporalConstraint(NamedTuple):
    # 해당 subtask에서 in/out하는 제약 시간
    interval: int
    # 해당 subtask에서 in/out하는 제약 critical한지 여부
    is_critical: bool
    # 해당 subtask에서 in/out하는 제약과 연결된 subtask 이름
    related_subtask_name: Optional[str]

    def __repr__(self):
        return f"({self.related_subtask_name}, {self.interval}, {self.is_critical}, )"


class Candidate(NamedTuple):

    subtask: Subtask
    # subtask의 시작 시간
    earliest_start: float
    # subtask이 critical인지 여부
    is_critical: bool

    def __repr__(self):
        return f"({self.subtask.name}, {self.earliest_start}, {self.is_critical})"
