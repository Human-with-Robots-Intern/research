# utils/viz/main_visualizer.py
import json
from pathlib import Path

import matplotlib.pyplot as plt

from .gantt import assign_chain_numbers, compute_start_times, plot_subtask_timeline
from .union_find import merge_groups


def load_json_data(file_path: str) -> dict:
    """
    JSON 파일을 로드해 dict로 반환
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def plot_multi_approach_gantt():
    """
    OURS, CPM, EDF 3개 json 파일을 비교하여 Gantt 차트를 생성/시각화/저장하는 예시.
    """
    ours_data = load_json_data("assets/gantt_data/ours.json")
    cpm_data = load_json_data("assets/gantt_data/cpm.json")
    edf_data = load_json_data("assets/gantt_data/edf.json")

    for task_name in ours_data.keys():
        ours = ours_data[task_name]
        cpm = cpm_data[task_name]
        edf = edf_data[task_name]

        # 서브태스크 이름
        ours_subtasks = ours["complete_schedule"]
        cpm_subtasks = cpm["complete_schedule"]
        edf_subtasks = edf["complete_schedule"]

        # duration
        ours_durations = [ours[s]["scheduler"] for s in ours_subtasks]
        cpm_durations = [cpm[s]["scheduler"] for s in cpm_subtasks]
        edf_durations = [edf[s]["scheduler"] for s in edf_subtasks]

        # constraints -> merge groups
        ours_dep = merge_groups(ours["constraints"])
        cpm_dep = merge_groups(cpm["constraints"])
        edf_dep = merge_groups(edf["constraints"])

        # 체인 번호 계산
        chains_ours, indep_ours = assign_chain_numbers(
            ours_subtasks, ours_dep, ours_durations
        )
        chains_cpm, indep_cpm = assign_chain_numbers(
            cpm_subtasks, cpm_dep, cpm_durations
        )
        chains_edf, indep_edf = assign_chain_numbers(
            edf_subtasks, edf_dep, edf_durations
        )

        # 시작 시간/총 시간
        ours_start, ours_total = compute_start_times(ours_durations)
        cpm_start, cpm_total = compute_start_times(cpm_durations)
        edf_start, edf_total = compute_start_times(edf_durations)

        min_time_all = min(ours_total, cpm_total, edf_total)
        max_time_all = max(ours_total, cpm_total, edf_total)

        fig, axes = plt.subplots(
            nrows=3, ncols=1, figsize=(10, 8), sharex=False, constrained_layout=True
        )
        fig.suptitle("Three DataSets with Shortest End-Time Mark", fontsize=14)

        # Ours
        plot_subtask_timeline(
            axes[0],
            ours_subtasks,
            ours_durations,
            chains_ours,
            ours_start,
            max_time_all,
            indep_ours,
        )
        axes[0].set_title("OURS")
        axes[0].axvline(min_time_all, color="r", linewidth=2)
        axes[0].text(
            min_time_all,
            axes[0].get_ylim()[1],
            "Shortest End",
            color="r",
            ha="left",
            va="top",
        )

        # CPM
        plot_subtask_timeline(
            axes[1],
            cpm_subtasks,
            cpm_durations,
            chains_cpm,
            cpm_start,
            max_time_all,
            indep_cpm,
        )
        axes[1].set_title("CPM")
        axes[1].axvline(min_time_all, color="r", linewidth=2)
        axes[1].text(
            min_time_all,
            axes[1].get_ylim()[1],
            "Shortest End",
            color="r",
            ha="left",
            va="top",
        )

        # EDF
        plot_subtask_timeline(
            axes[2],
            edf_subtasks,
            edf_durations,
            chains_edf,
            edf_start,
            max_time_all,
            indep_edf,
        )
        axes[2].set_title("EDF")
        axes[2].axvline(min_time_all, color="r", linewidth=2)
        axes[2].text(
            min_time_all,
            axes[2].get_ylim()[1],
            "Shortest End",
            color="r",
            ha="left",
            va="top",
        )

        # 시각화/저장
        save_path = Path(f"assets/gantt_data/{task_name}.png")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=300)
        print(f"Saved figure: {save_path}")
        plt.close()


def main():
    # 간단한 예시
    plot_multi_approach_gantt()

    # 다른 시각화 예: DAG
    # import networkx as nx
    # from networkx import DiGraph
    #
    # G = nx.DiGraph()
    # G.add_node("A", label="Start", subtask_type="Monitoring")
    # G.add_node("B", label="Middle")
    # G.add_node("C", label="End", subtask_type="Interaction")
    # G.add_edge("A", "B", info={"Interval":2.5, "IsCritical":True})
    # G.add_edge("B", "C", info={"Interval":1.0, "IsCritical":False})
    #
    # visualize_graph(G, save_path="test_dag.png", is_display=False)


if __name__ == "__main__":
    main()
