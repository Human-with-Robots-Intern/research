import argparse
import json

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse

# --- 데이터 준비 (공통) ---
# 순서: [Under(60s), Correct(100s), Over(140s)]
DATA = {
    "Ours (Default)": {
        "tsr": [],
        "makespan": [],
        "color": "red",
        "marker": "*",
        "style": "-",
    },
    "Ours (w/o Mon.)": {  # Ablation
        "tsr": [],
        "makespan": [],
        "color": "orange",
        "marker": "D",
        "style": ":",
    },
    "DAG + EDF": {
        "tsr": [],
        "makespan": [],
        "color": "gray",
        "marker": "^",
        "style": "-.",
    },
    "DAG + CPM": {
        "tsr": [],
        "makespan": [],
        "color": "gray",
        "marker": "s",
        "style": "--",
    },
}

APPROACH_LIST = {
    "dag_bayesian_DEFAULT": "Ours (Default)",
    "dag_bayesian_NONE_MONITORING": "Ours (w/o Mon.)",
    "dag_edf": "DAG + EDF",
    "cpm": "DAG + CPM",
}

INIT_LIST = ["init_60", "init_100", "init_140"]
TASK_CASE = ["tasks_2", "tasks_3", "tasks_4"]
METRIC_LIST = ["tsr", "makespan"]


def load_data(data_path: str) -> dict:
    with open(data_path, "r") as f:
        raw_data = json.load(f)

    # DATA 딕셔너리 초기화
    for key in DATA:
        DATA[key]["tsr"] = []
        DATA[key]["makespan"] = []

    # 각 접근법에 대해 데이터 처리
    for approach_key, approach_name in APPROACH_LIST.items():
        if approach_key not in raw_data:
            continue

        # 각 초기 조건(init_60, 100, 140)별로 순회
        for init_cond in INIT_LIST:
            tsr_values = []
            makespan_values = []

            # 모든 태스크 케이스(tasks_2, 3, 4)의 값을 수집
            for task_case in TASK_CASE:
                if (
                    task_case in raw_data[approach_key]
                    and init_cond in raw_data[approach_key][task_case]
                ):
                    metrics = raw_data[approach_key][task_case][init_cond]
                    tsr_values.append(metrics.get("tsr", 0))
                    makespan_values.append(metrics.get("makespan", 0))

            # 수집된 값들의 평균 계산
            avg_tsr = np.mean(tsr_values) if tsr_values else 0.0
            avg_makespan = np.mean(makespan_values) if makespan_values else 0.0

            # 결과 저장
            DATA[approach_name]["tsr"].append(avg_tsr)
            DATA[approach_name]["makespan"].append(avg_makespan)

    print("Data Loaded Successfully.")
    return DATA


def plot_trajectory(data: dict) -> None:
    """
    TSR과 Makespan의 관계를 보여주는 궤적 그래프를 생성합니다.
    x축은 Makespan(효율성), y축은 TSR(강건성)을 나타냅니다.

    Args:
        data (dict): 시각화에 사용할 데이터.
    """
    fig, ax = plt.subplots(figsize=(8, 6))

    # 각 Method별 궤적 그리기
    for name, d in data.items():
        ax.plot(
            d["makespan"],
            d["tsr"],
            label=name,
            color=d["color"],
            marker=d["marker"],
            linestyle=d["style"],
            linewidth=3 if "Default" in name else 1.5,
            markersize=10 if "Default" in name else 8,
            alpha=1.0 if "Default" in name else 0.8,
        )

    # --- 영역 하이라이트 (핵심) ---
    # 1. Ours: Tight Cluster (Robustness)
    ours_center = (
        np.mean(data["Ours (Default)"]["makespan"]),
        np.mean(data["Ours (Default)"]["tsr"]),
    )
    cluster_circle = Ellipse(
        ours_center, width=30, height=6, angle=0, color="red", alpha=0.1
    )
    ax.add_patch(cluster_circle)
    ax.text(
        ours_center[0],
        ours_center[1] + 4,
        "Robust & Efficient\n(Sweet Spot)",
        color="red",
        ha="center",
        fontweight="bold",
    )

    # --- 축 및 설정 ---
    ax.set_xlabel("Makespan (s) ↓ (Efficiency)", fontsize=12, fontweight="bold")
    ax.set_ylabel(
        "Temporal Success Rate (%) ↑ (Robustness)", fontsize=12, fontweight="bold"
    )
    ax.set_title(
        "Performance Stability across Belief Conditions", fontsize=14, fontweight="bold"
    )

    # 그리드 및 범례
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="lower left", fontsize=10)

    plt.tight_layout()
    plt.show()


