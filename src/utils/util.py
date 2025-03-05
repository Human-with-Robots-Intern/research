import logging
import signal
import time
from functools import wraps

from colorlog import ColoredFormatter

from utils.constants import LOG_PATH


def create_module_logger(module_name, is_file_handler=False):
    """
    module_name: 모듈 이름
    is_file_handler: 파일 핸들러를 추가할지 여부 (파일에도 로그를 기록)
    console_output: 콘솔에 로그를 출력할지 여부
    """
    # 개별 로그 생성
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)

    # 콘솔 핸들러 추가

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s %(log_color)s%(message)s",
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 추가
    if is_file_handler:
        file_handler = logging.FileHandler(
            LOG_PATH / f"{module_name}.log",
            # LOG_PATH / "all.log",
            mode="w",
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


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


def timeit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        results = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        # log.warning(f"Elapsed time: {elapsed_time:.2f} seconds")
        return results

    return wrapper
