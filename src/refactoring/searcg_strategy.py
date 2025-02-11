# scheduler/search_strategy.py
import itertools
from queue import PriorityQueue
from typing import List, Optional

from scheduler.constraint_handler import ConstraintHandler
from scheduler.cost_manager import HeuristicManager, NavigationManager
from scheduler.dataclass import Candidate, SchedulerState, SimulationNode
from scheduler.subtask_expander import SubtaskExpander
from utils.logger_util import create_module_logger

log = create_module_logger(__name__)


class BeamSearchStrategy:
    def __init__(
        self,
        constraint_handler: ConstraintHandler,
        cost_calculator: HeuristicManager,
        nav_manager: NavigationManager,
        beam_width: int,
        simulation_depth: int,
    ):
        self.constraint_handler = constraint_handler
        self.cost_calculator = cost_calculator
        self.nav_manager = nav_manager
        self.expander = SubtaskExpander()
        self.beam_width = beam_width
        self.simulation_depth = simulation_depth

        self._counter = itertools.count()

    def search(self, init_node: SimulationNode) -> Optional[SimulationNode]:
        queue = PriorityQueue()
        queue.put((init_node.heuristic_cost, next(self._counter), init_node))
        best_solutions: List[SimulationNode] = []

        while not queue.empty():
            _, _, curr_node = queue.get()
            state = curr_node.state

            if not state.remaining_subtasks or curr_node.depth >= self.simulation_depth:
                best_solutions.append(curr_node)
                continue

            feasible, not_yet = self.constraint_handler.get_feasible_candidates(state)
            if not feasible and not not_yet:
                # No expansions => dead end
                continue

            expanded_nodes: List[SimulationNode] = []

            # expand feasible
            for cand in feasible:
                nav_time, new_loc = self.nav_manager.compute_total_navigation_time(
                    curr_node, cand.subtask
                )
                # check if critical => monitoring or normal
                # (여기서는 simple 조건으로 구현)
                if (
                    cand.deadline.subtask_name
                    and not curr_node.state.subtask.decomposed
                    and cand.is_critical
                ):
                    child = self.expander.expand_subtask_with_monitoring(
                        curr_node, cand, nav_time, tie_breaker=next(self._counter)
                    )
                else:
                    child = self.expander.expand_subtask_wo_monitoring(
                        curr_node, cand, nav_time, tie_breaker=next(self._counter)
                    )
                if child:
                    # agent_location 업데이트
                    # (필요하다면 child.state.agent_location = new_loc)
                    cost = self.cost_calculator.calc_heuristic(
                        curr_node, cand, nav_time
                    )
                    child = self._replace_cost(child, curr_node.heuristic_cost + cost)
                    expanded_nodes.append(child)

            # expand wait if no feasible
            if not feasible and not_yet:
                earliest = sorted(not_yet, key=lambda c: c.earliest_start_time)[0]
                child = self.expander.expand_wait_subtask(
                    curr_node, earliest, tie_breaker=next(self._counter)
                )
                cost = self.cost_calculator.calc_heuristic(curr_node, earliest, 0.0)
                child = self._replace_cost(child, curr_node.heuristic_cost + cost)
                expanded_nodes.append(child)

            # local beam pruning
            expanded_nodes.sort(key=lambda n: n.heuristic_cost)
            for e_node in expanded_nodes[: self.beam_width]:
                queue.put((e_node.heuristic_cost, next(self._counter), e_node))

        if not best_solutions:
            return None
        best_solutions.sort(key=lambda n: n.heuristic_cost)
        return best_solutions[0]

    def _replace_cost(self, node: SimulationNode, new_cost: float) -> SimulationNode:
        return SimulationNode(
            heuristic_cost=new_cost,
            depth=node.depth,
            tie_breaker=node.tie_breaker,
            parent_node=node.parent_node,
            state=node.state,
        )
