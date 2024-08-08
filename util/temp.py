# NOTE! Do not Erase it,
# def _calculate_move_duration(self, path_difference: List[Node]) -> int:
#     """
#     Calculate the move duration for nodes whose names start with "Move".

#     Args:
#         path_difference (List[Node]): The path difference between the parent node and the constraint node.

#     Returns:
#         int: The total move duration.
#     """
#     path_difference = parent_node.path[len(constraint_node.path) - 1 :]
#     move_duration = self._calculate_move_duration(path_difference)

#     move_duration = 0
#     move_indexes = [
#         i
#         for i in range(len(path_difference) - 1)
#         if path_difference[i].name.startswith("Move")
#     ]

#     move_duration = sum(
#         path_difference[i].makespan - path_difference[i - 1].makespan
#         for i in move_indexes
#     )

#     return move_duration
