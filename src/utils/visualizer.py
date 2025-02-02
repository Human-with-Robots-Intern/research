from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from core.task import Subtask
from utils.constants import VIS_PATH


def visualize(task_name, constraints, plan=None):
    folder_name = task_name
    save_folder_path = Path(VIS_PATH) / folder_name
    save_folder_path.mkdir(exist_ok=True)  # Create the folder if it doesn't exist

    visualize_graph(constraints, save_folder_path)
    if plan:
        plot_gantt_chart(plan, save_folder_path)


def visualize_graph(G: nx.DiGraph, save_folder_path, is_display=False):
    pos = nx.spring_layout(G, k=0.5)  # Adjusting the k value for layout optimization
    plt.figure(figsize=(10, 8))  # Adjust the figure size to make it more readable

    # Define edge labels based on the Interval attribute from edge data
    edge_labels = {(u, v): f"{d['info']['Interval']}" for u, v, d in G.edges(data=True)}

    # Define a color map for different subtask types
    color_map = {
        "Monitoring": "pink",
        "Interaction": "lightblue",
    }

    # Assign colors to nodes based on their subtask type
    node_colors = [
        color_map.get(G.nodes[node].get("subtask_type", "Interaction"), "gray")
        for node in G.nodes
    ]

    # Assign colors to edges based on is_critical attribute
    edge_colors = [
        "red" if data["info"]["IsCritical"] else "blue"
        for _, _, data in G.edges(data=True)
    ]

    # Draw the nodes with specified attributes
    nx.draw(
        G,
        pos,
        with_labels=True,
        node_size=1500,
        node_color=node_colors,
        font_size=10,
        font_weight="bold",
        edge_color=edge_colors,
        arrows=True,
    )

    # Draw edge labels with specified font color
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color="black")

    # Create handles for legend items
    red_edge = plt.Line2D([0], [0], color="red", lw=2)
    blue_edge = plt.Line2D([0], [0], color="blue", lw=2)

    # Add a legend to the plot
    plt.legend(
        [red_edge, blue_edge], ["Critical", "Not Critical"], loc="best", frameon=True
    )

    # Set the title of the plot
    plt.title("Directed Acyclic Graph (DAG) with Edge Info")

    # Save the plot to a file
    plt.savefig(Path(save_folder_path) / "task_graph.png")

    if is_display:
        plt.show()
    else:
        plt.close()


from pathlib import Path
from typing import List, Optional

import matplotlib.pyplot as plt
import numpy as np


def plot_gantt_chart(
    completed_subtasks: List[Subtask], save_folder_path: str, is_display: bool = False
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
    save_path = Path(save_folder_path) / "task_schedule_gantt.png"
    plt.savefig(save_path)

    if is_display:
        plt.show()
    else:
        plt.close()


def make_gantt_data(completed_subtasks: List[Subtask]) -> List[dict]:
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
