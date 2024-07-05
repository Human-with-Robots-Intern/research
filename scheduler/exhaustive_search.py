import copy
import logging
from multiprocessing import Pool

import pandas as pd

from concept.env import Env
from concept.task import Subtask, Task, get_all_subtasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExhaustiveSearch:
    def __init__(self, env: Env, tasks: list[Task]) -> None:
        """
        Initialize the ExhaustiveSearch with environment and tasks.

        Args:
            env (Env): The environment.
            tasks (list[Task]): List of tasks.
        """
        self.env = env
        self.init_location = self.env.current_location
        self.goal_location = self.env.goal_location
        self.tasks = tasks
        self.schedule = self.init_tree()

    def init_tree(self) -> dict:
        """
        Initialize the search tree to find the optimal schedule.

        Returns:
            dict: The best schedule found.

        Raises:
            Exception: If no optimal schedule exists.
        """
        best_schedule = None
        best_cost = float("inf")
        subtasks = get_all_subtasks(self.tasks, mode="all")
        permutations = list(get_permutations(subtasks, []))

        # Evaluate permutations in parallel
        with Pool() as pool:
            results = pool.map(self.evaluate_permutation, permutations)

        best_result = min(results, key=lambda x: x[0])
        best_cost, best_schedule = best_result

        if best_schedule:
            return best_schedule
        else:
            raise Exception("No optimal schedule exists")

    def evaluate_permutation(self, permutation: list[Subtask]) -> tuple[int, dict]:
        """
        Evaluate a single permutation to find its total cost and schedule.

        Args:
            permutation (list[Subtask]): Sequence of subtasks.

        Returns:
            tuple[int, dict]: Total cost and the schedule.
        """
        temp_permutation = copy.deepcopy(permutation)
        self.env.current_location = self.init_location
        try:
            return self.exhaustive_search(temp_permutation, 0, {})
        except ValueError:
            return float("inf"), {}

    def exhaustive_search(
        self, permutation: list[Subtask], makespan: int, log: dict, index: int = 0
    ) -> tuple[int, dict]:
        """
        Perform an exhaustive search to calculate the expected duration for the given permutation.

        Args:
            permutation (list[Subtask]): Sequence of subtasks.
            makespan (int): Time taken to handle all subtasks.
            log (dict): Schedule considering wait and move.
            index (int, optional): Prevent log_dict key overwrite. Defaults to 0.

        Returns:
            tuple[int, dict]: Final makespan, log.
        """

        def update_log_and_makespan(subtask, start_time, index):
            transition_cost = self.env.get_cost(subtask.location)
            move_start_time = start_time
            move_end_time = move_start_time + transition_cost

            if self.env.current_location != subtask.location:
                log[
                    f"Move_{self.env.current_location}_to_{subtask.location}_{index}"
                ] = {
                    "Start": move_start_time,
                    "End": move_end_time,
                }
                self.env.current_location = subtask.location

            task_start_time = move_end_time
            task_end_time = task_start_time + subtask.duration
            log[f"{subtask.name}_{index}"] = {
                "Start": task_start_time,
                "End": task_end_time,
            }

            return task_end_time

        def handle_waiting(subtask: Subtask, makespan: int, index: int) -> int:
            """
            Determine waiting time for tasks with start constraints.

            Args:
                subtask (Subtask): Task with time constraints.
                makespan (int): Time before starting the task.
                index (int): Prevent log_dict key overwrite.

            Returns:
                int: Updated makespan.
            """
            constraint_task = subtask.constraints.get("After")
            constraint_duration = subtask.constraints.get("Duration", 0)

            if constraint_task:
                constraint_key = next(
                    (key for key in log if key.startswith(constraint_task)), None
                )
                if constraint_key:
                    task_end_time = log[constraint_key]["End"]
                    if makespan >= task_end_time + constraint_duration:
                        return makespan
                    else:
                        waiting_time = task_end_time + constraint_duration - makespan
                        log[f"Waiting_for_{constraint_task}_{index}"] = {
                            "Start": makespan,
                            "End": makespan + waiting_time,
                        }
                        return makespan + waiting_time
                else:
                    raise ValueError(
                        f"Constraint task {constraint_task} not found in log. Task: {subtask.name}"
                    )
            return makespan

        def handle_surveillance(
            subtask: Subtask,
            parallelable_subtasks: list[Subtask],
            makespan: int,
            index: int,
        ) -> int:
            """
            Handle surveillance tasks with potential parallel subtasks.

            Args:
                subtask (Subtask): Surveillance task.
                parallelable_subtasks (list[Subtask]): List of parallelable subtasks.
                makespan (int): Time before starting the task.
                index (int): Prevent log_dict key overwrite.

            Returns:
                int: Updated makespan.
            """
            constraint_task = subtask.constraints.get("After")
            constraint_duration = subtask.constraints.get("Duration", 0)

            if constraint_task:
                constraint_key = next(
                    (key for key in log if key.startswith(constraint_task)), None
                )
                if constraint_key:
                    precedence_task_end_time = log[constraint_key]["End"]
                    if makespan == precedence_task_end_time + constraint_duration:
                        task_start_time = makespan
                        for parallelable_subtask in parallelable_subtasks:
                            task_end_time = (
                                task_start_time + parallelable_subtask.duration
                            )
                            log[f"{parallelable_subtask.name}_{index}"] = {
                                "Start": task_start_time,
                                "End": task_end_time,
                            }
                            task_start_time = task_end_time
                        return makespan
                    else:
                        raise ValueError(
                            "The surveillance task must start right after precedence task end"
                        )
                else:
                    raise ValueError(
                        f"Constraint task {constraint_task} not found in log. Task: {subtask.name}"
                    )
            return makespan

        if not permutation:
            # 스케쥴링 끝에, 목표 지점으로
            if self.env.current_location != self.goal_location:
                goal_cost = self.env.get_cost(self.goal_location)
                log[
                    f"Move_{self.env.current_location}_to_{self.goal_location}_{index}"
                ] = {
                    "Start": makespan,
                    "End": makespan + goal_cost,
                }
                makespan += goal_cost
            return makespan, log

        subtask = permutation.pop(0)

        if subtask.constraints:
            if subtask.constraints.get("Type", None) == "Waiting":
                makespan = handle_waiting(subtask, makespan, index)
            else:
                permutation, parallelable_subtasks = self.get_parallelable_subtask(
                    permutation, subtask
                )
                makespan = handle_surveillance(
                    subtask, parallelable_subtasks, makespan, index
                )

        makespan = update_log_and_makespan(subtask, makespan, index)

        return self.exhaustive_search(permutation, makespan, log, index + 1)

    def generate_schedule(self) -> pd.DataFrame:
        """
        Generate the schedule in a pandas DataFrame.

        Returns:
            pd.DataFrame: The generated schedule.
        """
        results = [
            {
                "name": "_".join(subtask.split("_")[:-1]),
                "start": info["Start"],
                "end": info["End"],
            }
            for subtask, info in self.schedule.items()
        ]
        df = pd.DataFrame(results).iloc[::-1]
        return df

    def get_parallelable_subtask(
        self, permutation: list[Subtask], target_subtask: Subtask
    ) -> tuple[list[Subtask], list[Subtask]]:
        """
        Get parallelable subtasks for a given target subtask.

        Args:
            permutation (list[Subtask]): Remaining subtasks.
            target_subtask (Subtask): Target subtask.

        Returns:
            tuple[list[Subtask], list[Subtask]]: Updated permutation and list of parallelable subtasks.
        """
        parallelable_subtasks = [
            subtask
            for subtask in permutation
            if subtask.location == target_subtask.location
            and target_subtask.task_name != subtask.task_name
        ]

        cumulative_duration = 0
        splitted_subtasks = []
        is_parallel_complete = False

        for parallelable_subtask in parallelable_subtasks:
            cumulative_duration += parallelable_subtask.duration

            if cumulative_duration > target_subtask.duration:
                if not is_parallel_complete:
                    over_duration = cumulative_duration - target_subtask.duration
                    splitted_subtask1 = copy.deepcopy(parallelable_subtask)
                    splitted_subtask2 = copy.deepcopy(parallelable_subtask)
                    splitted_subtask1.duration -= over_duration
                    splitted_subtask2.duration = over_duration
                    splitted_subtasks.extend([splitted_subtask1, splitted_subtask2])
                    is_parallel_complete = True
                else:
                    splitted_subtasks.append(parallelable_subtask)
            else:
                splitted_subtasks.append(parallelable_subtask)

        parallelable_subtasks = []
        cumulative_duration = 0
        left_splitted_subtasks = []
        is_parallel_complete = False

        for splitted_subtask in splitted_subtasks:
            if not is_parallel_complete:
                cumulative_duration += splitted_subtask.duration
                parallelable_subtasks.append(splitted_subtask)
                if cumulative_duration == target_subtask.duration:
                    is_parallel_complete = True
            else:
                left_splitted_subtasks.append(splitted_subtask)

        result_permutation = []
        for subtask in permutation:
            is_parallel_subtask = any(
                subtask.name == psubtask.name for psubtask in parallelable_subtasks
            )
            if not is_parallel_subtask:
                result_permutation.append(subtask)

            for left_splitted_subtask in left_splitted_subtasks:
                if subtask.name == left_splitted_subtask.name:
                    result_permutation.append(left_splitted_subtask)

        return result_permutation, parallelable_subtasks


def get_permutations(lists: list[list[Subtask]], result: list[Subtask]):
    """
    Generate all permutations of the given lists of subtasks.

    Args:
        lists (list[list[Subtask]]): List of lists of subtasks.
        result (list[Subtask]): Accumulated result of permutations.

    Yields:
        list[Subtask]: A permutation of subtasks.
    """
    if all(len(lst) == 0 for lst in lists):
        yield result
        return

    for i, lst in enumerate(lists):
        if lst:
            new_result = result + [lst[0]]
            new_lists = [lst[1:] if j == i else lst for j, lst in enumerate(lists)]
            yield from get_permutations(new_lists, new_result)
