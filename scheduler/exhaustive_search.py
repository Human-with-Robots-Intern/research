import copy
from collections import deque
from itertools import permutations

import pandas as pd
from anytree import Node, RenderTree

from concept.env import Env
from concept.task import Subtask, Task, get_all_subtasks


class ExhaustiveSearch:
    def __init__(self, env: Env, tasks: list[Task]) -> None:
        """Initialize the TaskScheduler with environment and tasks"""
        self.env = env
        self.init_location = self.env.current_location

        self.tasks = tasks
        self.root_node = None
        self.init_tree()

    def init_tree(self):
        best_schedule, best_log = None, None
        best_cost = float("inf")
        subtasks = get_all_subtasks(self.tasks, mode="all")
        permutations = list(get_permutations(subtasks, []))

        # 최적의 makespan을 계산
        for idx, permutation in enumerate(permutations):
            temp_permutation = copy.deepcopy(permutation)
            self.env.current_location = self.init_location
            total_cost, log = self.exhaustive_search(temp_permutation, 0, {})

            if total_cost < best_cost:
                best_cost = total_cost
                best_schedule = permutations[idx]
                best_log = log

        print(best_log)

        if best_schedule:
            self.root_node = Node("Start")
            parent = self.root_node
            self.env.current_location = self.init_location
        else:
            raise Exception("Not exist optimal schedule")

        for subtask in best_schedule:
            if self.env.current_location != subtask.location:
                move_node = Node(self.env.move(subtask.location), parent=parent)
                parent = Node(subtask, parent=move_node)
            else:
                # 어떻게 Waiting을 추가하지?
                parent = Node(subtask, parent=parent)
            self.env.current_location = subtask.location

    def exhaustive_search(
        self, permutation: list[Subtask], makespan: int, log: dict, index: int = 0
    ) -> tuple[int, dict]:
        """permutation에 대해, 예상 소요 시간 계산 (실제로 방을 움직이는 것은 아님)

        Args:
            permutation (list[Subtask]): 일련의 subtask 순서
            makespan (int): 모든 subtask를 처리하는데 걸리는 시간
            log (dict): wait, move까지 고려한 schedule
            index (int, optional): prevent a log_dict key overwrite. Defaults to 0.

        Returns:
            tuple[int, dict]: 최종 makespan, log
        """

        def update_log_and_makespan(
            subtask,
            start_time,
            index,
        ):
            # Log the move first
            transition_cost = self.env.get_cost(subtask.location)
            move_start_time = start_time
            move_end_time = move_start_time + transition_cost
            log[
                f"move_from_{self.env.current_location}_to_{subtask.location}_{index}"
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
                "Location": subtask.location,
            }

            return task_end_time

        def handle_constraints(subtask, makespan, index):
            constraint_task = subtask.constraints.get("After")
            constraint_duration = subtask.constraints.get("Duration", 0)

            if constraint_task:
                constraint_key = next(
                    (key for key in log if key.startswith(constraint_task)), None
                )
                if constraint_key:
                    task_end_time = log[constraint_key]["End"]
                    if makespan >= task_end_time + constraint_duration:
                        return makespan  # No waiting needed
                    else:
                        waiting_time = task_end_time + constraint_duration - makespan
                        log[f"Waiting_for_{constraint_task}_{index}"] = {
                            "Start": makespan,
                            "End": makespan + waiting_time,
                        }
                        return makespan + waiting_time
                else:
                    raise ValueError(
                        f"Constraint task {constraint_task} not found in log."
                    )
            return makespan

        if not permutation:
            return makespan, log

        subtask = permutation.pop(0)

        if subtask.constraints:
            makespan = handle_constraints(subtask, makespan, index)

        makespan = update_log_and_makespan(
            subtask,
            makespan,
            index,
        )

        return self.exhaustive_search(permutation, makespan, log, index + 1)

    def generate_schedule(self):
        schedule = []

        for _, _, node in RenderTree(self.root_node):
            schedule.append(node.name)

        results = []
        start_time = 0
        for idx, subtask in enumerate(schedule):
            if idx == 0:
                continue
            results.append(
                {
                    "name": subtask.name,
                    "start": start_time,
                    "duration": subtask.duration,
                }
            )

            start_time += subtask.duration

        df = pd.DataFrame(results).iloc[::-1]

        return df


def get_permutations(lists, result):
    # 모든 리스트의 모든 요소를 다 사용한 경우
    if all(len(lst) == 0 for lst in lists):
        yield result
        return

    # 각 리스트에서 하나씩 요소를 선택
    for i, lst in enumerate(lists):
        if lst:  # 리스트에 요소가 남아 있는 경우에만
            # 요소를 하나 선택하여 새로운 결과 리스트에 추가
            new_result = result + [lst[0]]
            # 선택된 요소를 제외한 리스트들로 재귀 호출
            new_lists = [lst[1:] if j == i else lst for j, lst in enumerate(lists)]
            yield from get_permutations(new_lists, new_result)
