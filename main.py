import json
import os
import sys

from scheduler.solver import SchedulingProblem
from task import get_subtask_dict, parse_tasks
from visualizer import *


def main():
    with open(os.path.join("asset", "tasks.json"), "r") as file:
        tasks = parse_tasks(json.load(file))
    # Create and define the scheduling problem
    scheduler = SchedulingProblem(tasks)

    # Solve the problem
    status = scheduler.solve()
    print("Status:", status)

    # Extract and print the schedule
    schedule = scheduler.extract_schedule()
    for task, start, end in schedule:
        print(f"{task}: Start at {start}, Complete at {end}")

    # Visualize the schedule
    visualize(tasks, schedule)


if __name__ == "__main__":
    main()
