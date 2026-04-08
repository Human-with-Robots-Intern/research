"""Reusable subprocess batch runner helpers for experiment scripts."""

from __future__ import annotations

import concurrent.futures
import gc
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from itertools import product
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.experiments.offline_harness import (
    ExperimentConfig as OfflineExperimentConfig,
    load_experiment_config,
    resolve_instructions,
)
from src.utils.config.constants import (
    ASSETS_PATH,
    INIT_PRIOR_VARIANCE,
    LOG_PATH,
    RESULT_PATH,
    SCRIPTS_PATH,
)

MEMORY_THRESHOLD_PERCENT = 85.0
MEMORY_CHECK_INTERVAL_SECONDS = 5
GC_COLLECT_AFTER_TASKS = 5
DEFAULT_TIMEOUT_SECONDS = 1200
PROJECT_ROOT = SCRIPTS_PATH.parent


class BaselineType(Enum):
    """Represents the baseline family for AI2-THOR jobs."""

    SCHEDULER = 1
    LLM = 0


class AblationConfig(Enum):
    """Enumerations for supported DAG ablation settings."""

    NONE_URGENCY = {
        "alpha_heuristic": 1.0,
        "beta_heuristic": 0.0,
        "gamma_heuristic": 100.0,
    }
    NONE_REMAINING_WORK = {
        "alpha_heuristic": 1.0,
        "beta_heuristic": 10.0,
        "gamma_heuristic": 0.0,
    }
    NONE_MONITORING = {
        "disable_monitoring": True,
    }
    GREEDY = {
        "beam_width": 1,
        "beam_depth": 1,
    }
    DEFAULT = {}


