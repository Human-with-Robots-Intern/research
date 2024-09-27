import json
import os
import signal

import numpy as np

from concept.schedule import ScheduledTask
from utils.constants import ROOT_PATH


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


def update_task_duration(self, task_name, subtask_name, duration: int):
    TASK_PATH = os.path.join(ROOT_PATH, f"assets/tasks/task_{task_name}.json")
    with open(TASK_PATH, "r") as f:
        task_dict = json.load(f)
