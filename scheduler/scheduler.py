import pulp
from constants import LARGE_NUM, MIN_TIME, TRANSITION_TIME
from task import get_all_controllable_subtasks, tasks


class SchedulingProblem:
    def __init__(self, tasks):
        self.tasks = tasks
        self.prob = pulp.LpProblem("Household_Robot_Scheduling", pulp.LpMinimize)
        self.start_times = {}
        self.completion_times = {}
        self.task_vars = {}

    def define_variables(self):
        for task in self.tasks.values():
            for phase, duration, task_type in task.phases:
                subtask_name = f"{task.name}_{phase}"
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
        # Each sub-task must start exactly once
        for task in self.tasks.values():
            for phase, duration, task_type in task.phases:
                subtask_name = f"{task.name}_{phase}"
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
        for task in self.tasks.values():
            for i in range(len(task.phases) - 1):
                phase1, duration1, task_type1 = task.phases[i]
                phase2, duration2, task_type2 = task.phases[i + 1]
                subtask_name1 = f"{task.name}_{phase1}"
                subtask_name2 = f"{task.name}_{phase2}"

                # Start -> Continue -> End sequence
                self.prob += (
                    self.start_times[subtask_name2]
                    >= self.completion_times[subtask_name1]
                )
                self.prob += (
                    self.completion_times[subtask_name1]
                    == self.start_times[subtask_name1] + duration1
                )

            # Ensure the completion time for the last phase in each task
            last_phase, last_duration, last_task_type = task.phases[-1]
            last_subtask_name = f"{task.name}_{last_phase}"
            self.prob += (
                self.completion_times[last_subtask_name]
                == self.start_times[last_subtask_name] + last_duration
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
