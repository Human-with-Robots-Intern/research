"""Tests for the belief robustness benchmark CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from scripts.offline.belief_distribution_benchmark import (
    _resolve_cli_defaults,
    _run_observation_alpha_sweep,
    _safe_load_yaml_mapping,
    parse_args,
)
from src.experiments.belief_robustness import (
    SHAPE_STRESS_GT_DISTRIBUTIONS,
    BeliefBenchmarkConfig,
)
from src.utils.config import constants

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch


def test_empty_cli_matches_belief_benchmark_config_defaults() -> None:
    """No CLI flags should resolve to the dataclass baseline (shape-stress bundle)."""

    args = parse_args([])
    config, output_dir, emit_latex_export, latex_dir, alpha_sweep = (
        _resolve_cli_defaults(args)
    )

    assert config == BeliefBenchmarkConfig()
    assert output_dir == Path(
        "assets/results/offline_exp_result/belief_distribution_benchmark"
    )
    assert config.gt_variance is None
    assert config.gt_mean_multipliers == (1.0,)
    assert SHAPE_STRESS_GT_DISTRIBUTIONS == ("gaussian", "lognormal", "mixture")
    assert config.observation_alpha == constants.FACTOR_ALPHA
    assert config.observation_families == ("gaussian", "same_as_gt")
    assert config.particle_count == 1024
    assert not emit_latex_export
    assert latex_dir is None
    assert alpha_sweep is None


def test_latex_export_style_flags_and_comparison_outputs() -> None:
    """``--latex-export`` should enable comparison artifacts and default LaTeX dir."""

    out = Path("assets/results/offline_exp_result/belief_latex_export_smoke")
    args = parse_args(
        [
            "--gt-mean-multipliers",
            "0.6",
            "1.0",
            "1.4",
            "--latex-export",
            "--output-dir",
            str(out),
        ]
    )
    config, output_dir, emit_latex_export, latex_dir, alpha_sweep = (
        _resolve_cli_defaults(args)
    )

    assert output_dir == out
    assert config.gt_mean_multipliers == (0.6, 1.0, 1.4)
    assert config.etas == (0.1,)
    assert config.observation_families == ("gaussian", "same_as_gt")
    assert config.particle_count == 1024
    assert config.particle_distributions == ("gaussian",)
    assert emit_latex_export
    assert latex_dir == output_dir / "latex_tables"
    assert alpha_sweep is None


def test_cli_explicit_overrides_apply_on_top_of_defaults() -> None:
    """Explicit CLI values should override defaults; comparison stays off unless requested."""

    args = parse_args(
        [
            "--gt-mean-multipliers",
            "1.0",
            "--etas",
            "0.2",
            "--observation-alpha",
            "0.01",
            "--output-dir",
            "/tmp/custom_belief_benchmark",
        ]
    )
    config, output_dir, emit_latex_export, latex_dir, alpha_sweep = (
        _resolve_cli_defaults(args)
    )

    assert config.gt_mean_multipliers == (1.0,)
    assert config.etas == (0.2,)
    assert config.observation_alpha == 0.01
    assert output_dir == Path("/tmp/custom_belief_benchmark")
    assert config.particle_count == 1024
    assert not emit_latex_export
    assert latex_dir is None
    assert alpha_sweep is None


def test_cli_observation_alpha_sweep_resolves(tmp_path: Path) -> None:
    """``--observation-alphas`` should resolve to a non-``None`` sweep tuple."""

    args = parse_args(["--observation-alphas", "0.01", "0.05", "0.1"])
    _, _, _, _, alpha_sweep = _resolve_cli_defaults(args)
    assert alpha_sweep == (0.01, 0.05, 0.1)


def test_cli_observation_alpha_mutually_exclusive() -> None:
    """Single and multi α flags must not be combined."""

    args = parse_args(["--observation-alpha", "0.02", "--observation-alphas", "0.01"])
    with pytest.raises(ValueError, match="not both"):
        _resolve_cli_defaults(args)


def test_legacy_yaml_deprecated_comparison_key_maps_to_latex_export(
    tmp_path: Path,
) -> None:
    """Deprecated comparison YAML key should behave like ``latex_export``."""

    cfg_path = tmp_path / "legacy.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"episode_count": 1, "reviewer10_comparison": True}),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path)])
    with pytest.warns(DeprecationWarning, match="reviewer10_comparison"):
        _, _, emit_latex_export, _, _ = _resolve_cli_defaults(args)
    assert emit_latex_export


def test_yaml_config_sets_benchmark_and_script_fields(tmp_path: Path) -> None:
    """YAML values should populate the config and paths before CLI overrides."""

    out_dir = tmp_path / "from_yaml"
    cfg_path = tmp_path / "bench.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "episode_count": 11,
                "etas": [0.05],
                "output_dir": str(out_dir),
                "latex_export": True,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path)])
    config, output_dir, emit_latex_export, latex_dir, alpha_sweep = (
        _resolve_cli_defaults(args)
    )

    assert config.episode_count == 11
    assert config.etas == (0.05,)
    assert output_dir == out_dir
    assert emit_latex_export
    assert latex_dir == out_dir / "latex_tables"
    assert alpha_sweep is None


def test_cli_overrides_yaml_benchmark_fields(tmp_path: Path) -> None:
    """Explicit CLI flags should win over YAML for overlapping settings."""

    cfg_path = tmp_path / "bench.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"episode_count": 3, "etas": [0.05]}),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path), "--episodes", "9", "--etas", "0.2"])
    config, _, _, _, alpha_sweep = _resolve_cli_defaults(args)

    assert config.episode_count == 9
    assert config.etas == (0.2,)
    assert alpha_sweep is None


def test_yaml_observation_alphas_sweep(tmp_path: Path) -> None:
    """YAML ``observation_alphas`` should populate the fifth resolve tuple."""

    cfg_path = tmp_path / "sweep.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "episode_count": 2,
                "observation_alphas": [0.001, 0.01],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path)])
    _, _, _, _, alpha_sweep = _resolve_cli_defaults(args)
    assert alpha_sweep == (0.001, 0.01)


def test_run_observation_alpha_sweep_tags_each_summary_row() -> None:
    """Merged sweep output should carry ``observation_alpha`` on every summary row."""

    template = BeliefBenchmarkConfig(
        etas=(0.1,),
        episode_count=1,
        gt_mean_multipliers=(1.0,),
        observation_families=("gaussian",),
        random_seed=3,
        write_episode_rows=False,
    )
    merged = _run_observation_alpha_sweep(template, (0.01, 0.02))
    assert all("observation_alpha" in row for row in merged["summary_rows"])
    assert {row["observation_alpha"] for row in merged["summary_rows"]} == {0.01, 0.02}
    per_alpha = {0.01: 0, 0.02: 0}
    for row in merged["summary_rows"]:
        per_alpha[float(row["observation_alpha"])] += 1
    assert per_alpha[0.01] == per_alpha[0.02] == len(merged["summary_rows"]) // 2


def test_cli_single_alpha_conflicts_with_yaml_sweep(tmp_path: Path) -> None:
    """``--observation-alpha`` must not override a YAML ``observation_alphas`` sweep."""

    cfg_path = tmp_path / "sweep.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"observation_alphas": [0.01, 0.02]}),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path), "--observation-alpha", "0.03"])
    with pytest.raises(ValueError, match="Cannot combine"):
        _resolve_cli_defaults(args)


def test_yaml_rejects_observation_alpha_with_alphas(tmp_path: Path) -> None:
    """YAML must not combine scalar and sweep α keys."""

    cfg_path = tmp_path / "bad.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {"observation_alpha": 0.01, "observation_alphas": [0.001, 0.01]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path)])
    with pytest.raises(ValueError, match="both"):
        _resolve_cli_defaults(args)


def test_safe_load_yaml_mapping_rejects_non_mapping_root(tmp_path: Path) -> None:
    """Non-dict YAML roots should raise ``TypeError``."""

    bad = tmp_path / "bad.yaml"
    bad.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(TypeError, match="mapping"):
        _safe_load_yaml_mapping(bad)


def test_unknown_yaml_key_raises_at_resolve(tmp_path: Path) -> None:
    """Unknown keys in the config file should fail fast with a clear error."""

    cfg_path = tmp_path / "bad_keys.yaml"
    cfg_path.write_text("not_a_valid_field: 1\n", encoding="utf-8")
    args = parse_args(["--config", str(cfg_path)])
    with pytest.raises(ValueError, match="Unknown keys"):
        _resolve_cli_defaults(args)
