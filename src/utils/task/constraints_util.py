import networkx as nx

from core.dataclass import CompletedEntry
from scheduler.constraint_handler import ConstraintHandler


def get_critical_start_info(
    subtask_name: str,
    completed: list[CompletedEntry],
    constraints: nx.DiGraph,
    constraint_handler: ConstraintHandler,
) -> tuple[str, float]:
    """
    subtask_name에 inbound로 연결된 critical slots 중 interval이 가장 큰 것 찾기.
    그리고 그 slot의 related_subtask_name과 그 subtask의 end_time을 반환.
    """
    constraints_start_names = constraint_handler.get_time_slots(
        subtask_name, constraints, direction="in"
    )
    critical_slots = [slot for slot in constraints_start_names if slot.is_critical]
    if not critical_slots:
        raise ValueError(f"No critical slots found for {subtask_name}")

    max_critical = max(critical_slots, key=lambda x: x.interval)
    critical_start_sub_name = max_critical.related_subtask_name

    # completed_subtasks에서 critical_start_sub_name의 end_time 찾기
    critical_start_sub_end_time = next(
        (ce.end_time for ce in completed if ce.subtask.name == critical_start_sub_name),
        None,
    )
    if critical_start_sub_end_time is None:
        raise ValueError(
            f"Critical start sub '{critical_start_sub_name}' end time not found in completed list."
        )

    return critical_start_sub_name, critical_start_sub_end_time
