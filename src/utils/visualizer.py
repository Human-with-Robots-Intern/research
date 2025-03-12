import textwrap
from pathlib import Path
from typing import List
import sys,os
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np


from .constants import BEAM_WIDTH, LOG_ROUND, SIMULATION_DEPTH, VIS_PATH


def visualize(task_name, constraints, plan=None):
    folder_name = task_name
    save_folder_path = Path(VIS_PATH) / folder_name
    save_folder_path.mkdir(exist_ok=True)  # Create the folder if it doesn't exist

    visualize_graph(constraints, save_folder_path)
    if plan:
        plot_gantt_chart(plan, save_folder_path)


def visualize_graph(G: nx.DiGraph, save_folder_path="debug", is_display=False):
    def wrap_label(label, width=10):
        """너무 긴 라벨을 일정 너비로 줄바꿈해 반환"""
        return "\n".join(textwrap.wrap(label, width=width))

    # Graphviz layout 사용 (dot, neato, twopi 등)
    pos = nx.nx_agraph.graphviz_layout(G, prog="dot")

    plt.figure(figsize=(10, 8))

    # 노드 라벨 설정: G의 노드 정보에서 라벨을 가져오거나 노드ID를 사용
    node_labels = {}
    for node in G.nodes():
        # 예: 노드에 'label' 키가 있다면 가져오고, 없으면 노드ID(str(node)) 사용
        original_label = str(G.nodes[node].get("label", node))
        node_labels[node] = wrap_label(original_label, width=10)

    # 간선 라벨 설정
    edge_labels = {
        (u, v): f"{round(d['info']['Interval'], 2)}" for u, v, d in G.edges(data=True)
    }

    # 노드 색상 설정
    color_map = {
        "Monitoring": "pink",
        "Interaction": "lightblue",
    }
    node_colors = [
        color_map.get(G.nodes[node].get("subtask_type", "Interaction"), "gray")
        for node in G.nodes
    ]

    # 간선 색상 설정
    edge_colors = [
        "red" if data["info"]["IsCritical"] else "blue"
        for _, _, data in G.edges(data=True)
    ]

    # 1) 먼저 노드, 엣지만 그린다 (with_labels=False)
    nx.draw(
        G,
        pos,
        with_labels=False,
        node_size=1500,
        node_color=node_colors,
        edge_color=edge_colors,
        arrows=True,
    )

    # 2) 줄바꿈된 라벨을 따로 그린다
    nx.draw_networkx_labels(
        G,
        pos,
        labels=node_labels,
        font_size=8,
        font_weight="bold",
    )

    # 3) 간선 라벨 (rotate=False로 세로 돌림 방지)
    nx.draw_networkx_edge_labels(
        G, pos, edge_labels=edge_labels, font_color="black", rotate=False
    )

    # 범례(예시)
    red_edge = plt.Line2D([0], [0], color="red", lw=2)
    blue_edge = plt.Line2D([0], [0], color="blue", lw=2)
    plt.legend(
        [red_edge, blue_edge], ["Critical", "Not Critical"], loc="best", frameon=True
    )

    plt.title("Directed Acyclic Graph (DAG) with Edge Info")

    # 결과 저장
    plt.savefig(Path(save_folder_path) / "task_graph.png")
    if is_display:
        plt.show()
    else:
        plt.close()


def plot_gantt_chart(
    completed_subtasks: List, save_folder_path: str, is_display: bool = False
):
    """
    주어진 completed_subtasks를 순서대로 가정, Gantt 차트를 그린다.
    - start/end가 없으므로, make_gantt_data(...)로 start/end를 임시로 계산.
    - 하나의 Gantt로 시각화 (단일 path 시나리오).

    Args:
        completed_subtasks: 순서대로 수행된 Subtask 리스트
        save_folder_path: 결과물을 저장할 폴더
        is_display: True면 plt.show(), False면 plt.close()
    """
    if not completed_subtasks:
        print("No completed subtasks to plot.")
        return

    # 1) Gantt 데이터 구성
    gantt_data = make_gantt_data(completed_subtasks)
    # gantt_data: [ {"name": ..., "start":..., "end":...}, {...}, ...]

    # 2) Matplotlib barh로 시각화
    fig, ax = plt.subplots(figsize=(12, 6))

    task_names = [d["name"] for d in gantt_data]
    start_times = [d["start"] for d in gantt_data]
    durations = [d["end"] - d["start"] for d in gantt_data]

    y_pos = np.arange(len(task_names))
    bars = ax.barh(y_pos, durations, left=start_times, color="skyblue")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(task_names)
    ax.invert_yaxis()  # y축을 뒤집어 위가 0이 되도록
    ax.set_xlabel("Time")
    ax.set_title("Gantt Chart of Completed Subtasks")

    # 바 위에 시작/끝 시간을 표시
    for i, bar in enumerate(bars):
        st = start_times[i]
        et = st + durations[i]
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_y() + bar.get_height() / 2,
            f"{st:.1f} - {et:.1f}",
            ha="center",
            va="center",
            color="black",
            fontsize=8,
            fontweight="bold",
        )

    plt.tight_layout()

    # 3) 파일 저장
    save_path = (
        Path(save_folder_path)
        / f"{SIMULATION_DEPTH}_{BEAM_WIDTH}_task_schedule_gantt_{len(completed_subtasks)}.png"
    )
    plt.savefig(save_path)

    if is_display:
        plt.show()
    else:
        plt.close()


def make_gantt_data(completed_subtasks: List) -> List[dict]:
    """
    주어진 completed_subtasks를 순서대로 가정하고,
    Subtask마다 (start, end)를 누적 계산하여 반환.

    Returns:
        A list of dictionaries, each having:
          {
            "name": <subtask.name>,
            "start": <start_time>,
            "end": <end_time>
          }
    """
    gantt_info = []
    current_time = 0.0

    for st in completed_subtasks:
        if not st.duration:
            continue

        duration = st.duration.interval
        start = current_time
        end = start + duration

        gantt_info.append({"name": st.name, "start": start, "end": end})

        # 다음 Subtask의 시작 시간은 end로 누적
        current_time = end

    return gantt_info
