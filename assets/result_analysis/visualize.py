import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse

# --- 데이터 준비 (공통) ---
# 순서: [Under(60s), Under-mid(80s), Correct(100s), Over-mid(120s), Over(140s)]
DATA = {
    "Ours": {
        "sr": [],
        "makespan": [],
        "color": "red",
        "marker": "*",
        "style": "-",
    },
    "Ours (w/o Mon.)": {  # Ablation
        "sr": [],
        "makespan": [],
        "color": "orange",
        "marker": "p",
        "style": "-",
    },
    "DAG + EDF": {
        "sr": [],
        "makespan": [],
        "color": "brown",
        "marker": "x",
        "style": "-.",
    },
    "DAG + CPM": {
        "sr": [],
        "makespan": [],
        "color": "green",
        "marker": "s",
        "style": "--",
    },
    "ProgPrompt": {
        "sr": [],
        "makespan": [],
        "color": "blue",
        "marker": "o",
        "style": ":",
    },
    "CaP": {
        "sr": [],
        "makespan": [],
        "color": "purple",
        "marker": "D",
        "style": ":",
    },
}

APPROACH_LIST = {
    "dag_bayesian_DEFAULT": "Ours",
    "dag_bayesian_NONE_MONITORING": "Ours (w/o Mon.)",
    "dag_edf": "DAG + EDF",
    "cpm": "DAG + CPM",
    "progprompt": "ProgPrompt",
    "cap_ai2thor_simulation": "CaP",
}

INIT_LIST = [
    "init_60",
    "init_70",
    "init_80",
    "init_90",
    "init_100",
    "init_110",
    "init_120",
    "init_130",
    "init_140",
]
TASK_CASE = [
    # "tasks_2_constraints_1",
    "tasks_2",
    "tasks_3",
    # "tasks_3_constraints_2",
]
METRIC_LIST = ["sr", "makespan"]

# 제거할 베이스라인 목록
EXCLUDE_BASELINES = []


def load_data(data_path: str) -> dict:
    with open(data_path, "r") as f:
        raw_data = json.load(f)

    # DATA 딕셔너리 초기화
    for key in DATA:
        DATA[key]["sr"] = []
        DATA[key]["makespan"] = []

    # 각 접근법에 대해 데이터 처리
    for approach_key, approach_name in APPROACH_LIST.items():
        # 제외할 베이스라인 스킵
        if approach_key in EXCLUDE_BASELINES:
            continue

        if approach_key not in raw_data:
            continue

        # 각 초기 조건(init_60, 80, 100, 120, 140)별로 순회
        for init_cond in INIT_LIST:
            sr_values = []
            makespan_values = []

            # 모든 태스크 케이스(tasks_2, 3, 4)의 값을 수집
            for task_case in TASK_CASE:
                if (
                    task_case in raw_data[approach_key]
                    and init_cond in raw_data[approach_key][task_case]
                ):
                    metrics = raw_data[approach_key][task_case][init_cond]
                    sr_values.append(metrics.get("sr", 0))
                    makespan_value = metrics.get("makespan", 0)

                    # CAP의 makespan이 비정상적으로 높은 경우 클리핑 (500초로 제한)
                    if approach_name == "CaP" and makespan_value > 500:
                        makespan_value = 500

                    makespan_values.append(makespan_value)

            # 수집된 값들의 평균 계산
            avg_sr = np.mean(sr_values) if sr_values else 0.0
            avg_makespan = np.mean(makespan_values) if makespan_values else 0.0

            # 결과 저장
            DATA[approach_name]["sr"].append(avg_sr)
            DATA[approach_name]["makespan"].append(avg_makespan)

    print("Data Loaded Successfully.")
    return DATA


def plot_trajectory(data: dict, output_path: str | None = None) -> None:
    """
    sr과 Makespan의 관계를 보여주는 궤적 그래프를 생성합니다.
    x축은 Makespan(효율성), y축은 sr(강건성)을 나타냅니다.

    Args:
        data (dict): 시각화에 사용할 데이터.
        output_path (str | None): 그래프를 저장할 파일 경로. None이면 화면에 표시.
    """
    fig, ax = plt.subplots(figsize=(8, 8))

    # 각 Method별 궤적 그리기
    for name, d in data.items():
        # 데이터가 비어있으면(제외된 베이스라인) 그리지 않음
        if not d["sr"] or not d["makespan"]:
            continue

        ax.plot(
            d["makespan"],
            d["sr"],
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
        np.mean(data["Ours"]["makespan"]),
        np.mean(data["Ours"]["sr"]),
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
    ax.set_ylabel("Success Rate (%) ↑ (Robustness)", fontsize=12, fontweight="bold")
    ax.set_title(
        "Performance Stability across Belief Conditions", fontsize=14, fontweight="bold"
    )

    # 그리드 및 범례
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="lower left", fontsize=10)

    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"그래프가 저장되었습니다: {output_path}")
    else:
        plt.show()


