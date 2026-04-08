"""CLI entrypoint for in-process offline scheduler experiments."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.experiments.offline_compare import compare_result_files, save_comparison_report
from src.experiments.offline_harness import (
    ExperimentConfig,
    apply_cli_overrides,
    iter_oracle_report_lines,
    iter_report_lines,
    load_experiment_config,
    run_grid_experiment,
    run_oracle_comparison_experiment,
    save_experiment_report,
)

SUBCOMMAND_CHOICES = {"run", "oracle-compare", "compare"}


def _add_common_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Register shared CLI arguments for offline runs."""

    parser.add_argument("--config", type=str, default=None, help="JSON/YAML config path.")
    parser.add_argument("--experiment-name", type=str, default=None)
    parser.add_argument("--task-folder-name", type=str, default=None)
    parser.add_argument(
        "--planner-type",
        type=str,
        choices=["bayesian", "edf", "cpm"],
        default=None,
    )
    parser.add_argument("--case", type=str, default=None)
    parser.add_argument("--cases", nargs="+", default=None)
    parser.add_argument("--scene", type=str, default=None)
    parser.add_argument("--instructions", nargs="*", default=None)
    parser.add_argument("--max-tasks", type=int, default=None)
    parser.add_argument("--beam-width-values", nargs="+", type=int, default=None)
    parser.add_argument("--beam-depth-values", nargs="+", type=int, default=None)
    parser.add_argument("--belief-update-method", type=str, default=None)
    parser.add_argument("--gt-distribution", type=str, default=None)
    parser.add_argument("--gt-seed", type=int, default=None)
    parser.add_argument("--init-prior-mean", type=float, default=None)
    parser.add_argument("--init-prior-variance", type=float, default=None)
    parser.add_argument("--disable-monitoring", action="store_true")
    parser.add_argument("--factor-alpha", type=float, default=None)
    parser.add_argument("--bayesian-threshold-probability", type=float, default=None)
    parser.add_argument(
        "--nav-graph-source",
        type=str,
        choices=["synthetic_grid", "ai2thor_controller"],
        default=None,
    )
    parser.add_argument("--output-path", type=str, default=None)
    parser.add_argument("--oracle-time-limit-seconds", type=float, default=None)


def _build_subcommand_parser() -> argparse.ArgumentParser:
    """Build the existing subcommand-based parser."""

    parser = argparse.ArgumentParser(description="Offline scheduler experiment harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an offline experiment grid.")
    _add_common_run_arguments(run_parser)

    oracle_parser = subparsers.add_parser(
        "oracle-compare",
        help="Compare deterministic scheduler runs against an exact oracle.",
    )
    _add_common_run_arguments(oracle_parser)

    compare_parser = subparsers.add_parser("compare", help="Compare two result JSON files.")
    compare_parser.add_argument("--before", type=str, required=True)
    compare_parser.add_argument("--after", type=str, required=True)
    compare_parser.add_argument("--output-path", type=str, default=None)

    return parser


def _build_flat_parser() -> argparse.ArgumentParser:
    """Build a flat compatibility parser aligned with run_all-style flags."""

    parser = argparse.ArgumentParser(
        description="Offline scheduler experiment harness (flat compatibility mode)."
    )
    parser.add_argument(
        "--offline-command",
        choices=["run", "oracle-compare"],
        default="run",
        help="Offline command to execute in flat compatibility mode.",
    )
    _add_common_run_arguments(parser)
    parser.add_argument("--instruction", type=str, default=None)
    parser.add_argument("--log-path", type=str, default=None)
    parser.add_argument("--ablation-name", type=str, default=None)
    parser.add_argument("--simulation", action="store_true")
    parser.add_argument("--ros", action="store_true")
    parser.add_argument("--cloud-rendering", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--attempt", type=int, default=None)
    parser.add_argument("--log-level", type=str, default=None)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for both legacy and flat compatibility workflows."""

    cli_args = list(argv) if argv is not None else sys.argv[1:]
    if cli_args and cli_args[0] in SUBCOMMAND_CHOICES:
        parser = _build_subcommand_parser()
        parsed = parser.parse_args(cli_args)
        parsed.entry_mode = "subcommand"
        return parsed

    parser = _build_flat_parser()
    parsed = parser.parse_args(cli_args)
    parsed.command = parsed.offline_command
    if parsed.instruction and not parsed.instructions:
        parsed.instructions = [parsed.instruction]
    if parsed.command == "oracle-compare" and parsed.case and not parsed.cases:
        parsed.cases = [parsed.case]
    parsed.entry_mode = "flat"
    return parsed


def _build_run_config(args: argparse.Namespace) -> ExperimentConfig:
    """Build the effective run config from file defaults and CLI overrides."""

    base_config = load_experiment_config(
        Path(args.config).expanduser() if args.config else None
    )
    overrides: dict[str, Any] = {
        "experiment_name": args.experiment_name,
        "task_folder_name": args.task_folder_name,
        "planner_type": args.planner_type,
        "case": args.case,
        "cases": args.cases,
        "scene": args.scene,
        "instructions": args.instructions,
        "max_tasks": args.max_tasks,
        "beam_width_values": args.beam_width_values,
        "beam_depth_values": args.beam_depth_values,
        "belief_update_method": args.belief_update_method,
        "gt_distribution": args.gt_distribution,
        "gt_seed": args.gt_seed,
        "init_prior_mean": args.init_prior_mean,
        "init_prior_variance": args.init_prior_variance,
        "factor_alpha": args.factor_alpha,
        "bayesian_threshold_probability": args.bayesian_threshold_probability,
        "nav_graph_source": args.nav_graph_source,
        "output_path": args.output_path,
        "oracle_time_limit_seconds": args.oracle_time_limit_seconds,
    }
    merged = apply_cli_overrides(base_config, overrides)
    if args.disable_monitoring:
        merged = apply_cli_overrides(merged, {"disable_monitoring": True})
    return merged


def _run_command(args: argparse.Namespace) -> None:
    """Execute the run subcommand."""

    config = _build_run_config(args)
    report = run_grid_experiment(config)
    for line in iter_report_lines(report):
        print(line)
    if config.output_path:
        save_experiment_report(report, Path(config.output_path).expanduser())


def _compare_command(args: argparse.Namespace) -> None:
    """Execute the compare subcommand."""

    report = compare_result_files(
        Path(args.before).expanduser(),
        Path(args.after).expanduser(),
    )
    print(f"Improved settings: {len(report['improved_settings'])}")
    print(f"Regressed settings: {len(report['regressed_settings'])}")
    if args.output_path:
        save_comparison_report(report, Path(args.output_path).expanduser())


def _oracle_compare_command(args: argparse.Namespace) -> None:
    """Execute the oracle-compare subcommand."""

    config = _build_run_config(args)
    report = run_oracle_comparison_experiment(config)
    for line in iter_oracle_report_lines(report):
        print(line)
    if config.output_path:
        save_experiment_report(report, Path(config.output_path).expanduser())


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()
    if args.command == "run":
        _run_command(args)
        return
    if args.command == "oracle-compare":
        _oracle_compare_command(args)
        return
    _compare_command(args)


if __name__ == "__main__":
    main()
