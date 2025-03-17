import datetime
import logging
import signal
import time
from functools import wraps

from colorlog import ColoredFormatter

from utils.constants import LOG_PATH


def create_module_logger(module_name, module_log=False, all_log=True):
    """
    module_name: 모듈 이름
    module_log: 파일 핸들러를 추가할지 여부 (파일에도 로그를 기록)
    console_output: 콘솔에 로그를 출력할지 여부, 없어진 듯 하다
    """
    # 개별 로그 생성
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # 기존 핸들러가 있는지 확인하여 중복 추가 방지
    if logger.hasHandlers():
        return logger

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

    # 파일 핸들러 (all)
    file_handler = logging.FileHandler(
        LOG_PATH / "all_log" / f"{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.log",
        mode="a",
    )

    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 파일 핸들러 추가
    if module_log:
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


def retry(retries=3, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    time.sleep(delay)
            raise Exception(
                f"Function '{func.__name__}' failed after {retries} retries."
            )

        return wrapper

    return decorator


def time_logger(func):
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        print(f"Function '{func.__name__}' took {end_time - start_time:.4f} seconds.")
        return result

    return wrapper


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
