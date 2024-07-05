import json
import os
import sys

from anytree import Node, RenderTree
from concept.env import Env
from concept.task import parse_tasks
from scheduler.exhaustive_search2 import ExhaustiveSearch
from scheduler.milp_solver import SchedulingProblem
from scheduler.task_scheduler import TaskProfiler, TaskScheduler
from util.util import printing_queue
from util.visualizer import *

with open(os.path.join("asset", "task_detach.json"), "r") as file:
    tasks = parse_tasks(json.load(file))


def milp_scheduler(tasks):
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


def priority_scheduler(env, tasks):
    task_profiler = TaskProfiler(env)
    task_ques = task_profiler.priority_classify(tasks)

    task_schedule = TaskScheduler(env, task_ques).generate_schedule()

    visualize2(task_schedule)


def exhaustive_scheduler(env, tasks):
    task_schedule = ExhaustiveSearch(env, tasks).generate_schedule()
    visualize3(task_schedule)


if __name__ == "__main__":
    env = Env()
    env.gen_dummpy(current_location="Living Room", goal_location="Living Room")

    # milp_scheduler(tasks)
    # priority_scheduler(env, tasks)
    exhaustive_scheduler(env, tasks)
