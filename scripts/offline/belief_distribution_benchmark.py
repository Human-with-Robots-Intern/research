"""Run a scheduler-free PF-vs-Bayesian robustness benchmark."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

# parents[0]=offline, parents[1]=scripts, parents[2]=repo root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.experiments.belief_robustness import (
    BeliefBenchmarkConfig,
    belief_benchmark_config_and_script_options_from_flat_mapping,
    run_belief_robustness_benchmark,
    save_belief_robustness_results,
    save_reviewer10_comparison_results,
)
from assets.result_analysis.belief_robustness_tables import (
    render_belief_robustness_tables,
    save_rendered_tables,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the belief robustness benchmark."""

    parser = argparse.ArgumentParser(
        description=(
            "Scheduler-free PF-vs-Bayesian robustness benchmark (shape-stress GT "
            "only; sequential monitoring observations)."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "YAML file whose keys match ``BeliefBenchmarkConfig`` plus optional "
            "``output_dir``, ``reviewer10_comparison``, ``latex_dir``. CLI flags "
            "override YAML when both are set."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where summary JSON/CSV files will be written.",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=None,
        help="Monte Carlo episodes per cell (default: 200).",
    )
    parser.add_argument(
        "--base-duration",
        type=float,
        default=None,
        help="Reference duration used to scale prior settings and GT means (default: 100.0).",
    )
    parser.add_argument(
        "--gt-variance",
        type=float,
        default=None,
        help="Optional fixed variance for GT sampling. If omitted, family-specific defaults are used.",
    )
    parser.add_argument(
        "--observation-alpha",
        type=float,
        default=None,
        help=(
            "Override the synthetic observation variance scale "
            "(factor alpha) used by the scheduler-free benchmark."
        ),
    )
    parser.add_argument(
        "--etas",
        nargs="+",
        type=float,
        default=None,
        help="Monitoring quantiles to evaluate.",
    )
    parser.add_argument(
        "--gt-mean-multipliers",
        nargs="+",
        type=float,
        default=None,
        help="Multipliers applied to base duration to define GT means.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Belief-update backends to compare.",
    )
    parser.add_argument(
        "--observation-families",
        nargs="+",
        default=None,
        help="Observation likelihood families shared across compared methods.",
    )
    parser.add_argument(
        "--max-sequential-observations",
        type=int,
        default=None,
        help="Cap on sequential monitoring observation iterations per episode.",
    )
    parser.add_argument(
        "--particle-count",
        type=int,
        default=None,
        help="Number of particles used by the PF backend.",
    )
    parser.add_argument(
        "--pf-particle-distributions",
        nargs="+",
        default=None,
        help="Particle initialization families compared for the PF backend.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Master random seed (default: 42).",
    )
    parser.add_argument(
        "--no-episode-csv",
        action="store_true",
        help="Skip episode-level CSV export and keep only summary outputs.",
    )
    parser.add_argument(
        "--reviewer10-comparison",
        action="store_true",
        help="Write reviewer-facing comparison CSVs in addition to the raw benchmark outputs.",
    )
    parser.add_argument(
        "--latex-dir",
        type=Path,
        default=None,
        help="Optional output directory for belief robustness LaTeX tables.",
    )
    return parser.parse_args(argv)


def _safe_load_yaml_mapping(config_path: Path | None) -> dict[str, Any]:
    """Load a YAML file into a flat top-level mapping for the belief benchmark.

    Args:
        config_path: Path to YAML, or ``None`` for an empty mapping.

    Returns:
        A shallow ``dict`` copy of the top-level mapping.

    Raises:
        TypeError: If the YAML root is not a mapping.
        OSError: If the file cannot be read.
    """

    if config_path is None:
        return {}
    raw_text = Path(config_path).expanduser().read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw_text)
    if loaded is None:
        return {}
    if not isinstance(loaded, Mapping):
        msg = (
            "Belief benchmark config YAML must be a mapping at the top level; "
            f"got {type(loaded).__name__}."
        )
        raise TypeError(msg)
    return dict(loaded)


def _resolve_cli_defaults(args: argparse.Namespace) -> tuple[BeliefBenchmarkConfig, Path, bool, Path | None]:
    """Resolve YAML (optional) and CLI overrides on top of shape-stress defaults."""

    yaml_payload = _safe_load_yaml_mapping(args.config)
    yaml_config, script_opts = belief_benchmark_config_and_script_options_from_flat_mapping(
        yaml_payload
    )

    # Collect only the CLI arguments that were explicitly provided.
    overrides: dict[str, Any] = {}
    if args.methods is not None:
        overrides["methods"] = tuple(args.methods)
    if args.etas is not None:
        overrides["etas"] = tuple(args.etas)
    if args.gt_mean_multipliers is not None:
        overrides["gt_mean_multipliers"] = tuple(args.gt_mean_multipliers)
    if args.max_sequential_observations is not None:
        overrides["max_sequential_observations"] = int(args.max_sequential_observations)
    if args.observation_families is not None:
        overrides["observation_families"] = tuple(args.observation_families)
    if args.pf_particle_distributions is not None:
        overrides["particle_distributions"] = tuple(args.pf_particle_distributions)
    if args.particle_count is not None:
        overrides["particle_count"] = int(args.particle_count)
    if args.episodes is not None:
        overrides["episode_count"] = int(args.episodes)
    if args.base_duration is not None:
        overrides["base_duration"] = float(args.base_duration)
    if args.gt_variance is not None:
        overrides["gt_variance"] = float(args.gt_variance)
    if args.observation_alpha is not None:
        overrides["observation_alpha"] = float(args.observation_alpha)
    if args.seed is not None:
        overrides["random_seed"] = int(args.seed)
    if args.no_episode_csv:
        overrides["write_episode_rows"] = False

    config = replace(yaml_config, **overrides)

    default_output = Path(
        "assets/results/offline_exp_result/belief_distribution_benchmark"
    )
    output_dir: Path
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    elif script_opts.get("output_dir") is not None:
        output_dir = Path(script_opts["output_dir"])
    else:
        output_dir = default_output

    yaml_reviewer10 = bool(script_opts.get("reviewer10_comparison", False))
    yaml_latex = script_opts.get("latex_dir")
    emit_reviewer10_outputs = bool(
        args.reviewer10_comparison
        or yaml_reviewer10
        or args.latex_dir is not None
        or yaml_latex is not None
    )

    latex_dir: Path | None
    if args.latex_dir is not None:
        latex_dir = Path(args.latex_dir)
    elif yaml_latex is not None:
        latex_dir = Path(yaml_latex)
    elif emit_reviewer10_outputs:
        latex_dir = output_dir / "latex_tables"
    else:
        latex_dir = None

    return config, Path(output_dir), emit_reviewer10_outputs, latex_dir


def main(argv: Sequence[str] | None = None) -> None:
    """Run the benchmark and write result artifacts."""

    args = parse_args(argv)
    config, output_dir, emit_reviewer10_outputs, latex_dir = _resolve_cli_defaults(args)
    results = run_belief_robustness_benchmark(config)
    written_paths = save_belief_robustness_results(
        results,
        output_dir=output_dir,
        write_episode_rows=config.write_episode_rows,
    )
    if emit_reviewer10_outputs:
        written_paths.update(
            save_reviewer10_comparison_results(results, output_dir=output_dir)
        )
        if latex_dir is not None:
            written_paths.update(
                {
                    f"latex_{path.name}": path
                    for path in save_rendered_tables(
                        render_belief_robustness_tables(
                            results["summary_rows"],
                            eta=float(config.etas[0]),
                        ),
                        latex_dir,
                    )
                }
            )
    for label, path in written_paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
