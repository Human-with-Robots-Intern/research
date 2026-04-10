"""Tests for the offline experiment CLI surface."""

from __future__ import annotations

from pathlib import Path

from scripts.offline.offline_experiment import _build_run_config, parse_args
from src.experiments.offline_harness import load_experiment_config


def test_parse_args_accepts_new_offline_flags() -> None:
    """Parse the new run_all-style offline CLI flags."""

    args = parse_args(
        [
            "--approach",
            "edf",
            "--case",
            "tasks_3_constraints_2",
            "--scene",
            "FloorPlan13",
            "--instruction",
            "task_a.json",
            "--ablation-config",
            "NONE_MONITORING",
            "--init-prior-config",
            "OVER_ESTIMATE_110",
            "--beam-bound",
            "1,1",
            "5,5",
            "--eta",
            "0.35",
            "--nav-graph-source",
            "ai2thor_controller",
            "--oracle-time-limit-seconds",
            "300",
        ]
    )

    assert args.approach == "edf"
    assert args.ablation_config == "NONE_MONITORING"
    assert args.init_prior_config == "OVER_ESTIMATE_110"
    assert args.beam_bound == ["1,1", "5,5"]
    assert args.eta == 0.35
    assert args.nav_graph_source == "ai2thor_controller"
    assert args.oracle_time_limit_seconds == 300.0


def test_load_experiment_config_reads_new_field_names(tmp_path: Path) -> None:
    """Load offline config files that use only the new key vocabulary."""

    config_path = tmp_path / "offline.yaml"
    config_path.write_text(
        "\n".join(
            [
                "approach: bayesian",
                "ablation_config: NONE_MONITORING",
                "init_prior_config: OVER_ESTIMATE_110",
                "beam_bound:",
                "  - [1, 1]",
                "  - [5, 5]",
                "eta: 0.4",
                'nav_graph_source: "ai2thor_controller"',
                "oracle_time_limit_seconds: 300",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_experiment_config(config_path)

    assert loaded.approach == "bayesian"
    assert loaded.ablation_config == "NONE_MONITORING"
    assert loaded.init_prior_config == "OVER_ESTIMATE_110"
    assert loaded.beam_bound == [(1, 1), (5, 5)]
    assert loaded.eta == 0.4
    assert loaded.nav_graph_source == "ai2thor_controller"
    assert loaded.oracle_time_limit_seconds == 300


def test_build_run_config_uses_new_fields_without_legacy_aliases(tmp_path: Path) -> None:
    """Build the effective run config from the new CLI/config field names."""

    config_path = tmp_path / "offline.yaml"
    config_path.write_text(
        "\n".join(
            [
                "approach: bayesian",
                "ablation_config: DEFAULT",
                "init_prior_config: OVER_ESTIMATE_110",
                "beam_bound:",
                "  - [1, 1]",
                "eta: 0.2",
            ]
        ),
        encoding="utf-8",
    )

    args = parse_args(
        [
            "--config",
            str(config_path),
            "--approach",
            "cpm",
            "--ablation-config",
            "NONE_MONITORING",
            "--init-prior-config",
            "UNDER_ESTIMATE_90",
            "--beam-bound",
            "10,10",
            "--eta",
            "0.6",
        ]
    )

    config = _build_run_config(args)

    assert config.approach == "cpm"
    assert config.ablation_config == "NONE_MONITORING"
    assert config.init_prior_config == "UNDER_ESTIMATE_90"
    assert config.beam_bound == [(10, 10)]
    assert config.eta == 0.6
