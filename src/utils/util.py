import os
import signal

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPT_PATH = os.path.join(ROOT_PATH, "assets", "prompts")
ASSET_PATH = os.path.join(ROOT_PATH, "assets", "results")
TASK_PATH = os.path.join(ROOT_PATH, "assets", "tasks")
LOG_PATH = os.path.join(ROOT_PATH, "logs")


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