def plot_separate_metrics(data: dict, output_path: str | None = None) -> None:
    """
    sr과 Makespan을 각각의 그래프로 분리하여 보여줍니다.
    x축은 초기 믿음 조건, y축은 각 메트릭의 값을 나타냅니다.

    Args:
        data (dict): 시각화에 사용할 데이터.
        output_path (str | None): 그래프를 저장할 파일 경로. None이면 화면에 표시.
    """
    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    conditions = [
        "60s",
        "70s",
        "80s",
        "90s",
        "100s\n(Correct)",
        "110s",
        "120s",
        "130s",
        "140s",
    ]
    metrics_info = [
        (
            "sr",
            "Success Rate across Initial Belief Conditions",
            "Success Rate (%)",
        ),
    ]

    method_order = [
        "Ours",
        "Ours (w/o Mon.)",
        "DAG + CPM",
        "DAG + EDF",
        "ProgPrompt",
        "CaP",
    ]

    for col, (metric_key, title, ylabel) in enumerate(metrics_info):
        for name in method_order:
            # 데이터가 비어있으면(제외된 베이스라인) 그리지 않음
            if not data[name][metric_key]:
                continue

            d = data[name]
            y_data = d[metric_key]
            lw = 3.5 if "Default" in name else 1.8
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
                markersize=9,
            )

        ax.set_title(title, fontsize=14, pad=15, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=12, labelpad=10)
        ax.set_xlabel(
            r"Initial Belief Condition ($\Delta_0$)", fontsize=12, labelpad=10
        )
        ax.grid(True, linestyle="--", alpha=0.4)

        # Correct (index 2) 조건 강조 (빨간색 세로줄, 약간 투명하게)
        ax.axvline(x=4, color="red", alpha=0.3, linewidth=1.5)

    # 범례 통합
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="center right",
        bbox_to_anchor=(0.99, 0.65),  # bbox_to_anchor 조정
        ncol=1,
        fontsize=10,
        framealpha=0.9,
    )

    plt.tight_layout()
    # tight_layout 후 하단 여백 확보
    plt.subplots_adjust(bottom=0.20)
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"그래프가 저장되었습니다: {output_path}")
    else:
        plt.show()


def save_aggregated_json(
    data: dict, output_path: str = "aggregated_result.json"
) -> None:
    """
    통합된 결과(sr, Makespan)를 JSON 파일로 저장합니다.
    """
    # 저장할 데이터 구조 변환
    export_data = {}
    for method, metrics in data.items():
        if not metrics["sr"] and not metrics["makespan"]:
            continue

        method_results = []
        for i, condition in enumerate(INIT_LIST):
            # 인덱스 에러 방지
            sr_val = metrics["sr"][i] if i < len(metrics["sr"]) else 0.0
            makespan_val = (
                metrics["makespan"][i] if i < len(metrics["makespan"]) else 0.0
            )

            method_results.append(
                {
                    "init_condition": condition,
                    "sr": float(sr_val),
                    "makespan": float(makespan_val),
                }
            )

        export_data[method] = method_results

    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=4)
    print(f"통합 결과가 저장되었습니다: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
        sr(Success Rate)과 Makespan 성능 지표를 시각화합니다.
        두 가지 플롯 타입을 선택할 수 있습니다:
        1. trajectory: sr과 Makespan의 관계를 2D 궤적으로 표시 (기본값)
        2. separate: sr과 Makespan을 각각 별도의 라인 그래프로 표시
        """
    )
    parser.add_argument(
        "--root_path",
        type=Path,
        default="assets/results",
        help="데이터 파일 경로를 지정합니다.",
    )

    parser.add_argument(
        "--save_json",
        action="store_true",
        default=True,
        help="통합된 결과를 JSON 파일로 저장합니다 (기본값: True).",
    )

    args = parser.parse_args()

    load_data(args.root_path / "unified_analysis_summary.revised.json")

    if args.save_json:
        save_aggregated_json(DATA, args.root_path / "aggregated_result.json")

    # plot_trajectory(DATA, args.data_path / "trajectory.png")
    plot_separate_metrics(DATA, args.root_path / "separate.png")
