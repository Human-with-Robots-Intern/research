import numpy as np


class ScheduledTask:
    def __init__(self, name, start, end, duration, subtask=None):
        self.name = name
        self.start = start  # 시작 시간
        self.end = end  # 끝 시간
        self.duration = duration  # 지속 시간
        self.subtask = subtask  # 서브태스크 자체 정보

    def __repr__(self):
        return (
            f"ScheduledTask(name={self.name}, "
            f"subtask={self.subtask},start={self.start}, end={self.end}, duration={self.duration})"
        )


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
