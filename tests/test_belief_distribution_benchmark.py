"""Tests for the belief robustness benchmark CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from scripts.offline.belief_distribution_benchmark import (
    _resolve_cli_defaults,
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
    config, output_dir, emit_reviewer10_outputs, latex_dir = _resolve_cli_defaults(args)

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
    assert not emit_reviewer10_outputs
    assert latex_dir is None


def test_reviewer10_style_flags_and_comparison_outputs() -> None:
    """Opting into reviewer10 outputs should enable comparison artifacts and LaTeX dir."""

    out = Path("assets/results/offline_exp_result/belief_reviewer10_comparison")
    args = parse_args(
        [
            "--gt-mean-multipliers",
            "0.6",
            "1.0",
            "1.4",
            "--reviewer10-comparison",
            "--output-dir",
            str(out),
        ]
    )
    config, output_dir, emit_reviewer10_outputs, latex_dir = _resolve_cli_defaults(args)

    assert output_dir == out
    assert config.gt_mean_multipliers == (0.6, 1.0, 1.4)
    assert config.etas == (0.1,)
    assert config.observation_families == ("gaussian", "same_as_gt")
    assert config.particle_count == 1024
    assert config.particle_distributions == ("gaussian",)
    assert emit_reviewer10_outputs
    assert latex_dir == output_dir / "latex_tables"


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
    config, output_dir, emit_reviewer10_outputs, latex_dir = _resolve_cli_defaults(args)

    assert config.gt_mean_multipliers == (1.0,)
    assert config.etas == (0.2,)
    assert config.observation_alpha == 0.01
    assert output_dir == Path("/tmp/custom_belief_benchmark")
    assert config.particle_count == 1024
    assert not emit_reviewer10_outputs
    assert latex_dir is None


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
                "reviewer10_comparison": True,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path)])
    config, output_dir, emit_reviewer10, latex_dir = _resolve_cli_defaults(args)

    assert config.episode_count == 11
    assert config.etas == (0.05,)
    assert output_dir == out_dir
    assert emit_reviewer10
    assert latex_dir == out_dir / "latex_tables"


def test_cli_overrides_yaml_benchmark_fields(tmp_path: Path) -> None:
    """Explicit CLI flags should win over YAML for overlapping settings."""

    cfg_path = tmp_path / "bench.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"episode_count": 3, "etas": [0.05]}),
        encoding="utf-8",
    )
    args = parse_args(["--config", str(cfg_path), "--episodes", "9", "--etas", "0.2"])
    config, _, _, _ = _resolve_cli_defaults(args)

    assert config.episode_count == 9
    assert config.etas == (0.2,)


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