def plot_separate_metrics(data: dict) -> None:
    """
    TSR과 Makespan을 각각의 그래프로 분리하여 보여줍니다.
    x축은 초기 믿음 조건, y축은 각 메트릭의 값을 나타냅니다.

    Args:
        data (dict): 시각화에 사용할 데이터.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    conditions = ["Under-est\n(60s)", "Correct\n(100s)", "Over-est\n(140s)"]
    metrics_info = [
        (
            "tsr",
            "(a) TSR across Initial Belief Conditions",
            "Temporal Success Rate (%)",
        ),
        ("makespan", "(b) Makespan across Initial Belief Conditions", "Time (s)"),
    ]

    method_order = ["DAG + CPM", "DAG + EDF", "Ours (w/o Mon.)", "Ours (Default)"]

    for col, (metric_key, title, ylabel) in enumerate(metrics_info):
        ax = axes[col]
        for name in method_order:
            d = data[name]
            y_data = d[metric_key]
            lw = 3 if "Default" in name else 1.5
            alpha = 1.0 if "Default" in name else 0.7

            ax.plot(
                conditions,
                y_data,
                label=name,
                color=d["color"],
                linestyle=d["style"],
                marker=d["marker"],
                linewidth=lw,
                alpha=alpha,
                markersize=8,
            )

        ax.set_title(
            title,
            fontsize=14,
        )
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_xlabel("Initial Belief Condition", fontsize=12)
        ax.grid(True, linestyle="--", alpha=0.5)

    # (a) TSR 그래프에 화살표로 Robustness 강조
    # axes[0].annotate(
    #     "Stable Robustness\n(Ours)",
    #     xy=(1, 89),
    #     xytext=(1, 70),
    #     arrowprops=dict(facecolor="red", shrink=0.05),
    #     fontsize=10,
    #     color="red",
    #     ha="center",
    #     fontweight="bold",
    # )
    # axes[0].annotate(
    #     "Performance Drop\n(Baselines)",
    #     xy=(2, 60),
    #     xytext=(1.5, 75),
    #     arrowprops=dict(facecolor="gray", shrink=0.05),
    #     fontsize=10,
    #     color="gray",
    #     ha="center",
    # )

    # 범례 통합
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.02),  # bbox_to_anchor 조정
        ncol=4,
        fontsize=11,
    )

    plt.tight_layout()
    # tight_layout 후 하단 여백 확보
    plt.subplots_adjust(bottom=0.2)
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
        TSR(Temporal Success Rate)과 Makespan 성능 지표를 시각화합니다.
        두 가지 플롯 타입을 선택할 수 있습니다:
        1. trajectory: TSR과 Makespan의 관계를 2D 궤적으로 표시 (기본값)
        2. separate: TSR과 Makespan을 각각 별도의 라인 그래프로 표시
        """
    )
    parser.add_argument(
        "--data_path",
        type=str,
        default="assets/results/1112 copy/unified_analysis_summary.revised.json",
        help="데이터 파일 경로를 지정합니다.",
    )
    parser.add_argument(
        "--plot_type",
        type=str,
        default="trajectory",
        choices=["trajectory", "separate"],
        help="생성할 그래프 종류를 선택합니다: 'trajectory' 또는 'separate'.",
    )
    args = parser.parse_args()

    load_data(args.data_path)

    if args.plot_type == "trajectory":
        plot_trajectory(DATA)
    elif args.plot_type == "separate":
        plot_separate_metrics(DATA)
