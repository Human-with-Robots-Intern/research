from __future__ import annotations

from typing import Optional

from src.models.dataclass import Candidate, SchedulingDue
from src.utils.config import constants


def has_finite_due(due: Optional[SchedulingDue]) -> bool:
    """Return True when the due object carries a real deadline."""

    return due is not None and due.due_date is not None and due.due_date != float("inf")


def get_candidate_self_due(candidate: Candidate) -> Optional[SchedulingDue]:
    """Return the candidate's own logical deadline when it is a critical end task."""

    due_date = candidate.logical_interaction_start_time
    if not candidate.is_critical or due_date is None or due_date == float("inf"):
        return None
    return SchedulingDue(
        due_date=float(due_date),
        due_related_sub_name=candidate.subtask.name,
    )


def get_candidate_effective_due(candidate: Candidate) -> SchedulingDue:
    """Resolve the safety deadline as the tighter of global due and self due."""

    global_due = (
        candidate.scheduling_due if has_finite_due(candidate.scheduling_due) else None
    )
    self_due = get_candidate_self_due(candidate)

    if self_due and global_due:
        if self_due.due_date <= global_due.due_date + constants.EPSILON:
            return self_due
        return global_due
    if self_due:
        return self_due
    if global_due:
        return global_due
    return SchedulingDue(due_date=float("inf"), due_related_sub_name=None)
