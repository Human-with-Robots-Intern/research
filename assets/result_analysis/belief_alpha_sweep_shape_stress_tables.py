"""Render one combined alpha-sweep belief-robustness table.

This helper aggregates the fixed-mean shape-stress GT runs at
alpha={0.1, 0.01, 0.001} into a single LaTeX table and a companion Markdown
note that explains how to read the metrics.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

DEFAULT_ALPHA_SUMMARY_PATHS: tuple[tuple[float, Path], ...] = (
    (
        0.1,
        Path(
            "assets/results/offline_exp_result/"
            "belief_shape_stress_alpha01/belief_benchmark_summary.json"
        ),
    ),
    (
        0.01,
        Path(
            "assets/results/offline_exp_result/"
            "belief_shape_stress_alpha001/belief_benchmark_summary.json"
        ),
    ),
    (
        0.001,
        Path(
            "assets/results/offline_exp_result/"
            "belief_shape_stress_alpha0001/belief_benchmark_summary.json"
        ),
    ),
)
DEFAULT_OUTPUT_DIR = Path(
    "assets/results/offline_exp_result/belief_shape_stress_alpha_sweep"
)
GT_ORDER = ("gaussian", "lognormal", "mixture")
METHOD_ORDER = (
    "Bayesian",
    "PF (Gaussian)",
    "PF (GT-family)",
)
METRIC_FIELDS = (
    "late_trigger_rate",
    "calibration_error",
    "mean_posterior_mean_abs_error",
    "mean_trigger_abs_error",
)


def load_summary_rows(summary_path: Path) -> list[dict[str, Any]]:
    """Load the saved benchmark summary rows from one JSON artifact."""

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return list(payload.get("summary_rows", []))


def build_alpha_sweep_rows(
    summary_rows_by_alpha: dict[float, list[dict[str, Any]]],
    *,
    gt_distributions: tuple[str, ...] = GT_ORDER,
    observation_setting: str = "same_as_gt",
) -> list[dict[str, Any]]:
    """Extract the fixed-mean alpha sweep rows shown in the final table."""

    table_rows: list[dict[str, Any]] = []
    for alpha in sorted(summary_rows_by_alpha.keys(), reverse=True):
        rows = summary_rows_by_alpha[alpha]
        for gt_distribution in gt_distributions:
            rows_by_variant = {
                str(row["variant"]): row
                for row in rows
                if str(row["gt_distribution"]) == gt_distribution
                and str(row["observation_setting"]) == observation_setting
            }
            required_variants = [
                "bayesian",
                "particle_filter[gaussian]",
            ]
            if gt_distribution != "gaussian":
                required_variants.append(
                    f"particle_filter[gaussian;lik={gt_distribution}]"
                )

            missing_variants = [
                variant
                for variant in required_variants
                if variant not in rows_by_variant
            ]
            if missing_variants:
                raise ValueError(
                    "Missing rows for "
                    f"alpha={alpha}, gt={gt_distribution}, "
                    f"observation_setting={observation_setting}: {missing_variants}"
                )

            for variant in required_variants:
                source_row = rows_by_variant[variant]
                table_rows.append(
                    {
                        "alpha": float(alpha),
                        "eta": float(source_row["eta"]),
                        "gt_distribution": gt_distribution,
                        "gt_label": _format_gt_label(gt_distribution),
                        "method_label": _resolve_method_label(
                            variant=variant,
                            gt_distribution=gt_distribution,
                        ),
                        "late_trigger_rate": float(source_row["late_trigger_rate"]),
                        "calibration_error": float(source_row["calibration_error"]),
                        "mean_posterior_mean_abs_error": float(
                            source_row["mean_posterior_mean_abs_error"]
                        ),
                        "mean_trigger_abs_error": float(
                            source_row["mean_trigger_abs_error"]
                        ),
                        "gt_target_mean": float(source_row["gt_target_mean"]),
                        "prior_config": str(source_row["prior_config"]),
                        "episode_count": int(source_row["episode_count"]),
                    }
                )
    return table_rows


def render_alpha_sweep_latex_table(rows: list[dict[str, Any]]) -> str:
    """Render one LaTeX table for the alpha sweep."""

    if not rows:
        raise ValueError("No rows were provided for LaTeX rendering.")

    metric_minima = _compute_metric_minima(rows)
    body_lines: list[str] = []
    previous_alpha: float | None = None
    previous_gt: str | None = None
    for row in _sort_rows(rows):
        if previous_alpha is not None and not math.isclose(
            float(row["alpha"]),
            previous_alpha,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            body_lines.append(r"        \midrule")
        elif previous_gt is not None and str(row["gt_distribution"]) != previous_gt:
            body_lines.append(r"        \addlinespace[2pt]")

        key = (float(row["alpha"]), str(row["gt_distribution"]))
        body_lines.append(
            "        "
            + " & ".join(
                [
                    _format_alpha(float(row["alpha"])),
                    _latex_escape(str(row["gt_label"])),
                    _latex_escape(str(row["method_label"])),
                    _format_latex_metric(
                        float(row["late_trigger_rate"]),
                        metric_minima[(key, "late_trigger_rate")],
                    ),
                    _format_latex_metric(
                        float(row["calibration_error"]),
                        metric_minima[(key, "calibration_error")],
                    ),
                    _format_latex_metric(
                        float(row["mean_posterior_mean_abs_error"]),
                        metric_minima[(key, "mean_posterior_mean_abs_error")],
                    ),
                    _format_latex_metric(
                        float(row["mean_trigger_abs_error"]),
                        metric_minima[(key, "mean_trigger_abs_error")],
                    ),
                ]
            )
            + r" \\"
        )
        previous_alpha = float(row["alpha"])
        previous_gt = str(row["gt_distribution"])

    eta = float(rows[0]["eta"])
    episode_count = int(rows[0]["episode_count"])
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{@{}c l l c c c c@{}}",
        r"\toprule",
        (
            r"Factor $\alpha$ & GT & Method & "
            r"\textbf{Late ($\downarrow$)} & "
            r"\textbf{$|$Late$-\eta|$ ($\downarrow$)} & "
            r"\textbf{Posterior Mean Error ($\downarrow$)} & "
            r"\textbf{Trigger Error ($\downarrow$)} \\"
        ),
        r"\midrule",
        *body_lines,
        r"\bottomrule",
        r"\end{tabular}}",
        (
            r"\caption{Fixed-mean belief robustness under the "
            r"shape-stress GT profile. All rows use the same-as-GT observation "
            r"setting with prior mean $\mu_0=100$ (CORRECT\_ESTIMATE), GT mean "
            r"$\mathbb{E}[T]=100$, $\eta="
            + f"{eta:.1f}"
            + r"$, "
            + str(episode_count)
            + r" Monte Carlo episodes, and 1024 particles for PF. "
            r"Heavy-tail denotes the fixed-mean lognormal GT under the same "
            r"shape-stress sampler. Non-Gaussian denotes the "
            r"fixed-mean bimodal mixture "
            r"$0.5\mathcal{N}(50,10^2)+0.5\mathcal{N}(150,10^2)$. "
            r"For Gaussian GT, PF with GT-family is identical to PF with "
            r"Gaussian and is omitted. Within each "
            r"$(\alpha,\mathrm{GT})$ block, bold marks the lowest value.}"
        ),
        r"\label{tab:belief_robustness_alpha_sweep_shape_stress}",
        (
            r"\parbox{0.98\linewidth}{\footnotesize "
            r"Observation variance proxy: "
            r"$v_{\mathrm{obs}}(t)=\max(\epsilon,\alpha(\mu_0-t)^2)$. "
            r"Metrics: "
            r"$\mathrm{Late}=\frac{1}{N}\sum_{i=1}^N \mathbf{1}[\hat{t}_i^{(\eta)} > T_i]$, "
            r"$|\mathrm{Late}-\eta|=\left|\mathrm{Late}-\eta\right|$, "
            r"$\mathrm{PosteriorMeanError}=\frac{1}{N}\sum_{i=1}^N |\hat{\mu}_i-T_i|$, "
            r"$\mathrm{TriggerError}=\frac{1}{N}\sum_{i=1}^N |\hat{t}_i^{(\eta)}-T_i|$. "
            r"Here $T_i$ is the GT duration on episode $i$, $\hat{\mu}_i$ is the "
            r"final posterior mean, and $\hat{t}_i^{(\eta)}$ is the method's "
            r"trigger estimate at quantile $\eta$.}"
        ),
        r"\end{table}",
    ]
    return "\n".join(lines)


def render_alpha_sweep_markdown(rows: list[dict[str, Any]]) -> str:
    """Render a Markdown summary with the same table plus reading notes."""

    if not rows:
        raise ValueError("No rows were provided for Markdown rendering.")

    metric_minima = _compute_metric_minima(rows)
    eta = float(rows[0]["eta"])
    episode_count = int(rows[0]["episode_count"])
    table_lines = [
        "# Belief Robustness Alpha Sweep",
        "",
        (
            "Fixed setup: `CORRECT_ESTIMATE` prior so `init mean = 100`, "
            "`E[T] = 100`, `eta = "
            + f"{eta:.1f}"
            + "`, `N = "
            + str(episode_count)
            + "`, PF particles = `1024`, and observations are generated under "
            "`same_as_gt`."
        ),
        "",
        (
            "Additional fixed-mean GTs are `Heavy-tail (Lognormal)` and the "
            "shape-stress mixture `0.5 N(50, 10^2) + 0.5 N(150, 10^2)`."
        ),
        "",
        "| Alpha | GT | Method | Late | Cal (|Late-eta|) | Posterior Mean Error | Trigger Error |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]

    for row in _sort_rows(rows):
        key = (float(row["alpha"]), str(row["gt_distribution"]))
        table_lines.append(
            "| "
            + " | ".join(
                [
                    _format_alpha(float(row["alpha"])),
                    str(row["gt_label"]),
                    str(row["method_label"]),
                    _format_markdown_metric(
                        float(row["late_trigger_rate"]),
                        metric_minima[(key, "late_trigger_rate")],
                    ),
                    _format_markdown_metric(
                        float(row["calibration_error"]),
                        metric_minima[(key, "calibration_error")],
                    ),
                    _format_markdown_metric(
                        float(row["mean_posterior_mean_abs_error"]),
                        metric_minima[(key, "mean_posterior_mean_abs_error")],
                    ),
                    _format_markdown_metric(
                        float(row["mean_trigger_abs_error"]),
                        metric_minima[(key, "mean_trigger_abs_error")],
                    ),
                ]
            )
            + " |"
        )

    table_lines.extend(
        [
            "",
            "## How To Read",
            "",
            "- Each `(alpha, GT)` block compares methods under exactly the same latent GT episodes and the same observation schedule.",
            "- `Late` is the empirical fraction of episodes where the trigger happens after the true completion time. Smaller means safer, but it can also be overly conservative.",
            "- `Cal = |Late-eta|` is the calibration metric. This is the cleanest way to check whether the method's late-trigger frequency matches the target quantile `eta`.",
            "- `Posterior Mean Error` checks belief accuracy, while `Trigger Error` checks decision accuracy. Both are absolute errors, so lower is better.",
            "- For Gaussian GT, `PF (GT-family)` is omitted because GT-family and Gaussian likelihood are the same model.",
            "",
            "## Metric Definitions",
            "",
            "Observation variance scale:",
            "",
            r"$$v_{\text{obs}}(t)=\max(\epsilon,\alpha(\mu_0-t)^2)$$",
            "",
            "Late-trigger rate:",
            "",
            r"$$\mathrm{Late}=\frac{1}{N}\sum_{i=1}^{N}\mathbf{1}\left[\hat{t}_i^{(\eta)} > T_i\right]$$",
            "",
            "Calibration error:",
            "",
            r"$$\mathrm{Cal}=\left|\mathrm{Late}-\eta\right|$$",
            "",
            "Posterior mean error:",
            "",
            r"$$\mathrm{PosteriorMeanError}=\frac{1}{N}\sum_{i=1}^{N}\left|\hat{\mu}_i-T_i\right|$$",
            "",
            "Trigger error:",
            "",
            r"$$\mathrm{TriggerError}=\frac{1}{N}\sum_{i=1}^{N}\left|\hat{t}_i^{(\eta)}-T_i\right|$$",
            "",
            "Here `T_i` is the GT duration for episode `i`, `\\hat{\\mu}_i` is the final posterior mean, and `\\hat{t}_i^{(\\eta)}` is the method's trigger estimate at quantile `eta`.",
            "",
            "## Short Takeaway",
            "",
            "- Lower `alpha` makes the synthetic observations tighter, and all methods improve sharply from `0.1` to `0.001`.",
            "- Under Gaussian GT, Bayesian stays the strongest method once `alpha` becomes small.",
            "- Under heavy-tail lognormal GT, `PF (GT-family)` does not help here; Bayesian remains clearly better on posterior and trigger accuracy.",
            "- Under the fixed-mean mixture GT, `PF (GT-family)` becomes the strongest PF variant and is best overall at `alpha = 0.001` on all four metrics in this table.",
        ]
    )
    return "\n".join(table_lines)


def save_alpha_sweep_outputs(
    *,
    latex_table: str,
    markdown_table: str,
    output_dir: Path,
) -> dict[str, Path]:
    """Persist the rendered LaTeX and Markdown artifacts."""

    latex_dir = output_dir / "latex_tables"
    markdown_dir = output_dir / "markdown_tables"
    latex_dir.mkdir(parents=True, exist_ok=True)
    markdown_dir.mkdir(parents=True, exist_ok=True)

    latex_path = latex_dir / "belief_robustness_tables.tex"
    markdown_path = markdown_dir / "belief_robustness_tables.md"
    latex_path.write_text(latex_table + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_table + "\n", encoding="utf-8")
    return {
        "latex_table": latex_path,
        "markdown_table": markdown_path,
    }


def _resolve_method_label(*, variant: str, gt_distribution: str) -> str:
    if variant == "bayesian":
        return "Bayesian"
    if variant == "particle_filter[gaussian]":
        return "PF (Gaussian)"
    if variant == f"particle_filter[gaussian;lik={gt_distribution}]":
        return "PF (GT-family)"
    raise ValueError(
        f"Unsupported variant for gt_distribution={gt_distribution}: {variant}"
    )


def _format_gt_label(gt_distribution: str) -> str:
    if gt_distribution == "gaussian":
        return "Gaussian"
    if gt_distribution == "lognormal":
        return "Heavy-tail (Lognormal)"
    if gt_distribution == "mixture":
        return "Multi-modal (Mixture)"
    return f"Non-Gaussian ({gt_distribution.title()})"


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -float(row["alpha"]),
            GT_ORDER.index(str(row["gt_distribution"])),
            METHOD_ORDER.index(str(row["method_label"])),
        ),
    )


def _compute_metric_minima(
    rows: list[dict[str, Any]],
) -> dict[tuple[tuple[float, str], str], float]:
    minima: dict[tuple[tuple[float, str], str], float] = {}
    grouped: dict[tuple[float, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(
            (float(row["alpha"]), str(row["gt_distribution"])),
            [],
        ).append(row)
    for key, group_rows in grouped.items():
        for metric_field in METRIC_FIELDS:
            minima[(key, metric_field)] = min(
                float(row[metric_field]) for row in group_rows
            )
    return minima


def _format_alpha(value: float) -> str:
    if math.isclose(value, 0.1, rel_tol=0.0, abs_tol=1e-12):
        return "0.1"
    if math.isclose(value, 0.01, rel_tol=0.0, abs_tol=1e-12):
        return "0.01"
    if math.isclose(value, 0.001, rel_tol=0.0, abs_tol=1e-12):
        return "0.001"
    return f"{value:.3g}"


def _format_latex_metric(value: float, best_value: float) -> str:
    text = f"{value:.3f}"
    if math.isclose(value, best_value, rel_tol=0.0, abs_tol=1e-12):
        return rf"\textbf{{{text}}}"
    return text


def _format_markdown_metric(value: float, best_value: float) -> str:
    text = f"{value:.3f}"
    if math.isclose(value, best_value, rel_tol=0.0, abs_tol=1e-12):
        return f"**{text}**"
    return text


def _latex_escape(text: str) -> str:
    return text.replace("&", r"\&").replace("_", r"\_")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render one combined alpha-sweep table for fixed-mean "
            "shape-stress belief robustness runs."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the LaTeX/Markdown tables will be written.",
    )
    args = parser.parse_args()

    summary_rows_by_alpha = {
        alpha: load_summary_rows(summary_path)
        for alpha, summary_path in DEFAULT_ALPHA_SUMMARY_PATHS
    }
    rows = build_alpha_sweep_rows(summary_rows_by_alpha)
    written_paths = save_alpha_sweep_outputs(
        latex_table=render_alpha_sweep_latex_table(rows),
        markdown_table=render_alpha_sweep_markdown(rows),
        output_dir=args.output_dir,
    )
    for path in written_paths.values():
        print(path)


if __name__ == "__main__":
    main()
