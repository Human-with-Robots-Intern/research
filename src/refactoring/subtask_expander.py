# scheduler/subtask_expander.py
import copy
from typing import Optional

from core.subtask import Subtask
from scheduler.dataclass import (
    Candidate,
    CompletedEntry,
    SchedulerState,
    SimulationNode,
)
from utils.logger_util import create_module_logger
from utils.task.task_util import (
    make_early_subtask,
    make_monitoring_subtask,
    make_remain_subtask,
    make_wait_subtask,
)

log = create_module_logger(__name__)


class SubtaskExpander:
    """
    Creates child states for subtask expansions:
      - monitoring subtask => (early, monitor, remain)
      - normal subtask
      - wait subtask
    """

    def expand_subtask_with_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        nav_time: float,
        tie_breaker: int,
    ) -> Optional[SimulationNode]:
        """
        Time-critical => split into early, monitor, remain
        """
        state = curr_node.state
        original_name = candidate.subtask.name
        start_time = state.current_time
        total_dur = candidate.subtask.duration.interval + nav_time

        # 예시로 70% 시점에 모니터링
        early_dur = total_dur * 0.7
        remain_dur = total_dur - early_dur
        if early_dur < 0:
            early_dur = 0
        if remain_dur < 0:
            remain_dur = 0

        # 생성
        early_sub = make_early_subtask(candidate.subtask, early_dur)
        mon_sub = make_monitoring_subtask(original_name)
        remain_sub = make_remain_subtask(candidate.subtask, remain_dur)

        new_constraints = copy.deepcopy(state.constraints)
        # 기존 old_name 노드 제거
        if new_constraints.has_node(original_name):
            in_edges = list(new_constraints.in_edges(original_name, data=True))
            out_edges = list(new_constraints.out_edges(original_name, data=True))
            new_constraints.remove_node(original_name)
        else:
            in_edges, out_edges = [], []

        for pred, _, edata in in_edges:
            new_constraints.add_edge(pred, early_sub.name, info=edata["info"])
        for _, succ, edata in out_edges:
            new_constraints.add_edge(remain_sub.name, succ, info=edata["info"])

        new_constraints.add_node(early_sub.name)
        new_constraints.add_node(mon_sub.name)
        new_constraints.add_node(remain_sub.name)

        new_constraints.add_edge(
            early_sub.name, mon_sub.name, info={"Interval": 0, "IsCritical": True}
        )
        new_constraints.add_edge(
            mon_sub.name, remain_sub.name, info={"Interval": 0, "IsCritical": False}
        )

        new_remaining = [r for r in state.remaining_subtasks if r.name != original_name]
        new_remaining.extend([mon_sub, remain_sub])

        # early_sub 완료 시각
        end_early = (
            start_time + nav_time
        )  # + early_dur를 어떻게 배분할지는 설계에 따라 조정
        new_completed = state.completed_subtasks + [
            CompletedEntry(subtask=early_sub, start_time=start_time, end_time=end_early)
        ]
        new_state = SchedulerState(
            subtask=early_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=new_constraints,
            current_time=end_early,
            agent_location=state.agent_location,  # nav_manager에서 업데이트해도 됨
        )
        new_node = SimulationNode(
            heuristic_cost=curr_node.heuristic_cost,
            depth=curr_node.depth + 1,
            tie_breaker=tie_breaker,
            parent_node=curr_node,
            state=new_state,
        )
        return new_node

    def expand_subtask_wo_monitoring(
        self,
        curr_node: SimulationNode,
        candidate: Candidate,
        nav_time: float,
        tie_breaker: int,
    ) -> Optional[SimulationNode]:
        """
        Normal subtask => just run it
        """
        state = curr_node.state
        start_time = state.current_time
        total_time = candidate.subtask.duration.interval + nav_time
        end_time = start_time + total_time

        # 데드라인 검사
        if candidate.deadline.due_date < end_time:
            log.debug(f"Deadline missed for {candidate.subtask.name} => discard")
            return None

        # subtask 복제 후 완료
        sub_copy = copy.deepcopy(candidate.subtask)
        sub_copy.duration.interval = total_time

        new_completed = state.completed_subtasks + [
            CompletedEntry(subtask=sub_copy, start_time=start_time, end_time=end_time)
        ]
        new_remaining = [
            r for r in state.remaining_subtasks if r.name != candidate.subtask.name
        ]

        new_state = SchedulerState(
            subtask=sub_copy,
            completed_subtasks=new_completed,
            remaining_subtasks=new_remaining,
            constraints=state.constraints,
            current_time=end_time,
            agent_location=state.agent_location,
        )
        return SimulationNode(
            heuristic_cost=curr_node.heuristic_cost,
            depth=curr_node.depth + 1,
            tie_breaker=tie_breaker,
            parent_node=curr_node,
            state=new_state,
        )

    def expand_wait_subtask(
        self, curr_node: SimulationNode, candidate: Candidate, tie_breaker: int
    ) -> SimulationNode:
        """
        Insert a Wait subtask until earliest_start_time
        """
        state = curr_node.state
        wait_time = max(0.0, candidate.earliest_start_time - state.current_time)

        wait_sub = make_wait_subtask(candidate.subtask.name, wait_time)
        new_completed = state.completed_subtasks + [
            CompletedEntry(
                subtask=wait_sub,
                start_time=state.current_time,
                end_time=state.current_time + wait_time,
            )
        ]
        new_state = SchedulerState(
            subtask=wait_sub,
            completed_subtasks=new_completed,
            remaining_subtasks=state.remaining_subtasks,
            constraints=state.constraints,
            current_time=state.current_time + wait_time,
            agent_location=state.agent_location,
        )
        return SimulationNode(
            heuristic_cost=curr_node.heuristic_cost,
            depth=curr_node.depth + 1,
            tie_breaker=tie_breaker,
            parent_node=curr_node,
            state=new_state,
        )
