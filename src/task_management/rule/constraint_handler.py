from typing import Any, List, Optional, Tuple

import networkx as nx

from utils.util import create_module_logger

log = create_module_logger(module_name=__name__, is_file_handler=False)


class ConstraintHandler:
    """
    This class handles subtask constraints using a directed graph (DiGraph).
    Each edge in the graph stores constraint info in the format:
      {
        'info': {
          'Interval': int,
          'Urgency': bool
        }
      }
    """

    def __init__(self, constraints: nx.DiGraph):
        """
        Args:
            constraints (nx.DiGraph):
                A directed graph where each edge has 'info' dict containing
                'Interval' (int) and 'Urgency' (bool).
        """
        self.constraints = constraints

    def update_constraints(self, constraints: nx.DiGraph):
        self.constraints = constraints

    def validate_constraints(
        self,
        current_state: "Subtask",  # or a more precise type if you have one
        candidate_subtask: "Subtask",
    ) -> bool:
        """
        Checks if the candidate subtask satisfies all of its incoming constraints.

        1. Gathers subtasks from the current_state that serve as "predecessors"
           to the candidate_subtask in the constraint graph.
        2. Compares the number of these subtasks to the number of actual incoming
           constraints for candidate_subtask. If there's a mismatch, constraints
           aren't fully satisfied.
        3. Checks time_slot vs. Urgency constraints (e.g., if time_slot < 0 and
           the edge is urgent, it fails).

        Returns:
            bool: True if all constraints are satisfied, False otherwise.
        """
        # Gather the subtasks in the partial plan that are relevant predecessors
        # of candidate_subtask.
        constraint_subtasks = self._get_constraint_subtasks(
            current_state, candidate_subtask.name
        )
        # Gather all incoming edges/constraints for candidate_subtask
        constraints = self._get_incoming_constraints(candidate_subtask.name)

        # If the number of matched subtask predecessors doesn't match the number
        # of incoming edges, it means not all constraints are met yet.
        if len(constraint_subtasks) != len(constraints):
            return False

        # Check time slot validity for urgent constraints
        time_slots = self.get_time_slot_and_urgency(current_state, candidate_subtask)
        return all((slot >= 0) if is_urgent else True for slot, is_urgent in time_slots)

    def get_initial_subtasks(self, subtasks: List["Subtask"]) -> List["Subtask"]:
        """
        Finds subtasks that have no incoming edges (i.e., no prerequisites).

        Returns:
            List["Subtask"]: A list of subtasks that can be started immediately.
        """
        # Nodes with in_degree == 0 are those with no incoming edges
        initial_nodes = {
            node for node, in_degree in self.constraints.in_degree() if in_degree == 0
        }
        return [subtask for subtask in subtasks if subtask.name in initial_nodes]

    def get_expandable_subtasks(self, state: Any) -> List["Subtask"]:
        """
        Retrieves all subtasks that can be executed next given the current state
        and the constraint graph. A subtask is considered 'expandable' if all
        of its constraints are satisfied.

        Args:
            state (Any): The object holding the 'remaining_subtasks' and
                         'partial_plan' or other needed info.

        Returns:
            List["Subtask"]: List of subtasks that can be executed next.
        """
        return [
            subtask
            for subtask in state.remaining_subtasks
            if self.validate_constraints(state, subtask)
        ]

    def get_time_slot_and_urgency(
        self, current_state: Any, subtask: "Subtask"
    ) -> List[Tuple[int, bool]]:
        """
        Calculates the time slot and urgency for all constraints leading into a subtask.

        For example, if subtaskA -> subtaskB with interval=3, urgency=True,
        this method would return (3, True) for that constraint.

        Args:
            current_state (Any): Contains partial plan or any other scheduling info.
            subtask (Subtask): The subtask for which we want the (time_slot, urgency) info.

        Returns:
            List[Tuple[int, bool]]:
                A list of (time_slot, urgency) for each incoming constraint
                that has been satisfied by the current_state.
        """
        constraint_subtasks = self._get_constraint_subtasks(current_state, subtask.name)

        # If no constraints exist or none matched from the partial plan, return default
        if not constraint_subtasks:
            return [(0, False)]

        time_slots = []
        for predecessor_subtask in constraint_subtasks:
            info = self.constraints.get_edge_data(
                predecessor_subtask.name, subtask.name
            )
            if info is None:
                # This case shouldn't normally happen if the graph is consistent
                # but handle gracefully if there's no edge data
                time_slots.append((0, False))
                continue

            interval = info["info"]["Interval"]
            urgency = info["info"]["Urgency"]
            time_slots.append((interval, urgency))

        return time_slots

    def get_temporal_constraints(
        self, subtask_name: str, direction: str
    ) -> Tuple[Tuple[int, bool, Optional[str]], ...]:
        """
        Retrieves minimal (Interval, Urgency, neighbor_name) for incoming or
        outgoing edges to a subtask. If multiple edges exist, the minimal
        Interval is returned.

        Args:
            subtask_name (str): Name of the subtask of interest.
            direction (str): 'in' for incoming edges or 'out' for outgoing edges.

        Returns:
            Tuple[Tuple[int, bool, Optional[str]], ...]:
                A tuple of one or more (interval, urgency, neighbor_name).
                If no edges exist, returns ((0, False, None),).
        """

        def extract_constraints(
            edges: List[Tuple[Any, Any, dict]]
        ) -> Tuple[int, bool, Optional[str]]:
            """
            Returns the constraint with the minimal interval (Interval, Urgency, neighbor_name).
            If no edges exist, return default (0, False, None).
            """
            if not edges:
                log.debug(
                    f"No {direction} edges found for subtask {subtask_name}. Returning default (0, False, None)."
                )
                return (0, False, None)
            return min(
                (
                    (edge_data["info"]["Interval"], edge_data["info"]["Urgency"], v)
                    for _, v, edge_data in edges
                ),
                key=lambda x: x[0],
            )

        if direction == "out":
            edges = list(self.constraints.out_edges(subtask_name, data=True))
        elif direction == "in":
            edges = list(self.constraints.in_edges(subtask_name, data=True))
        else:
            raise ValueError("direction must be either 'in' or 'out'.")

        # For consistency, we'll always return a tuple of a single item here.
        return extract_constraints(edges)

    # -----------------------------------------------------------------------
    #  Internal (private) helper methods
    # -----------------------------------------------------------------------

    def _get_incoming_constraints(
        self, subtask_name: str
    ) -> List[Tuple[str, str, int, bool]]:
        """
        Collects all incoming constraints for a given subtask.

        Returns:
            List[Tuple[str, str, int, bool]]:
                Each tuple is (u, v, Interval, Urgency).
        """
        return [
            (u, v, data["info"]["Interval"], data["info"]["Urgency"])
            for u, v, data in self.constraints.in_edges(subtask_name, data=True)
        ]

    def _get_constraint_subtasks(
        self, current_state: Any, subtask_name: str
    ) -> List["Subtask"]:
        """
        Given the subtask_name, find all subtasks in current_state.partial_plan
        that match any incoming constraint edge to subtask_name.

        Returns:
            List["Subtask"]: All partial-plan subtasks that act as predecessors
                             (i.e., appear in the constraint graph as sources
                             for `subtask_name`).
        """
        incoming_nodes = {edge[0] for edge in self.constraints.in_edges(subtask_name)}

        # Filter partial_plan tasks that match any predecessor node by name
        # (or some name-matching condition).
        # If your subtask names must match exactly, replace `startswith(...)`
        # with direct equality checks.
        return [
            done_subtask
            for done_subtask in current_state.partial_plan
            if any(done_subtask.name.startswith(src) for src in incoming_nodes)
        ]
