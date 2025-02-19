from dataclasses import dataclass, field
from typing import List, NamedTuple, Optional, Tuple

from networkx import DiGraph

from core.task import Subtask


@dataclass
class ActionResult:
    action_full_name: str
    action_type: str
    time_used: float  # 누적 시간 (이 액션이 종료된 시점)
    action_duration: float  # 이 액션에 걸린 소요 시간
    agent_position: dict[str, Tuple[float, float, float]]
    held_object: Optional[str] = None


@dataclass
class ActionSimulationLog:
    results: list[ActionResult] = field(default_factory=list)

    def add_result(
        self,
        action_full_name: str,
        action_type: str,
        time_used: float,
        action_duration: float,
        scene_positions: dict[str, Tuple[float, float, float]],
        held_object: Optional[str] = None,
    ):
        self.results.append(
            ActionResult(
                action_full_name=action_full_name,
                action_type=action_type,
                time_used=time_used,
                action_duration=action_duration,
                agent_position=scene_positions,
                held_object=held_object,
            )
        )

    def total_navigate_duration(self) -> float:
        """
        action_type이 'NAVIGATE_TO'인 액션들만 골라서 action_duration의 합을 구한다.
        """
        total = 0.0
        for result in self.results:
            if result.action_type.upper() == "NAVIGATE_TO":
                total += result.action_duration
        return total

    def total_time_used(self) -> float:
        """
        전체 액션 중 가장 마지막 액션의 time_used(누적 시간)를 반환.
        없으면 0.0을 반환.
        """
        if not self.results:
            return 0.0
        # 마지막 ActionResult의 time_used가 전체 시뮬레이션 누적 시간
        return self.results[-1].time_used

    def filter_by_action_type(self, action_type: str) -> list[ActionResult]:
        """
        특정 action_type(대소문자 무관)에 해당하는 모든 ActionResult를 리스트로 반환.
        """
        atype_upper = action_type.upper()
        return [res for res in self.results if res.action_type.upper() == atype_upper]

    def count_actions(self, action_type: Optional[str] = None) -> int:
        """
        특정 action_type에 해당하는 액션의 개수를 세거나,
        action_type이 None이면 전체 액션 개수를 반환한다.
        """
        if action_type is None:
            return len(self.results)
        atype_upper = action_type.upper()
        return sum(1 for res in self.results if res.action_type.upper() == atype_upper)


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
    현재 스케쥴 상태를 저장하는 dataclass
    """

    # 현재 subtask
    subtask: Subtask
    # 수행된 subtask들 (현재 subtask 포함)
    completed_subtasks: List[CompletedEntry]
    # 남은 subtask들
    remaining_subtasks: List[Subtask]
    # 현재 constraint
    constraints: DiGraph
    # 현재 절대 시간
    current_time: float
    # 현재 agent, object들의 position
    scene_positions: dict[str, list[float, float, float]]
    # 현재 agent가 들고 있는 object
    held_object: Optional[str]
    # agent의 위치 (landmark)
    agent_location: str = None


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
    deadline: Deadline = (None, None)

    def __repr__(self):
        return f"({self.subtask.name}; duration : {self.subtask.duration.interval}, earliest_start_time = {self.earliest_start_time}, deadline = {self.deadline}, is_critical = {self.is_critical})"
