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
        """
        self.env = env
        self.init_location = self.env.current_location
        self.goal_location = self.env.goal_location
        self.tasks = tasks
        self.schedule = self.init_tree()
        # with Pool() as pool:
        #     schedules = pool.map(self.evaluate_permutation, permutations)

    def init_tree(self) -> dict:
        """
        Initialize the search tree to find the optimal schedule.
        """
        best_schedule, best_cost = None, float("inf")
        subtasks = get_all_subtasks(self.tasks, mode="all")
        permutations = list(get_permutations(subtasks, []))

        print(f"Total permutations: {len(permutations)}")

        schedules = []
        for idx, permutation in enumerate(permutations):
            try:
                temp_permutation = copy.deepcopy(permutation)
                schedule = self.exhaustive_search(temp_permutation, 0, {})
            except ValueError:
                schedule = (float("inf"), {})

            # cost schedule permutation
            schedules.append((schedule[0], schedule[1], permutation))
            logger.info(
                f"Evaluated permutation {idx}/{len(permutations)-1}, cost : {schedule[0]}"
            )

        # Finding the minimum cost
        best_cost, best_schedule, best_permutation = min(schedules, key=lambda x: x[0])
        best_schedules = [
            idx
            for idx, (cost, schedule, perm) in enumerate(schedules)
            if cost == best_cost
        ]

        logger.info(f"optimal cost: {best_cost}")
        logger.info(
            f"Number of optimal solutions: {len(best_schedules)}, {best_schedules}"
        )

        # 디버깅용
        test_cost, test_schedule = self.exhaustive_search(permutations[133261], 0, {})
        print(test_cost, test_schedule)
        return test_schedule

        # if best_schedule:
        #     return best_schedule
        # else:
        #     raise Exception("No optimal schedule exists")

    def evaluate_permutation(self, permutation: list[Subtask]) -> tuple[int, dict]:
        """
        Evaluate a single permutation to find its total cost and schedule.

        Args:
            permutation (list[Subtask]): Sequence of subtasks.

        Returns:
            tuple[int, dict]: Total cost and the schedule.
        """

        self.env.current_location = self.init_location
        try:

            return self.exhaustive_search(permutation, 0, {})
        except ValueError:
            return float("inf"), {}

    def exhaustive_search(
        self, permutation: list[Subtask], makespan: int, log: dict, index: int = 0
    ) -> tuple[int, dict]:
        """
        Perform an exhaustive search to calculate the expected duration for the given permutation.
        """
        if not permutation:
            return self.handle_goal_return(makespan, log, index)

        subtask = permutation.pop(0)
        try:
            if subtask.constraints:
                permutation, makespan, log = self.handle_constraints(
                    subtask, permutation, makespan, log, index
                )
        except ValueError:
            raise ValueError("Surveillance constraint not satisfied")

        makespan = self.update_log_and_makespan(subtask, makespan, log, index)
        return self.exhaustive_search(permutation, makespan, log, index + 1)

    def update_log_and_makespan(self, subtask, start_time, log, index):
        """Update the log and makespan based on the subtask's location and duration."""
        transition_cost = self.env.get_cost(subtask.location)
        move_start_time = start_time
        move_end_time = move_start_time + transition_cost

        if self.env.current_location != subtask.location:
            log[f"Move_{self.env.current_location}_to_{subtask.location}_{index}"] = {
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

    def handle_goal_return(self, makespan, log, index):
        """Handle the return to the goal location."""
        if self.env.current_location != self.goal_location:
            goal_cost = self.env.get_cost(self.goal_location)
            log[f"Move_{self.env.current_location}_to_{self.goal_location}_{index}"] = {
                "Start": makespan,
                "End": makespan + goal_cost,
            }
            makespan += goal_cost
        return makespan, log

    def handle_constraints(self, subtask, permutation, makespan, log, index):
        """Handle the constraints for the given subtask."""
        constraint_type = subtask.constraints.get("Type", None)
        original_permutation = permutation

        if constraint_type == "Waiting":
            makespan, log = self.handle_waiting(subtask, makespan, log, index)
        else:
            try:
                permutation, parallelable_subtasks = self.get_parallelable_subtask(
                    permutation, subtask
                )
                parallelized_subtasks, makespan, log = self.handle_surveillance(
                    subtask, parallelable_subtasks, makespan, log, index
                )
                # original permutation에는 원래 작업 계획 상 병렬 처리 전 작업들이 존재
                # permutation에는 병렬 가능한 작업들이 제거된 상태의 작업들이 존재
                # 원하는 것 : 병렬 가능한 작업들이 존재하면서, 잘려진 원본의 데이터를 원래 자리에 끼워 넣는 것
                permutation = self.update_permutation_with_parallelized(
                    original_permutation, permutation, parallelized_subtasks
                )

            except ValueError:
                raise ValueError("Surveillance constraint not satisfied")

        return permutation, makespan, log

    def handle_waiting(self, subtask, makespan, log, index):
        """Determine waiting time for tasks with start constraints."""
        constraint_task = subtask.constraints.get("After")
        constraint_duration = subtask.constraints.get("Duration", 0)

        if constraint_task:
            constraint_key = next(
                (key for key in log if key.startswith(constraint_task)), None
            )
            if constraint_key:
                task_end_time = log[constraint_key]["End"]
                if makespan >= task_end_time + constraint_duration:
                    return makespan, log
                else:
                    waiting_time = task_end_time + constraint_duration - makespan
                    log[f"Waiting_for_{constraint_task}_{index}"] = {
                        "Start": makespan,
                        "End": makespan + waiting_time,
                    }
                    return makespan + waiting_time, log
            else:
                raise ValueError(
                    f"Constraint task {constraint_task} not found in log. Task: {subtask.name}"
                )

        return makespan, log

    def handle_surveillance(self, subtask, parallelable_subtasks, makespan, log, index):
        """Handle surveillance tasks with potential parallel subtasks."""
        constraint_task = subtask.constraints.get("After")
        constraint_duration = subtask.constraints.get("Duration", 0)
        parallelized_tasks = []

        if constraint_task:
            constraint_key = next(
                (key for key in log if key.startswith(constraint_task)), None
            )
            if constraint_key:
                precedence_task_end_time = log[constraint_key]["End"]

                if makespan >= precedence_task_end_time + constraint_duration:
                    task_start_time = makespan
                    parallel_cumulative_duration = 0
                    wait_duration = 0

                    for _ in range(len(parallelable_subtasks)):
                        parallelable_subtask = parallelable_subtasks.pop(0)

                        if parallelable_subtask.constraints is None:
                            task_end_time = (
                                task_start_time + parallelable_subtask.duration
                            )
                        else:
                            wait_duration = parallelable_subtask.constraints.get(
                                "Duration", 0
                            )
                            task_end_time = (
                                task_start_time
                                + parallelable_subtask.duration
                                + wait_duration
                            )
                            task_start_time = (
                                task_end_time - parallelable_subtask.duration
                            )

                        log[f"{parallelable_subtask.name}_{index}"] = {
                            "Start": task_start_time,
                            "End": task_end_time,
                        }

                        parallelized_tasks.append(parallelable_subtask)
                        parallel_cumulative_duration += (
                            task_end_time - task_start_time + wait_duration
                        )

                        if parallel_cumulative_duration == subtask.duration:
                            break

                    return parallelized_tasks, makespan, log
                else:
                    raise ValueError(
                        "The surveillance task must start right after precedence task end + wait duration"
                    )
            else:
                raise ValueError(
                    f"Constraint task {constraint_task} not found in log. Task: {subtask.name}"
                )

        return makespan, log

    def update_permutation_with_parallelized(
        self, original_permutation, permutation, parallelized_subtasks
    ):
        """Update the permutation by removing completed parallelized subtasks."""
        # permutation은 병렬처리 이후, 잘리고 남겨진 subtask를 삽입하는 역할임

        result_permutation = []
        for subtask in original_permutation:
            if parallelized_subtasks:
                for parallelized_subtask in parallelized_subtasks:
                    if (
                        parallelized_subtask.name == subtask.name
                        and parallelized_subtask.duration == subtask.duration
                    ):
                        for cropped_subtask in permutation:
                            if cropped_subtask.name == parallelized_subtask.name:
                                result_permutation.append(cropped_subtask)
                            else:
                                pass
                    else:
                        result_permutation.append(subtask)
            else:
                result_permutation.append(subtask)
        return result_permutation

    def get_parallelable_subtask(
        self, permutation: list[Subtask], target_subtask: Subtask
    ) -> tuple[list[Subtask], list[Subtask]]:
        """Get parallelable subtasks for a given target subtask."""
        parallelable_subtasks = [
            subtask
            for subtask in permutation
            if subtask.location == target_subtask.location
            and target_subtask.task_name != subtask.task_name
        ]

        parallelized_subtasks = []
        left_splitted_subtasks = []
        cumulative_duration = 0
        is_parallel_complete = False

        for parallelable_subtask in parallelable_subtasks:
            constraint_duration = (
                parallelable_subtask.constraints["Duration"]
                if parallelable_subtask.constraints
                else 0
            )
            cumulative_duration += parallelable_subtask.duration + constraint_duration

            if cumulative_duration <= target_subtask.duration:
                parallelized_subtasks.append(parallelable_subtask)
            else:
                if not is_parallel_complete:
                    is_parallel_complete = True
                    over_duration = cumulative_duration - target_subtask.duration
                    splitted_subtask1 = parallelable_subtask
                    splitted_subtask2 = copy.deepcopy(parallelable_subtask)
                    splitted_subtask1.duration -= over_duration
                    splitted_subtask2.duration = over_duration

                    parallelized_subtasks.append(splitted_subtask1)
                    left_splitted_subtasks.append(splitted_subtask2)
                else:
                    break

        result_permutation = []
        for subtask in permutation:
            if subtask not in parallelable_subtasks:
                result_permutation.append(subtask)
            else:
                for left_splitted_subtask in left_splitted_subtasks:
                    if subtask.name == left_splitted_subtask.name:
                        result_permutation.append(left_splitted_subtask)

        return result_permutation, parallelable_subtasks

    def generate_schedule(self) -> pd.DataFrame:
        """Generate the schedule in a pandas DataFrame."""

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


def get_permutations(lists: list[list[Subtask]], result: list[Subtask]):
    """
    Generate all permutations of the given lists of subtasks.
    """
    if all(len(lst) == 0 for lst in lists):
        yield result
        return

    for i, lst in enumerate(lists):
        if lst:
            new_result = result + [lst[0]]
            new_lists = [lst[1:] if j == i else lst for j, lst in enumerate(lists)]
            yield from get_permutations(new_lists, new_result)
