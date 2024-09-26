import os
import signal

import numpy as np

from concept.schedule import ScheduledTask


# with timeout(seconds=timeout_seconds):
class timeout:
    def __init__(self, seconds=1, error_message="Timeout"):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)


def simulate_task_plan(task_plan):
    """
    Simulate the execution of a task plan by adding noise to the task durations.

    Args:
        task_plan (list of ScheduledTask): The planned tasks.

    Returns:
        list of ScheduledTask: The simulated tasks with actual start and end times.
    """
    sim_schedule = []
    current_time = 0

    for task in task_plan:
        # Simulate task duration with some noise
        while True:
            sim_task_duration = round(np.random.normal(task.duration, 0.1), 3)
            if sim_task_duration > 0:
                break
        sim_task_start_time = round(current_time, 3)
        sim_task_end_time = sim_task_start_time + sim_task_duration

        # Create a simulated ScheduledTask
        sim_task = ScheduledTask(
            name=task.name,
            start=sim_task_start_time,
            end=sim_task_end_time,
            duration=sim_task_duration,
            subtask=task.subtask if hasattr(task, "subtask") else None,
        )
        sim_schedule.append(sim_task)

        current_time = sim_task_end_time  # Update current time for the next task

    return sim_schedule


def convert_tree_to_schedule(root):
    schedules = []

    # Traverse the tree to gather task paths
    def traverse_tree(node, current_path):
        task = ScheduledTask(
            node.name,
            node.makespan - node.duration,
            node.makespan,
            node.duration,
            node.subtask if hasattr(node, "subtask") else None,
        )
        if not node.children:  # If it's a leaf node, store the path
            schedules.append(current_path + [task])
        for child in node.children:
            traverse_tree(
                child,
                current_path + [task],
            )

    traverse_tree(root, [])

    return schedules[0][1:]
