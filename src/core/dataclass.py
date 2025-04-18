from dataclasses import dataclass, field
from typing import List, NamedTuple, Optional, Tuple

import networkx as nx
from networkx import DiGraph

from core.task import Subtask


@dataclass
class ActionResult:
    action_full_name: str
    action_type: str
    time_used: float  # 누적 시간 (이 액션이 종료된 시점)
    action_duration: float  # 이 액션에 걸린 소요 시간
    scene_positions: dict[str, Tuple[float, float, float]]
    held_object: Optional[str] = None

    def __repr__(self):
        return f"({self.action_full_name}, {self.action_type}, {self.time_used}, {self.action_duration}, {self.held_object})"


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
                scene_positions=scene_positions,
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

    def get_actions(self) -> List[str]:
        """
        모든 액션 이름을 리스트로 반환한다.
        """
        return [res.action_full_name for res in self.results]


@dataclass
class CompletedEntry:
    """
    완료된 Subtask에 대해, (Subtask, start_time, end_time)을 함께 저장
    """

    subtask: Subtask
    start_time: float
    end_time: float

    def __repr__(self):
        return f"({self.subtask.name}, {self.start_time:.2f} ~ {self.end_time:.2f})"


@dataclass
class SchedulerState:
    """
    현재 스케쥴 상태를 저장하는 dataclass
    """

    subtask: Subtask
    completed_subtasks: List[CompletedEntry]
    remaining_subtasks: List[Subtask]
    constraints: nx.DiGraph
    current_time: float
    scene_positions: dict[str, Tuple[float, float, float]]
    held_object: Optional[str]


@dataclass(order=True)
class SimulationNode:
    """
    우선순위 큐에서 사용할 탐색 노드.
    """

    # 비교 순서: heuristic_cost -> depth -> tie_breaker 순으로 비교됨
    heuristic_cost: float
    depth: int
    tie_breaker: int  # cost, depth가 같을 때 비교하기 위한 필드
    # 비교에 포함되지 않도록 compare=False 설정 (NamedTuple에는 없던 기능)
    parent_node: Optional["SimulationNode"] = field(compare=False)
    state: SchedulerState = field(compare=False)


@dataclass
class TimeSlot:
    """
    Subtask 간의 제약 시간을 저장하는 데이터 클래스
    """

    interval: float
    is_critical: bool
    related_subtask_name: Optional[str]

    def __repr__(self):
        name_repr = (
            f"related={self.related_subtask_name}"
            if self.related_subtask_name
            else "None"
        )
        return f"({self.interval:.2f}, crit={self.is_critical}, {name_repr})"


@dataclass
class Deadline:
    """
    Subtask의 데드라인을 저장하는 데이터 클래스
    """

    due_date: float
    subtask_name: Optional[str]

    def __repr__(self):
        name_repr = f"subtask_name={self.subtask_name}" if self.subtask_name else "None"
        return f"(due_date={self.due_date:.2f}, {name_repr})"


@dataclass
class Candidate:
    """
    Subtask의 실행 가능 여부를 판단하기 위한 데이터 클래스
    """

    subtask: Subtask
    is_critical: bool
    adjusted_start_time: float
    logical_start_time: float
    deadline: Optional[Deadline] = field(
        default_factory=lambda: Deadline(float("inf"), None)
    )

    def __repr__(self):
        return (
            f"Candidate({self.subtask.name}; "
            f"AdjustedEST={self.adjusted_start_time:.2f}, "
            f"LogicalEST={self.logical_start_time:.2f}, "
            f"Deadline={self.deadline}, "
            f"IsCritical={self.is_critical})"
        )