class InitPriorConfig(Enum):
    """Enumerations for supported initial prior settings."""

    OVER_ESTIMATE = {
        "init_prior_mean": 140.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    OVER_MEDIUM_ESTIMATE = {
        "init_prior_mean": 120.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    CORRECT_ESTIMATE = {
        "init_prior_mean": 100.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    UNDER_MEDIUM_ESTIMATE = {
        "init_prior_mean": 80.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    UNDER_ESTIMATE = {
        "init_prior_mean": 60.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    OVER_ESTIMATE_130 = {
        "init_prior_mean": 130.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    OVER_ESTIMATE_110 = {
        "init_prior_mean": 110.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    UNDER_ESTIMATE_90 = {
        "init_prior_mean": 90.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }
    UNDER_ESTIMATE_70 = {
        "init_prior_mean": 70.0,
        "init_prior_variance": INIT_PRIOR_VARIANCE,
    }


@dataclass(frozen=True)
class BatchTask:
    """Serializable subprocess task executed by the shared batch runner.

    Args:
        name: Human-readable task identifier.
        command: Full subprocess argv list.
        log_path: Log file destination for stdout/stderr snapshots.
        metadata: Extra task metadata used for dry-run and progress logging.
        max_retries: Maximum number of attempts before the task is marked failed.
        retry_delay_seconds: Delay between retries.
        startup_delay_seconds: Optional initial delay before the first attempt.
        timeout_seconds: Per-attempt timeout.
        gpu_id: GPU assignment for CUDA-aware jobs. ``-1`` disables pinning.
        reset_ros_state: Whether the worker should reset ROS object state first.
        cwd: Optional working directory for subprocess execution.
    """

    name: str
    command: list[str]
    log_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 1
    retry_delay_seconds: float = 0.0
    startup_delay_seconds: float = 0.0
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    gpu_id: int = -1
    reset_ros_state: bool = False
    cwd: Path | None = None

    def summary(self) -> str:
        """Render a concise dry-run summary line."""

        metadata_bits = [f"{key}={value}" for key, value in self.metadata.items()]
        return f"{self.name} | {' | '.join(metadata_bits)}"


@dataclass(frozen=True)
class OfflineBatchOptions:
    """Options for constructing offline subprocess jobs."""

    base_config_path: Path | None
    command: str
    planner_types: list[str]
    task_folder_names: list[str]
    cases: list[str]
    scenes: list[str]
    instructions: list[str]
    max_tasks: int | None
    beam_width_values: list[int]
    beam_depth_values: list[int]
    nav_graph_source: str | None
    output_dir: Path
    experiment_name: str | None = None
    disable_monitoring: bool = False
    gt_distribution: str | None = None
    gt_seed: int | None = None
    init_prior_mean: float | None = None
    init_prior_variance: float | None = None
    factor_alpha: float | None = None
    bayesian_threshold_probability: float | None = None
    oracle_time_limit_seconds: float | None = None
    skip_completed: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    tags: list[str] = field(default_factory=list)


def get_memory_usage() -> float:
    """Return current system memory usage percentage."""

    import psutil

    return float(psutil.virtual_memory().percent)


def wait_for_memory_available(
    logger: logging.Logger,
    threshold: float = MEMORY_THRESHOLD_PERCENT,
    timeout_seconds: int = 600,
) -> None:
    """Pause scheduling while system memory usage remains high.

    Args:
        logger: Logger used for periodic warnings.
        threshold: Maximum acceptable memory percentage.
        timeout_seconds: Maximum wait duration before continuing anyway.
    """

    start_time = time.time()
    last_log_time = start_time
    while get_memory_usage() > threshold:
        current_time = time.time()
        elapsed_seconds = current_time - start_time
        if elapsed_seconds > timeout_seconds:
            logger.critical(
                "Memory usage %.1f%% still exceeds threshold after %ss; "
                "continuing anyway.",
                get_memory_usage(),
                timeout_seconds,
            )
            break
        if current_time - last_log_time >= 30:
            logger.warning(
                "Memory usage %.1f%%; waiting for headroom (%ss elapsed).",
                get_memory_usage(),
                int(elapsed_seconds),
            )
            last_log_time = current_time
        time.sleep(MEMORY_CHECK_INTERVAL_SECONDS)
        gc.collect()


def cleanup_subprocess(process: subprocess.Popen[str]) -> None:
    """Terminate a process tree if it is still running.

    Args:
        process: Process handle returned by ``subprocess.Popen``.
    """

    import psutil

    try:
        if process.poll() is not None:
            return
        parent = psutil.Process(process.pid)
        try:
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(children, timeout=1)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.kill()
            parent.wait(timeout=1)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass
    except Exception as exc:  # pragma: no cover - best effort cleanup.
        logging.getLogger(__name__).warning("Error cleaning subprocess: %s", exc)


def _resolve_repo_path(path_like: str | Path) -> Path:
    """Resolve a repo-relative path against the project root."""

    candidate = Path(path_like)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _sanitize_token(value: str) -> str:
    """Normalize an arbitrary string into a filename-safe token."""

    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def _append_flag(command: list[str], flag: str, value: Any) -> None:
    """Append a CLI flag only when its value is meaningful."""

    if value is None:
        return
    if isinstance(value, bool):
        if value:
            command.append(flag)
        return
    if isinstance(value, (list, tuple)):
        if not value:
            return
        command.append(flag)
        command.extend(str(item) for item in value)
        return
    command.extend([flag, str(value)])


def _reset_ros_state(file_copy_lock: threading.Lock, logger: logging.Logger) -> None:
    """Restore ROS object state before a real-world run."""

    object_mapping_path = PROJECT_ROOT / "assets/ros/static/object_init_states.json"
    object_positions_path = PROJECT_ROOT / "assets/ros/dynamic/object_states.json"
    with file_copy_lock:
        if object_mapping_path.exists():
            shutil.copy2(object_mapping_path, object_positions_path)
            logger.info("Reset ROS object state from %s.", object_mapping_path)
            return
        logger.warning("ROS object init file not found: %s", object_mapping_path)


def _run_task_subprocess(
    task: BatchTask,
    attempt: int,
    logger: logging.Logger,
) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess attempt and append outputs to the task log.

    Args:
        task: Task definition with command and environment information.
        attempt: 1-indexed attempt number.
        logger: Logger used for progress reporting.

    Returns:
        Completed process-like result with captured stdout/stderr.
    """

    env = os.environ.copy()
    if task.gpu_id >= 0:
        env["CUDA_VISIBLE_DEVICES"] = str(task.gpu_id)
    logger.info(
        "Executing task '%s' (GPU=%s): %s",
        task.name,
        task.gpu_id,
        " ".join(task.command),
    )
    process = subprocess.Popen(
        task.command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(task.cwd) if task.cwd is not None else None,
    )
    try:
        stdout, stderr = process.communicate(timeout=task.timeout_seconds)
        returncode = int(process.returncode or 0)
    except subprocess.TimeoutExpired:
        cleanup_subprocess(process)
        stdout = ""
        stderr = f"Process killed due to timeout after {task.timeout_seconds}s"
        returncode = -1
    except Exception:
        cleanup_subprocess(process)
        raise
    finally:
        cleanup_subprocess(process)

    result = subprocess.CompletedProcess(
        args=task.command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    log_header = (
        f"\n--- {'SUCCESS' if result.returncode == 0 else 'FAILURE'} "
        f"(Attempt {attempt}) ---\n"
    )
    log_content = (
        result.stdout
        if result.returncode == 0
        else (
            f"Return Code: {result.returncode}\n--- STDOUT ---\n{result.stdout}\n"
            f"--- STDERR ---\n{result.stderr}"
        )
    )
    task.log_path.parent.mkdir(parents=True, exist_ok=True)
    with task.log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(log_header)
        log_file.write(log_content)
    return result


def _worker(
    task: BatchTask,
    logger: logging.Logger,
    file_copy_lock: threading.Lock,
) -> None:
    """Run a single batch task with retries and memory-aware throttling."""

    wait_for_memory_available(logger)
    memory_at_start = get_memory_usage()
    try:
        if task.reset_ros_state:
            _reset_ros_state(file_copy_lock, logger)
        if task.startup_delay_seconds > 0:
            logger.info(
                "Delaying task '%s' for %.1fs before first attempt.",
                task.name,
                task.startup_delay_seconds,
            )
            time.sleep(task.startup_delay_seconds)
        logger.critical("WORKER START | %s", task.summary())
        retries = max(int(task.max_retries), 1)
        for attempt in range(1, retries + 1):
            result = _run_task_subprocess(task, attempt, logger)
            if result.returncode == 0:
                logger.info("Task '%s' succeeded on attempt %s.", task.name, attempt)
                return
            if attempt < retries:
                logger.warning(
                    "Task '%s' failed on attempt %s. Retrying in %.1fs.",
                    task.name,
                    attempt,
                    task.retry_delay_seconds,
                )
                if task.retry_delay_seconds > 0:
                    time.sleep(task.retry_delay_seconds)
        logger.error("Task '%s' failed after %s attempts.", task.name, retries)
    finally:
        gc.collect()
        memory_at_end = get_memory_usage()
        logger.info(
            "Task '%s' completed. Memory usage %.1f%% (%+.1f%%).",
            task.name,
            memory_at_end,
            memory_at_end - memory_at_start,
        )


def execute_batch_tasks(
    tasks: Sequence[BatchTask],
    *,
    max_workers: int,
    logger: logging.Logger,
) -> None:
    """Execute tasks concurrently using the shared worker implementation.

    Args:
        tasks: Prepared subprocess tasks.
        max_workers: Maximum worker threads.
        logger: Shared logger.
    """

    if not tasks:
        logger.warning("No tasks to execute.")
        return

    file_copy_lock = threading.Lock()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: list[concurrent.futures.Future[None]] = [
            executor.submit(_worker, task, logger, file_copy_lock) for task in tasks
        ]
        pending_futures = set(futures)
        completed_count = 0
        last_log_time = time.time()
        while pending_futures:
            done, not_done = concurrent.futures.wait(
                pending_futures,
                timeout=30,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                try:
                    future.result()
                    completed_count += 1
                    if completed_count % GC_COLLECT_AFTER_TASKS == 0:
                        logger.info(
                            "Completed %s tasks. Running garbage collection.",
                            completed_count,
                        )
                        gc.collect()
                        logger.info(
                            "Current memory usage: %.1f%%", get_memory_usage()
                        )
                except Exception as exc:
                    logger.critical("A task generated an exception: %s", exc)
                    logger.critical(traceback.format_exc())
            pending_futures = not_done
            current_time = time.time()
            if current_time - last_log_time >= 60 or not done:
                logger.critical(
                    "Progress Update: %s/%s completed. %s pending/running. "
                    "(Memory: %.1f%%)",
                    completed_count,
                    len(tasks),
                    len(pending_futures),
                    get_memory_usage(),
                )
                last_log_time = current_time
        gc.collect()


def log_dry_run(tasks: Sequence[BatchTask], logger: logging.Logger) -> None:
    """Emit a dry-run summary for prepared tasks."""

    logger.critical("=" * 80)
    logger.critical("DRY RUN MODE: Found %s experiments to run.", len(tasks))
    logger.critical("=" * 80)
    for task in tasks:
        logger.critical("  - %s", task.summary())
    logger.critical("Total %s experiments to run.", len(tasks))
    logger.critical("=" * 80)


def load_instruction_case_mapping_from_scenes(
    target_scenes: list[str],
    task_folder_names: str | list[str],
    logger: logging.Logger,
    min_task_count: int = 0,
    min_constraint_count: int = 0,
) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Load instruction file paths grouped by case and scene."""

    folder_names = (
        [task_folder_names] if isinstance(task_folder_names, str) else task_folder_names
    )
    case_instruction_mapping: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for task_folder_name in folder_names:
        task_folder = ASSETS_PATH / "tasks" / task_folder_name
        if not task_folder.exists():
            logger.error("Task folder not found: %s", task_folder)
            continue
        for test_case in sorted(task_folder.iterdir(), key=lambda path: path.name):
            if not test_case.is_dir():
                continue
            match = re.match(r"tasks_(\d+)_constraints_(\d+)", test_case.name)
            if match is None:
                continue
            num_tasks, num_constraints = map(int, match.groups())
            if num_tasks < min_task_count or num_constraints < min_constraint_count:
                continue
            for scene_name in target_scenes:
                scene_folder = test_case / scene_name
                if not scene_folder.is_dir():
                    continue
                instruction_files = sorted(
                    scene_folder.glob("*.json"),
                    key=lambda path: path.name,
                )
                case_instruction_mapping[test_case.name][scene_name].extend(
                    [(str(path), task_folder_name) for path in instruction_files]
                )
    if not case_instruction_mapping:
        logger.warning("No cases found in any provided task folders.")
    return case_instruction_mapping


def _iter_states_dirs(
    config: Mapping[str, Any],
    task_folder_name: str | None = None,
) -> list[Path]:
    """Return candidate result state directories for AI2-THOR skip checks."""

    base_path = RESULT_PATH / task_folder_name if task_folder_name else RESULT_PATH
    init_prior = config.get("init_prior_mean")
    if isinstance(init_prior, (int, float)):
        return [base_path / f"states{int(init_prior)}"]
    if not base_path.exists():
        return []
    return [
        path
        for path in base_path.iterdir()
        if path.is_dir() and path.name.startswith("states")
    ]


def _find_latest_result_json_for_task(
    baseline_path: Path,
    instruction_path: str,
    scene_name: str,
    config: Mapping[str, Any],
    case_name: str | None = None,
    ablation_name: str | None = None,
    task_folder_name: str | None = None,
) -> Path | None:
    """Locate the latest AI2-THOR result JSON for an instruction."""

    if "dag_bayesian" in baseline_path.name and case_name and ablation_name:
        approach_name = f"dag_bayesian_{ablation_name}"
    else:
        suffix = "_simulation" if config.get("simulation", False) else ""
        approach_name = f"{baseline_path.stem}{suffix}"
    approach_names = [approach_name]
    if approach_name.endswith("_simulation"):
        approach_names.append(approach_name.replace("_simulation", ""))
    raw_stem = Path(instruction_path).stem
    instruction_keys: list[str] = []
    for key in (raw_stem, raw_stem.replace(" ", "_")):
        if key not in instruction_keys:
            instruction_keys.append(key)
    candidates: list[tuple[int, Path]] = []
    for state_dir in _iter_states_dirs(config, task_folder_name):
        base_dir = state_dir / case_name if case_name else state_dir
        if not base_dir.exists():
            continue
        for key in instruction_keys:
            exact_dir = base_dir / key
            if exact_dir.is_dir():
                for approach_name_variant in approach_names:
                    json_path = (
                        exact_dir / scene_name / approach_name_variant / "end_state.json"
                    )
                    if json_path.exists():
                        candidates.append((0, json_path))
            for task_dir in base_dir.glob(f"{key}_*"):
                if not task_dir.is_dir():
                    continue
                match = re.search(r"_(\d+)$", task_dir.name)
                if match is None:
                    continue
                for approach_name_variant in approach_names:
                    json_path = (
                        task_dir
                        / scene_name
                        / approach_name_variant
                        / "end_state.json"
                    )
                    if json_path.exists():
                        candidates.append((int(match.group(1)), json_path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def should_skip_completed_for_task(
    baseline_path: Path,
    instruction_path: str,
    scene_name: str,
    config: Mapping[str, Any],
    case_name: str | None = None,
    ablation_name: str | None = None,
    task_folder_name: str | None = None,
) -> tuple[bool, Path | None]:
    """Return whether an AI2-THOR task already has a saved result."""

    if not config.get("skip_completed"):
        return False, None
    result_json = _find_latest_result_json_for_task(
        baseline_path=baseline_path,
        instruction_path=instruction_path,
        scene_name=scene_name,
        config=config,
        case_name=case_name,
        ablation_name=ablation_name,
        task_folder_name=task_folder_name,
    )
    if result_json is not None and result_json.exists():
        return True, result_json
    return False, None


def build_ai2thor_tasks(
    config: Mapping[str, Any],
    *,
    run_timestamp: str,
    logger: logging.Logger,
) -> list[BatchTask]:
    """Build subprocess tasks for AI2-THOR simulation or ROS experiments."""

    is_simulation = bool(config.get("simulation", False))
    cloud_rendering = bool(config.get("cloud_rendering", False))
    num_runs_per_instruction = int(config.get("num_runs_per_instruction", 1))
    max_retries = int(config.get("max_retries", 1))
    num_gpus = int(config.get("num_gpus", 0))
    sched_baselines = [
        (BaselineType.SCHEDULER, _resolve_repo_path(path_like))
        for path_like in config.get("approaches", [])
    ]
    llm_baselines = [
        (BaselineType.LLM, _resolve_repo_path(path_like))
        for path_like in config.get("llm_scripts", [])
    ]
    baselines = sched_baselines + llm_baselines
    scene_types_config = config.get("scene_type", "kitchen")
    scene_types = (
        [scene_types_config]
        if isinstance(scene_types_config, str)
        else list(scene_types_config)
    )
    scene_lists = dict(config.get("scene_lists", {}))
    target_scenes = [
        scene for scene_type in scene_types for scene in scene_lists.get(scene_type, [])
    ]
    case_instruction_mapping = load_instruction_case_mapping_from_scenes(
        target_scenes=target_scenes,
        task_folder_names=config.get(
            "task_folder_name", "decomposed_rightbefore_final_251031"
        ),
        logger=logger,
        min_task_count=int(config.get("min_task_count", 0)),
        min_constraint_count=int(config.get("min_constraint_count", 0)),
    )
    ablation_names_to_run = list(config.get("ablation_configs", []))
    if ablation_names_to_run:
        ablation_configs_to_run = {
            name: AblationConfig[name].value
            for name in ablation_names_to_run
            if name in AblationConfig.__members__
        }
    else:
        ablation_configs_to_run = {
            name: enum_member.value
            for name, enum_member in AblationConfig.__members__.items()
        }
    init_prior_names_to_run = list(config.get("init_prior_configs", []))
    if init_prior_names_to_run:
        init_prior_configs_to_run = {
            name: InitPriorConfig[name].value
            for name in init_prior_names_to_run
            if name in InitPriorConfig.__members__
        }
    else:
        init_prior_configs_to_run = {
            name: enum_member.value
            for name, enum_member in InitPriorConfig.__members__.items()
        }
    if not ablation_configs_to_run:
        ablation_configs_to_run = {"DEFAULT": {}}
    if not init_prior_configs_to_run:
        init_prior_configs_to_run = {"DEFAULT": {}}
    execute_dict = dict(config.get("execute_dict", {}))
    tasks_to_run: list[BatchTask] = []
    gpu_counter = 0
    for baseline_type, baseline_path in baselines:
        ablations_to_use = ablation_configs_to_run
        if "dag_bayesian.py" not in str(baseline_path):
            ablations_to_use = {"DEFAULT": AblationConfig.DEFAULT.value}
        for (
            (ablation_name, ablation_params),
            (init_prior_name, init_prior_params),
            (case_name, scene_map),
        ) in product(
            ablations_to_use.items(),
            init_prior_configs_to_run.items(),
            case_instruction_mapping.items(),
        ):
            for scene_name, instructions in scene_map.items():
                for instruction_path, task_src_folder_name in instructions:
                    instruction_file = Path(instruction_path)
                    if execute_dict:
                        if case_name not in execute_dict:
                            continue
                        if scene_name not in execute_dict[case_name]:
                            continue
                        if (
                            instruction_file.name
                            not in execute_dict[case_name][scene_name]
                        ):
                            continue
                    merged_skip_config = {**dict(config), **dict(init_prior_params)}
                    should_skip, found_json = should_skip_completed_for_task(
                        baseline_path=baseline_path,
                        instruction_path=instruction_path,
                        scene_name=scene_name,
                        config=merged_skip_config,
                        case_name=case_name,
                        ablation_name=ablation_name,
                        task_folder_name=task_src_folder_name,
                    )
                    if should_skip:
                        logger.critical(
                            "Skip completed: %s | %s | '%s' -> %s",
                            scene_name,
                            baseline_path.stem,
                            instruction_file.stem,
                            found_json,
                        )
                        continue
                    for try_idx in range(num_runs_per_instruction):
                        gpu_id = -1
                        if num_gpus > 0:
                            gpu_id = gpu_counter % num_gpus
                            gpu_counter += 1
                        log_file_name = (
                            f"{baseline_path.stem}_{ablation_name}_{init_prior_name}_"
                            f"{case_name}_{scene_name}_{instruction_file.stem}_{try_idx + 1}.log"
                        )
                        command = [
                            str(SCRIPTS_PATH / "run_project.sh"),
                            "python3",
                            str(baseline_path),
                            "--scene",
                            scene_name,
                            "--case",
                            case_name,
                            "--ablation-name",
                            ablation_name,
                            "--instruction",
                            instruction_file.name,
                            "--log-path",
                            str(
                                LOG_PATH
                                / f"{run_timestamp}-worker_logs"
                                / log_file_name
                            ),
                            "--task-folder-name",
                            task_src_folder_name,
                        ]
                        if is_simulation:
                            command.append("--simulation")
                            if cloud_rendering:
                                command.append("--cloud-rendering")
                        else:
                            command.append("--ros")
                        for key, value in (dict(ablation_params) | dict(init_prior_params)).items():
                            _append_flag(command, f"--{key}", value)
                        tasks_to_run.append(
                            BatchTask(
                                name=f"{baseline_path.stem}:{instruction_file.stem}:{try_idx + 1}",
                                command=command,
                                log_path=LOG_PATH
                                / f"{run_timestamp}-worker_logs"
                                / log_file_name,
                                metadata={
                                    "mode": "ai2thor",
                                    "baseline": baseline_path.name,
                                    "ablation": ablation_name,
                                    "prior": init_prior_name,
                                    "case": case_name,
                                    "scene": scene_name,
                                    "instruction": instruction_file.name,
                                    "run": str(try_idx + 1),
                                },
                                max_retries=max_retries,
                                retry_delay_seconds=(
                                    10.0 if baseline_type == BaselineType.SCHEDULER else (2.0 if is_simulation else 30.0)
                                ),
                                startup_delay_seconds=(
                                    0.0 if is_simulation or baseline_type != BaselineType.SCHEDULER else 10.0
                                ),
                                gpu_id=gpu_id,
                                reset_ros_state=not is_simulation,
                                cwd=PROJECT_ROOT,
                            )
                        )
    logger.critical("Found %s AI2-THOR tasks to run.", len(tasks_to_run))
    return tasks_to_run


def _build_offline_options(config: Mapping[str, Any]) -> OfflineBatchOptions:
    """Normalize offline YAML config into a typed options object."""

    base_config_path = config.get("base_config")
    resolved_base_config_path = (
        _resolve_repo_path(base_config_path) if base_config_path is not None else None
    )
    base_config = load_experiment_config(resolved_base_config_path)
    planner_types = list(config.get("planner_types", [base_config.planner_type]))
    cases = list(config.get("cases", []))
    if not cases and config.get("case") is not None:
        cases = [str(config["case"])]
    if not cases:
        cases = list(base_config.cases) or [base_config.case]
    scenes = list(config.get("scenes", []))
    if not scenes and config.get("scene") is not None:
        scenes = [str(config["scene"])]
    if not scenes:
        scenes = [base_config.scene]
    if not scenes:
        raise ValueError("Offline config must provide 'scene' or 'scenes'.")
    raw_task_folder_names = config.get("task_folder_name", base_config.task_folder_name)
    if isinstance(raw_task_folder_names, str):
        task_folder_names = [raw_task_folder_names]
    else:
        task_folder_names = [str(value) for value in raw_task_folder_names]
    output_dir = _resolve_repo_path(
        config.get("output_dir", "assets/results/offline_batch")
    )
    return OfflineBatchOptions(
        base_config_path=resolved_base_config_path,
        command=str(config.get("command", "run")),
        planner_types=planner_types,
        task_folder_names=task_folder_names,
        cases=cases,
        scenes=scenes,
        instructions=list(config.get("instructions", base_config.instructions)),
        max_tasks=config.get("max_tasks", base_config.max_tasks),
        beam_width_values=[
            int(value)
            for value in config.get("beam_width_values", base_config.beam_width_values)
        ],
        beam_depth_values=[
            int(value)
            for value in config.get("beam_depth_values", base_config.beam_depth_values)
        ],
        nav_graph_source=config.get("nav_graph_source", base_config.nav_graph_source),
        output_dir=output_dir,
        experiment_name=config.get("experiment_name", base_config.experiment_name),
        disable_monitoring=bool(
            config.get("disable_monitoring", base_config.disable_monitoring)
        ),
        gt_distribution=config.get("gt_distribution", base_config.gt_distribution),
        gt_seed=config.get("gt_seed", base_config.gt_seed),
        init_prior_mean=config.get("init_prior_mean", base_config.init_prior_mean),
        init_prior_variance=config.get(
            "init_prior_variance", base_config.init_prior_variance
        ),
        factor_alpha=config.get("factor_alpha", base_config.factor_alpha),
        bayesian_threshold_probability=config.get(
            "bayesian_threshold_probability",
            base_config.bayesian_threshold_probability,
        ),
        oracle_time_limit_seconds=config.get(
            "oracle_time_limit_seconds", base_config.oracle_time_limit_seconds
        ),
        skip_completed=bool(config.get("skip_completed", True)),
        timeout_seconds=int(config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        tags=[str(tag) for tag in config.get("tags", base_config.tags)],
    )


def _make_offline_config(
    options: OfflineBatchOptions,
    *,
    task_folder_name: str,
    planner_type: str,
    scene_name: str,
    case_name: str,
) -> OfflineExperimentConfig:
    """Build an effective offline experiment config for task discovery."""

    base_config = load_experiment_config(options.base_config_path)
    payload = asdict(base_config)
    payload.update(
        {
            "planner_type": planner_type,
            "scene": scene_name,
            "case": case_name,
            "cases": [case_name],
            "task_folder_name": task_folder_name,
            "beam_width_values": list(options.beam_width_values),
            "beam_depth_values": list(options.beam_depth_values),
            "instructions": list(options.instructions),
            "max_tasks": options.max_tasks,
            "experiment_name": options.experiment_name or base_config.experiment_name,
            "tags": list(options.tags) or list(base_config.tags),
            "disable_monitoring": options.disable_monitoring,
            "gt_distribution": (
                options.gt_distribution
                if options.gt_distribution is not None
                else base_config.gt_distribution
            ),
            "gt_seed": options.gt_seed if options.gt_seed is not None else base_config.gt_seed,
            "nav_graph_source": (
                options.nav_graph_source
                if options.nav_graph_source is not None
                else base_config.nav_graph_source
            ),
        }
    )
    if options.init_prior_mean is not None:
        payload["init_prior_mean"] = options.init_prior_mean
    if options.init_prior_variance is not None:
        payload["init_prior_variance"] = options.init_prior_variance
    if options.factor_alpha is not None:
        payload["factor_alpha"] = options.factor_alpha
    if options.bayesian_threshold_probability is not None:
        payload["bayesian_threshold_probability"] = (
            options.bayesian_threshold_probability
        )
    if options.oracle_time_limit_seconds is not None:
        payload["oracle_time_limit_seconds"] = options.oracle_time_limit_seconds
    return OfflineExperimentConfig(**payload)


def _build_offline_output_path(
    options: OfflineBatchOptions,
    *,
    task_folder_name: str | None,
    planner_type: str,
    scene_name: str,
    case_name: str | None,
    instruction_name: str | None,
) -> Path:
    """Construct a deterministic JSON report path for one offline subprocess."""

    case_token = _sanitize_token(case_name) if case_name is not None else "multi_case"
    instruction_token = (
        _sanitize_token(Path(instruction_name).stem)
        if instruction_name is not None
        else "aggregate"
    )
    task_folder_token = (
        _sanitize_token(task_folder_name) if task_folder_name is not None else "default"
    )
    filename = (
        f"offline_{options.command}_{task_folder_token}_{_sanitize_token(planner_type)}_"
        f"{_sanitize_token(scene_name)}_{case_token}_{instruction_token}.json"
    )
    return options.output_dir / filename


def _is_completed_offline_report(report_path: Path) -> bool:
    """Return whether an offline report exists and looks usable."""

    if not report_path.exists():
        return False
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    return bool(payload)


def build_offline_tasks(
    config: Mapping[str, Any],
    *,
    run_timestamp: str,
    logger: logging.Logger,
) -> list[BatchTask]:
    """Build subprocess tasks for offline experiment batches."""

    options = _build_offline_options(config)
    offline_script_path = PROJECT_ROOT / "scripts/offline_experiment.py"
    worker_log_dir = LOG_PATH / f"{run_timestamp}-worker_logs"
    tasks: list[BatchTask] = []
    if options.command == "oracle-compare":
        if not options.cases:
            raise ValueError("Offline oracle-compare requires 'cases'.")
        for task_folder_name, planner_type, scene_name in product(
            options.task_folder_names,
            options.planner_types,
            options.scenes,
        ):
            output_path = _build_offline_output_path(
                options,
                task_folder_name=task_folder_name,
                planner_type=planner_type,
                scene_name=scene_name,
                case_name="_".join(options.cases),
                instruction_name=None,
            )
            if options.skip_completed and _is_completed_offline_report(output_path):
                logger.critical("Skip completed offline report: %s", output_path)
                continue
            command = [
                os.environ.get("PYTHON", sys.executable),
                str(offline_script_path),
            ]
            if options.base_config_path is not None:
                command.extend(["--config", str(options.base_config_path)])
            _append_flag(command, "--offline-command", "oracle-compare")
            _append_flag(command, "--planner-type", planner_type)
            _append_flag(command, "--task-folder-name", task_folder_name)
            _append_flag(command, "--cases", options.cases)
            _append_flag(command, "--scene", scene_name)
            _append_flag(command, "--beam-width-values", options.beam_width_values)
            _append_flag(command, "--beam-depth-values", options.beam_depth_values)
            _append_flag(command, "--nav-graph-source", options.nav_graph_source)
            _append_flag(command, "--gt-distribution", options.gt_distribution)
            _append_flag(command, "--gt-seed", options.gt_seed)
            _append_flag(command, "--init-prior-mean", options.init_prior_mean)
            _append_flag(
                command,
                "--init-prior-variance",
                options.init_prior_variance,
            )
            _append_flag(command, "--factor-alpha", options.factor_alpha)
            _append_flag(
                command,
                "--bayesian-threshold-probability",
                options.bayesian_threshold_probability,
            )
            _append_flag(
                command,
                "--experiment-name",
                options.experiment_name or f"offline_oracle_{planner_type}",
            )
            _append_flag(
                command,
                "--log-path",
                worker_log_dir
                / f"offline_oracle_{_sanitize_token(task_folder_name)}_{planner_type}_{scene_name}.log",
            )
            _append_flag(command, "--output-path", output_path)
            _append_flag(
                command,
                "--oracle-time-limit-seconds",
                options.oracle_time_limit_seconds,
            )
            if options.disable_monitoring:
                command.append("--disable-monitoring")
            tasks.append(
                BatchTask(
                    name=f"offline-oracle:{task_folder_name}:{planner_type}:{scene_name}",
                    command=command,
                    log_path=worker_log_dir
                    / f"offline_oracle_{_sanitize_token(task_folder_name)}_{planner_type}_{scene_name}.log",
                    metadata={
                        "mode": "offline",
                        "task_folder": task_folder_name,
                        "command": "oracle-compare",
                        "planner": planner_type,
                        "scene": scene_name,
                        "cases": ",".join(options.cases),
                    },
                    max_retries=1,
                    timeout_seconds=options.timeout_seconds,
                    cwd=PROJECT_ROOT,
                )
            )
        return tasks

    for task_folder_name, planner_type, scene_name, case_name in product(
        options.task_folder_names,
        options.planner_types,
        options.scenes,
        options.cases,
    ):
        try:
            offline_config = _make_offline_config(
                options,
                task_folder_name=task_folder_name,
                planner_type=planner_type,
                scene_name=scene_name,
                case_name=case_name,
            )
            instruction_names = resolve_instructions(offline_config, case_name)
        except FileNotFoundError as exc:
            logger.warning(
                "Skipping offline task discovery for folder='%s', case='%s', scene='%s': %s",
                task_folder_name,
                case_name,
                scene_name,
                exc,
            )
            continue
        for instruction_name in instruction_names:
            output_path = _build_offline_output_path(
                options,
                task_folder_name=task_folder_name,
                planner_type=planner_type,
                scene_name=scene_name,
                case_name=case_name,
                instruction_name=instruction_name,
            )
            if options.skip_completed and _is_completed_offline_report(output_path):
                logger.critical("Skip completed offline report: %s", output_path)
                continue
            command = [os.environ.get("PYTHON", sys.executable), str(offline_script_path)]
            if options.base_config_path is not None:
                command.extend(["--config", str(options.base_config_path)])
            _append_flag(command, "--offline-command", "run")
            _append_flag(command, "--planner-type", planner_type)
            _append_flag(command, "--task-folder-name", task_folder_name)
            _append_flag(command, "--case", case_name)
            _append_flag(command, "--scene", scene_name)
            _append_flag(command, "--instruction", instruction_name)
            _append_flag(command, "--beam-width-values", options.beam_width_values)
            _append_flag(command, "--beam-depth-values", options.beam_depth_values)
            _append_flag(command, "--nav-graph-source", options.nav_graph_source)
            _append_flag(command, "--gt-distribution", options.gt_distribution)
            _append_flag(command, "--gt-seed", options.gt_seed)
            _append_flag(command, "--init-prior-mean", options.init_prior_mean)
            _append_flag(
                command,
                "--init-prior-variance",
                options.init_prior_variance,
            )
            _append_flag(command, "--factor-alpha", options.factor_alpha)
            _append_flag(
                command,
                "--bayesian-threshold-probability",
                options.bayesian_threshold_probability,
            )
            _append_flag(
                command,
                "--experiment-name",
                options.experiment_name or f"offline_batch_{planner_type}",
            )
            _append_flag(
                command,
                "--log-path",
                worker_log_dir
                / (
                    f"offline_run_{_sanitize_token(task_folder_name)}_"
                    f"{planner_type}_{case_name}_{scene_name}_"
                    f"{Path(instruction_name).stem}.log"
                ),
            )
            _append_flag(command, "--output-path", output_path)
            if options.disable_monitoring:
                command.append("--disable-monitoring")
            tasks.append(
                BatchTask(
                    name=(
                        f"offline-run:{task_folder_name}:{planner_type}:"
                        f"{case_name}:{instruction_name}"
                    ),
                    command=command,
                    log_path=worker_log_dir
                    / (
                        f"offline_run_{_sanitize_token(task_folder_name)}_"
                        f"{planner_type}_{case_name}_{scene_name}_"
                        f"{Path(instruction_name).stem}.log"
                    ),
                    metadata={
                        "mode": "offline",
                        "task_folder": task_folder_name,
                        "command": "run",
                        "planner": planner_type,
                        "case": case_name,
                        "scene": scene_name,
                        "instruction": instruction_name,
                    },
                    max_retries=1,
                    timeout_seconds=options.timeout_seconds,
                    cwd=PROJECT_ROOT,
                )
            )
    logger.critical("Found %s offline tasks to run.", len(tasks))
    return tasks


def generate_run_timestamp() -> str:
    """Return a stable timestamp string for one batch session."""

    return datetime.now().strftime("%Y%m%d_%H%M")
