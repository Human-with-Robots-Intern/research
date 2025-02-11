# scheduler/scheduler.py
from typing import Optional

from scheduler.dataclass import SchedulerState, SimulationNode
from scheduler.search_strategy import BeamSearchStrategy


class Scheduler:
    """
    High-level interface to get the 'next state' from the current state,
    using a provided search strategy (e.g., BeamSearch).
    """

    def __init__(self, search_strategy: BeamSearchStrategy):
        self.search_strategy = search_strategy

    def get_next_state(self, current_state: SchedulerState) -> Optional[SchedulerState]:
        init_node = SimulationNode(
            heuristic_cost=0.0,
            depth=0,
            tie_breaker=0,
            parent_node=None,
            state=current_state,
        )
        best_node = self.search_strategy.search(init_node)
        if not best_node:
            return None

        path = self._reconstruct_path(best_node)
        if len(path) < 2:
            # path[0] = init, no next step
            return None
        return path[1].state

    def _reconstruct_path(self, node: SimulationNode):
        chain = []
        curr = node
        while curr is not None:
            chain.append(curr)
            curr = curr.parent_node
        return list(reversed(chain))
