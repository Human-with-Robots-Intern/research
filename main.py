import json
import os

from concept.agent import Agent
from concept.env import Env
from concept.task import parse_tasks
from scheduler.exhaustive_scheduler import ExhaustiveScheduler
from util.visualizer import *

if __name__ == "__main__":
    with open(os.path.join("asset", "task_detach.json"), "r") as file:
        tasks = parse_tasks(json.load(file))

    env = Env()
    env.gen_dummy()
    agent = Agent("Waiting", "Living Room", env)

    task_schedule = ExhaustiveScheduler(agent, tasks).generate_schedule()
    visualize4(task_schedule)
