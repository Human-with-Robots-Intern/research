import json
import os

from concept.env import Env
from concept.task import parse_tasks
from scheduler.exhaustive_search3 import ExhaustiveSearch
from util.visualizer import *


def exhaustive_scheduler(env, tasks):
    task_schedule = ExhaustiveSearch(env, tasks).generate_schedule()
    visualize3(task_schedule)


if __name__ == "__main__":
    with open(os.path.join("asset", "task_detach.json"), "r") as file:
        tasks = parse_tasks(json.load(file))

    env = Env().gen_dummpy()

    exhaustive_scheduler(env, tasks)
