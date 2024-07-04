import copy

import pandas as pd

from concept.env import Env
from concept.task import Subtask, Task, get_all_subtasks


class ExhaustiveSearch:
    def __init__(self, env: Env, tasks: list[Task]) -> None:
        """Initialize the TaskScheduler with environment and tasks"""
        self.env = env
        self.init_location = self.env.current_location
        self.goal_location = self.env.goal_location
        self.tasks = tasks
        self.schedule = self.init_tree()

    def init_tree(self):
        best_schedule = None
        best_schedules = []
        best_cost = float("inf")
        subtasks = get_all_subtasks(self.tasks, mode="all")
        permutations = list(get_permutations(subtasks, []))

        # Calculate the optimal makespan
        for idx, permutation in enumerate(permutations):
            temp_permutation = copy.deepcopy(permutation)
            self.env.current_location = self.init_location
            total_cost, schedule = self.exhaustive_search(temp_permutation, 0, {})
            if total_cost < best_cost:
                best_cost = total_cost
                best_schedule = schedule
                best_schedules.append(best_schedules)

        if best_schedule:

            return best_schedule
        else:
            raise Exception("No optimal schedule exists")

    def exhaustive_search(
        self, permutation: list[Subtask], makespan: int, log: dict, index: int = 0
    ) -> tuple[int, dict]:
        """Calculate the expected duration for the given permutation (without actually moving rooms)

        Args:
            permutation (list[Subtask]): Sequence of subtasks
            makespan (int): Time taken to handle all subtasks
            log (dict): Schedule considering wait and move
            index (int, optional): Prevent log_dict key overwrite. Defaults to 0.

        Returns:
            tuple[int, dict]: Final makespan, log
        """

        def update_log_and_makespan(subtask, start_time, index):
            transition_cost = self.env.get_cost(subtask.location)
            move_start_time = start_time
            move_end_time = move_start_time + transition_cost

            # Log the move first
            if self.env.current_location != subtask.location:
                log[
                    f"Move_from_{self.env.current_location}_to_{subtask.location}_{index}"
                ] = {
                    "Start": move_start_time,
                    "End": move_end_time,
                }
                self.env.current_location = subtask.location

            # Now log the subtask
            task_start_time = move_end_time
            task_end_time = task_start_time + subtask.duration
            log[f"{subtask.name}_{index}"] = {
                "Start": task_start_time,
                "End": task_end_time,
            }

            return task_end_time

        def handle_Waiting(subtask: Subtask, makespan: int, index: int) -> int:
            """작업 시작 조건 충족위한 대기시간 결정

            Args:
                subtask (Subtask): 시작에 시간 제약이 있는 작업
                makespan (int): 작업 시작 전 시각
                index (int): dict key 겹침 방지용

            Raises:
                ValueError: Constraint가 없는 작업이 해당 함수에 들어온 경우

            Returns:
                int: 해당 작업 완료 시각
            """
            constraint_task = subtask.constraints.get("After")
            constraint_duration = subtask.constraints.get("Duration", 0)
            constraint_type = subtask.constraints.get("Type", 0)

            if constraint_task:
                constraint_key = next(
                    (key for key in log if key.startswith(constraint_task)), None
                )
                # constraint_key : 제약 조건 기준 작업
                if constraint_key:
                    task_end_time = log[constraint_key]["End"]

                    if makespan >= task_end_time + constraint_duration:
                        # 만약, 현 시점이 제약 조건을 충족하였다면
                        return makespan  # No waiting needed
                    else:
                        # 제약 조건을 충족하지 않는 경우, Waiting
                        waiting_time = task_end_time + constraint_duration - makespan
                        log[f"{constraint_type}_for_{constraint_task}_{index}"] = {
                            "Start": makespan,
                            "End": makespan + waiting_time,
                        }
                        return makespan + waiting_time
                else:
                    raise ValueError(
                        f"Constraint task {constraint_task} not found in log."
                    )
            return makespan

        def handle_Surveillance(
            subtask: Subtask,
            parallelable_subtask: list[Subtask],
            makespan: int,
            index: int,
        ) -> int:
            """Surveillance Subtask와 함께 병렬화를 진행할 작업을 선정

            Args:
                subtask (Subtask): 시작에 시간 제약이 있는 작업
                makespan (int): 작업 시작 전 시각
                index (int): dict key 겹침 방지용

            Raises:
                ValueError: Constraint가 없는 작업이 해당 함수에 들어온 경우

            Returns:
                int: 해당 작업 완료 시각
            """
            constraint_task = subtask.constraints.get("After")
            constraint_duration = subtask.constraints.get("Duration", 0)
            constraint_type = subtask.constraints.get("Type", 0)

            if constraint_task:
                constraint_key = next(
                    (key for key in log if key.startswith(constraint_task)), None
                )
                # constraint_key : 제약 조건 기준 작업
                if constraint_key:
                    task_end_time = log[constraint_key]["End"]

                    # TODO 바로 작업을 시작하게 만듦
                    # parallel_tasks = self.find_parallel_tasks(permutation, subtask.location)
                    #         for parallel_task in parallel_tasks:
                    #             permutation.remove(parallel_task)
                    #             makespan = self.update_log_and_makespan(
                    #                 parallel_task, surveillance_start_time, log, index
                    #             )
                    #             surveillance_start_time = makespan

                else:
                    raise ValueError(
                        f"Constraint task {constraint_task} not found in log."
                    )
            return makespan

        if not permutation:
            if self.env.current_location != self.goal_location:
                log[
                    f"Move_from_{self.env.current_location}_to_{self.goal_location}_{index}"
                ] = {
                    "Start": makespan,
                    "End": makespan + self.env.get_cost(self.goal_location),
                }

                makespan += self.env.get_cost(self.goal_location)
            return makespan, log

        subtask = permutation.pop(0)

        if subtask.constraints:
            if subtask.constraints.get("Type", None) == "Waiting":
                # Waiting 동작을 추가하고 makespan을 갱신하여 반환
                makespan = handle_Waiting(subtask, makespan, index)
            else:
                # Surveillance 동안 수행할 병렬가능 작업을 배치
                permutation, parallelable_subtask = self.get_parallelable_subtask(
                    permutation, subtask
                )

                makespan = handle_Surveillance(
                    subtask, parallelable_subtask, makespan, index
                )

        makespan = update_log_and_makespan(subtask, makespan, index)

        return self.exhaustive_search(permutation, makespan, log, index + 1)

    def generate_schedule(self):
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

    def get_parallelable_subtask(self, permutation, target_subtask):
        # Surveillance 15분. 결과값은 15분 자르기 + alpha겠지?

        # 앞으로 해야 하는 부엌 작업
        parallelable_subtasks = [
            subtask
            for subtask in permutation
            if subtask.location == target_subtask.location
            and target_subtask.task_name != subtask.task_name
        ]

        # 병렬 가능 후보군에서 해당 기간동안 병렬화할 수 있는 작업만 선택
        cumulative_duration = 0
        splitted_subtasks = []
        is_parallel_complete = False

        # 사이즈 20에 맞게 잘라야 함.
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

        # 병렬처리할 작업
        parallelable_subtasks = []
        cumulative_duration = 0
        # 병렬 처리 이후, 남겨진 수행할 작업
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

        # 기존 permutation에서 병렬 처리할 작업은 빼고, 남은 작업으로 작업 업데이트
        result_permutation = []
        is_parallel_subtask = False

        for subtask in permutation:
            # 병렬처리 대상 작업은 기존 permutation에서 제거
            for parallelable_subtask in parallelable_subtasks:
                if subtask.name == parallelable_subtask.name:
                    is_parallel_subtask = True

            # 나머지 작업이면 업데이트된 작업으로 바꿔치기
            for left_splitted_subtask in left_splitted_subtasks:
                if subtask.name == left_splitted_subtask.name:
                    result_permutation.append(left_splitted_subtask)

            # 일반적 경우 그냥 추가
            if is_parallel_subtask:
                continue

            if not is_parallel_subtask:
                result_permutation.append(subtask)

        return result_permutation, parallelable_subtasks


def get_permutations(lists, result):
    # If all lists are exhausted, return the result
    if all(len(lst) == 0 for lst in lists):
        yield result
        return

    # Choose an element from each list
    for i, lst in enumerate(lists):
        if lst:  # Only if the list has elements
            new_result = result + [lst[0]]
            new_lists = [lst[1:] if j == i else lst for j, lst in enumerate(lists)]
            yield from get_permutations(new_lists, new_result)
