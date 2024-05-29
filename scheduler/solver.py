import pulp

from scheduler import *
from task import get_all_controllable_subtasks


class SchedulingProblem:
    def __init__(self, tasks):
        self.tasks = tasks
        self.prob = pulp.LpProblem("Household_Robot_Scheduling", pulp.LpMinimize)
        self.start_times = {}
        self.completion_times = {}
        self.task_vars = {}

        self.define_variables()
        self.set_objective()
        self.add_constraints()

    def define_variables(self):
        for task in self.tasks:
            for subtask in task.subtasks:
                subtask_name = f"{task.name}_{subtask.name}"
                self.start_times[subtask_name] = pulp.LpVariable(
                    f"Start_time_{subtask_name}", lowBound=0, cat=pulp.LpContinuous
                )
                self.completion_times[subtask_name] = pulp.LpVariable(
                    f"Completion_time_{subtask_name}", lowBound=0, cat=pulp.LpContinuous
                )
                self.task_vars[subtask_name] = pulp.LpVariable(
                    f"Task_{subtask_name}", 0, 1, pulp.LpBinary
                )

    def set_objective(self):
        self.prob += (
            pulp.lpSum(
                [self.completion_times[subtask] for subtask in self.completion_times]
            ),
            "Total_Completion_Time",
        )

    def add_constraints(self):
        # Each sub-task must start exactly once and ruled by Min time
        for task in self.tasks:
            for subtask in task.subtasks:
                subtask_name = f"{task.name}_{subtask.name}"
                self.prob += self.task_vars[subtask_name] == 1
                self.prob += (
                    self.completion_times[subtask_name] - self.start_times[subtask_name]
                    >= MIN_TIME
                )

        # Non-overlapping Controllable tasks
        ctrl_subtask_names = get_all_controllable_subtasks(self.tasks)
        for base_idx in range(len(ctrl_subtask_names) - 1):
            for other_idx in range(base_idx + 1, len(ctrl_subtask_names)):
                base_subtask_name = ctrl_subtask_names[base_idx]
                other_subtask_name = ctrl_subtask_names[other_idx]

                # Introduce binary variables for each pair of sub-tasks
                b = pulp.LpVariable(f"b_{base_idx}_{other_idx}", cat="Binary")

                # Ensure that one sub-task starts after the other finishes
                self.prob += self.start_times[
                    base_subtask_name
                ] >= self.completion_times[other_subtask_name] - LARGE_NUM * (1 - b)
                self.prob += (
                    self.start_times[other_subtask_name]
                    >= self.completion_times[base_subtask_name] - LARGE_NUM * b
                )

        # Sub Task dependencies and durations (start -> continue -> end)
        for task in self.tasks:
            for i in range(len(task.subtasks) - 1):
                preceding_subtask = task.subtasks[i]
                trailing_subtask = task.subtasks[i + 1]

                pre_subtask_name = f"{task.name}_{preceding_subtask.name}"
                trail_subtask_name = f"{task.name}_{trailing_subtask.name}"

                # Start -> Continue -> End sequence
                self.prob += (
                    self.start_times[trail_subtask_name]
                    >= self.completion_times[pre_subtask_name]
                )
                self.prob += (
                    self.completion_times[pre_subtask_name]
                    == self.start_times[pre_subtask_name] + preceding_subtask.duration
                )

            # Ensure the completion time for the last subtask in each task
            last_subtask = task.subtasks[-1]
            last_subtask_name = f"{task.name}_{last_subtask.name}"
            self.prob += (
                self.completion_times[last_subtask_name]
                == self.start_times[last_subtask_name] + last_subtask.duration
            )

    def solve(self):
        self.prob.solve()
        return pulp.LpStatus[self.prob.status]

    def extract_schedule(self):
        schedule = []
        for var in self.start_times:
            start_time = pulp.value(self.start_times[var])
            completion_time = pulp.value(self.completion_times[var])
            schedule.append((var, start_time, completion_time))
        return schedule
