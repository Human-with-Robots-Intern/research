#!/usr/bin/env python3
"""Utility to run `scripts/run_all.py` with multiple INIT_PRIOR_MEAN settings."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_PATH = REPO_ROOT / "src" / "utils" / "config" / "constants.py"
RUN_ALL_PATH = Path(__file__).resolve().parent / "run_all.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run `run_all.py` experiments for multiple INIT_PRIOR_MEAN values while "
            "keeping GT_INTERVAL fixed at a desired value."
        )
    )
    parser.add_argument(
        "--means",
        type=float,
        nargs="+",
        default=[80.0, 100.0, 120.0],
        help="INIT_PRIOR_MEAN values to sweep.",
    )
    parser.add_argument(
        "--gt",
        type=float,
        default=100.0,
        help="Ground-truth interval to inject (GT_INTERVAL).",
    )
    parser.add_argument(
        "--tag-template",
        default="prior_mean_{mean}",
        help=(
            "Template for per-run suffix used under logs/ and assets/results/. "
            "Set to an empty string to reuse the default directories."
        ),
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort the sweep as soon as one run_all invocation fails.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned commands without executing run_all.py.",
    )
    return parser.parse_args()


def _format_scalar(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):.1f}"
    return f"{value}"


def _format_tag(mean: float) -> str:
    rounded = round(mean)
    if abs(mean - rounded) < 1e-9:
        mean_str = str(rounded)
    else:
        mean_str = str(mean).replace(".", "_")
    return mean_str


def _replace_assignment(content: str, name: str, expr: str) -> str:
    pattern = rf"^(?P<lhs>{name}\s*=\s*).*$"
    replacement = rf"\g<lhs>{expr}"
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count == 0:
        raise ValueError(f"Failed to locate assignment for {name} in constants.py")
    return updated


def prepare_constants(
    baseline_content: str,
    init_prior_mean: float,
    gt_interval: float,
    tag: str | None,
) -> str:
    """Return constants.py content with updated INIT/GT and optional log/result suffix."""
    content = _replace_assignment(
        baseline_content,
        "INIT_PRIOR_MEAN",
        _format_scalar(init_prior_mean),
    )
    content = _replace_assignment(
        content,
        "GT_INTERVAL",
        _format_scalar(gt_interval),
    )

    if tag:
        result_expr = f'ASSETS_PATH / "results" / "{tag}"'
        log_expr = f'ROOT_PATH / "logs" / "{tag}"'
        content = _replace_assignment(content, "RESULT_PATH", result_expr)
        content = _replace_assignment(content, "LOG_PATH", log_expr)
    else:
        # Ensure original paths are restored when tag is empty by working off the baseline
        content = baseline_content
        content = _replace_assignment(
            content,
            "INIT_PRIOR_MEAN",
            _format_scalar(init_prior_mean),
        )
        content = _replace_assignment(
            content,
            "GT_INTERVAL",
            _format_scalar(gt_interval),
        )
    return content


def ensure_directories(tag: str | None) -> None:
    if not tag:
        return
    (REPO_ROOT / "logs" / tag).mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "assets" / "results" / tag).mkdir(parents=True, exist_ok=True)


def run_experiments(
    means: Iterable[float],
    gt: float,
    tag_template: str,
    dry_run: bool,
    stop_on_error: bool,
) -> None:
    baseline_content = CONSTANTS_PATH.read_text(encoding="utf-8")
    try:
        for mean in means:
            tag = None
            if tag_template:
                tag = tag_template.format(mean=_format_tag(mean))

            updated_content = prepare_constants(baseline_content, mean, gt, tag)
            CONSTANTS_PATH.write_text(updated_content, encoding="utf-8")
            ensure_directories(tag)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"[{now}] INIT_PRIOR_MEAN={mean} GT_INTERVAL={gt} tag={tag or 'default'}"
            )

            if dry_run:
                print(f"  dry-run: {sys.executable} {RUN_ALL_PATH}")
                continue

            result = subprocess.run(
                [sys.executable, str(RUN_ALL_PATH)], check=False, cwd=str(REPO_ROOT)
            )

            if result.returncode != 0:
                msg = f"run_all.py failed for INIT_PRIOR_MEAN={mean} with return code {result.returncode}"
                print(msg)
                if stop_on_error:
                    raise subprocess.CalledProcessError(result.returncode, result.args)
    finally:
        CONSTANTS_PATH.write_text(baseline_content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    run_experiments(
        means=args.means,
        gt=args.gt,
        tag_template=args.tag_template,
        dry_run=args.dry_run,
        stop_on_error=args.stop_on_error,
    )


if __name__ == "__main__":
    main()
