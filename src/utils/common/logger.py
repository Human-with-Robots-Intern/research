import datetime
import logging

from colorlog import ColoredFormatter

from utils.config.constants import LOG_PATH

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
COLOR_LOG_FORMAT = "%(log_color)s%(levelname)-8s%(reset)s %(log_color)s%(message)s"


def _get_console_handler():
    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        COLOR_LOG_FORMAT,
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    handler.setFormatter(formatter)
    return handler


def _get_file_handler(filepath, mode="a"):
    handler = logging.FileHandler(filepath, mode=mode)
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)
    return handler


def create_module_logger(module_name, module_log=False):
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.hasHandlers():
        return logger

    logger.addHandler(_get_console_handler())

    log_file = LOG_PATH / "all_log" / f"{datetime.datetime.now():%Y%m%d_%H%M}.log"
    logger.addHandler(_get_file_handler(log_file))

    if module_log:
        module_log_file = LOG_PATH / f"{module_name}.log"
        logger.addHandler(_get_file_handler(module_log_file, mode="w"))

    return logger
