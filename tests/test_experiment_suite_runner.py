"""Tests for the offline experiment suite orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.offline.run_experiment_suite import (
    PROJECT_ROOT,
    _load_suite_definition,
    build_execution_plan,
)


def _write_oracle_config(tmp_path: Path) -> Path:
    """Create a minimal oracle config used as the suite-runner base config."""

    config_path = tmp_path / "oracle.yaml"
    config_path.write_text(
        "\n".join(
            [
                "max_workers: 4",
                "oracle_time_limit_seconds: 1800",
                "skip_completed: true",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _value_after(command: tuple[str, ...], flag: str) -> str:
    """Return the argument immediately following a CLI flag."""

    index = command.index(flag)
    return command[index + 1]


def test_pf_vs_bayesian_plan_orders_oracle_batches_and_analysis(
    tmp_path: Path,
) -> None:
    """The PF-vs-Bayesian suite should stage oracle, 10 batch configs, then analysis."""

    plan = build_execution_plan(
        requested_suite="pf_vs_bayesian",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=False,
        temp_dir=tmp_path,
    )

    assert [stage.kind for stage in plan.stages] == [
        "oracle",
        "batch",
        "batch",
        "batch",
        "batch",
        "batch",
        "batch",
        "batch",
        "batch",
        "batch",
        "batch",
        "analysis",
    ]
    assert [stage.suite for stage in plan.stages[1:11]] == ["pf_vs_bayesian"] * 10
    assert plan.stages[-1].suite == "pf_vs_bayesian"


def test_scalability_plan_orders_oracle_batch_and_analysis(tmp_path: Path) -> None:
    """The scalability suite should stage one oracle, one batch, and one analysis."""

    plan = build_execution_plan(
        requested_suite="scalability",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=False,
        temp_dir=tmp_path,
    )

    assert [(stage.kind, stage.suite) for stage in plan.stages] == [
        ("oracle", None),
        ("batch", "scalability"),
        ("analysis", "scalability"),
    ]


def test_skip_oracle_preflight_omits_oracle_stage(tmp_path: Path) -> None:
    """With ``skip_oracle_preflight``, the plan should start at batch then analysis."""

    plan = build_execution_plan(
        requested_suite="scalability",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=False,
        temp_dir=tmp_path,
        skip_oracle_preflight=True,
    )

    assert [(stage.kind, stage.suite) for stage in plan.stages] == [
        ("batch", "scalability"),
        ("analysis", "scalability"),
    ]
    assert plan.oracle_config == {}


def test_monitoring_budget_plan_orders_oracle_batch_and_analysis(
    tmp_path: Path,
) -> None:
    """The monitoring-budget suite should stage one oracle, one batch, and analysis."""

    plan = build_execution_plan(
        requested_suite="monitoring_budget",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=False,
        temp_dir=tmp_path,
    )

    assert [(stage.kind, stage.suite) for stage in plan.stages] == [
        ("oracle", None),
        ("batch", "monitoring_budget"),
        ("analysis", "monitoring_budget"),
    ]


def test_all_plan_uses_single_oracle_and_expected_suite_order(tmp_path: Path) -> None:
    """The combined suite run should execute one shared oracle stage, then each suite."""

    plan = build_execution_plan(
        requested_suite="all",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=False,
        temp_dir=tmp_path,
    )

    sequence = [(stage.kind, stage.suite) for stage in plan.stages]
    assert sequence[:7] == [
        ("oracle", None),
        ("batch", "scalability"),
        ("analysis", "scalability"),
        ("batch", "eta_sensitivity"),
        ("analysis", "eta_sensitivity"),
        ("batch", "monitoring_budget"),
        ("analysis", "monitoring_budget"),
    ]
    assert sequence[7:-1] == [("batch", "pf_vs_bayesian")] * 10
    assert sequence[-1] == ("analysis", "pf_vs_bayesian")


def test_skip_completed_flag_is_forwarded_to_oracle_and_batch(tmp_path: Path) -> None:
    """The explicit skip-completed override should appear on oracle and batch stages."""

    plan = build_execution_plan(
        requested_suite="scalability",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=True,
        temp_dir=tmp_path,
    )

    oracle_command = plan.stages[0].command
    batch_command = plan.stages[1].command

    assert "--skip-completed" in oracle_command
    assert "--skip-completed" in batch_command


def test_skip_completed_applies_only_to_batch_when_oracle_skipped(
    tmp_path: Path,
) -> None:
    """Skip-completed on the suite runner should still reach batch when oracle is off."""

    plan = build_execution_plan(
        requested_suite="scalability",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=True,
        temp_dir=tmp_path,
        skip_oracle_preflight=True,
    )

    batch_command = plan.stages[0].command
    assert "--skip-completed" in batch_command


def test_analysis_paths_are_inferred_from_output_and_oracle_dirs(
    tmp_path: Path,
) -> None:
    """Analysis stages should infer the correct base_dir and relative subdirectories."""

    plan = build_execution_plan(
        requested_suite="pf_vs_bayesian",
        oracle_config_path=_write_oracle_config(tmp_path),
        force_skip_completed=False,
        temp_dir=tmp_path,
    )

    analysis_command = plan.stages[-1].command

    assert _value_after(analysis_command, "--base_dir") == str(
        PROJECT_ROOT / "assets/results"
    )
    assert _value_after(analysis_command, "--batch_dirname") == (
        "offline_exp_result/offline_batch_pf_vs_bayesian"
    )
    assert _value_after(analysis_command, "--oracle_dirname") == (
        "offline_oracle_reference"
    )
    assert _value_after(analysis_command, "--output_dir") == str(
        PROJECT_ROOT / "assets/results/offline_exp_result/analysis/pf_vs_bayesian"
    )


def test_suite_definition_rejects_mismatched_output_dirs(tmp_path: Path) -> None:
    """All configs within one suite must share the same output_dir."""

    config_a = tmp_path / "suite_a.yaml"
    config_a.write_text(
        "\n".join(
            [
                'output_dir: "assets/results/offline_exp_result/offline_batch_a"',
                'oracle_reference_dir: "assets/results/offline_oracle_reference"',
            ]
        ),
        encoding="utf-8",
    )
    config_b = tmp_path / "suite_b.yaml"
    config_b.write_text(
        "\n".join(
            [
                'output_dir: "assets/results/offline_exp_result/offline_batch_b"',
                'oracle_reference_dir: "assets/results/offline_oracle_reference"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="single output_dir"):
        _load_suite_definition("broken_suite", [config_a, config_b])


def test_suite_definition_rejects_mismatched_oracle_dirs(tmp_path: Path) -> None:
    """All configs within one suite must share the same oracle_reference_dir."""

    config_a = tmp_path / "suite_a.yaml"
    config_a.write_text(
        "\n".join(
            [
                'output_dir: "assets/results/offline_exp_result/offline_batch_a"',
                'oracle_reference_dir: "assets/results/offline_oracle_reference"',
            ]
        ),
        encoding="utf-8",
    )
    config_b = tmp_path / "suite_b.yaml"
    config_b.write_text(
        "\n".join(
            [
                'output_dir: "assets/results/offline_exp_result/offline_batch_a"',
                'oracle_reference_dir: "assets/results/offline_exp_result/offline_oracle_reference"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="single oracle_reference_dir"):
        _load_suite_definition("broken_suite", [config_a, config_b])
