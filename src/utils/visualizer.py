from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from anytree import Node
from anytree.exporter import UniqueDotExporter

from utils.constants import VIS_PATH


def visualize(task_name, constraints, task_tree=None, opt_task_tree=None):
    folder_name = task_name
    save_folder_path = Path(VIS_PATH) / folder_name
    save_folder_path.mkdir(exist_ok=True)  # Create the folder if it doesn't exist

    visualize_graph(constraints, save_folder_path)
    if task_tree:
        visualize_tree(task_tree, opt_task_tree, save_folder_path)
        if opt_task_tree:
            plot_gantt_chart(opt_task_tree, save_folder_path)


def visualize_tree(task_tree, opt_task_tree, save_folder_path):
    """Export the visualizations of the complete and optimal task trees."""

    if task_tree and opt_task_tree:

        UniqueDotExporter(task_tree).to_picture(
            Path(save_folder_path) / "task_tree.png"
        )
        UniqueDotExporter(opt_task_tree).to_picture(
            Path(save_folder_path) / "opt_task_tree.png"
        )
    elif task_tree:
        UniqueDotExporter(task_tree).to_picture(
            Path(save_folder_path) / "task_tree.png"
        )
    elif opt_task_tree:
        UniqueDotExporter(opt_task_tree).to_picture(
            Path(save_folder_path) / "opt_task_tree.png"
        )


def visualize_graph(G: nx.DiGraph, save_folder_path):
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

    # Assign colors to edges based on urgency
    edge_colors = [
        "red" if data["info"]["Urgency"] else "blue"
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
        [red_edge, blue_edge], ["Urgent", "Not Urgent"], loc="best", frameon=True
    )

    # Set the title of the plot
    plt.title("Directed Acyclic Graph (DAG) with Edge Info")

    # Save the plot to a file
    plt.savefig(Path(save_folder_path) / "task_graph.png")


def plot_gantt_chart(opt_task_tree, save_folder_path, is_display=False):
    """
    Plot a Gantt chart for the given task tree, visualizing each path as a separate subplot.

    Args:
        opt_task_tree (Node): The root of the filtered task tree.
        save_folder_path (str): The path where the plot will be saved.
        is_display (bool): Whether to display the plot after saving.
    """

    # 모든 리프 노드를 순회
    leaf_nodes = opt_task_tree.leaves
    n_plots = len(leaf_nodes)

    # 서브플롯 생성
    fig, axs = plt.subplots(n_plots, 1, figsize=(24, 4 * n_plots))
    axs = np.atleast_1d(axs)  # Ensure axs is always iterable

    for idx, leaf_node in enumerate(leaf_nodes):
        # 각 리프에서 루트까지의 경로 추출
        tasks = [node.name for node in leaf_node.path]
        start_times = [node.start for node in leaf_node.path]
        durations = [node.end - node.start for node in leaf_node.path]  # Duration 계산

        # 현재 경로의 Gantt 차트 그리기
        ax = axs[idx]
        y_pos = range(len(tasks))
        bars = ax.barh(
            y_pos, durations, left=start_times, align="center", color="skyblue"
        )
        ax.set_yticks(y_pos)
        ax.set_yticklabels(tasks)
        ax.invert_yaxis()
        ax.set_xlabel("Time")
        ax.set_title(f"Task Schedule")

        # 시작/종료 시간 레이블 추가
        for j, bar in enumerate(bars):
            end_time = start_times[j] + durations[j]
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_y() + bar.get_height() / 2,
                f"{start_times[j]} - {end_time}",
                ha="center",
                va="center",
                color="black",
                fontsize=8,
                weight="bold",
            )

    plt.tight_layout()  # 반복문 밖에서 호출

    # 파일 저장
    save_path = Path(save_folder_path) / "task_schedule_paths.png"
    plt.savefig(save_path)

    # 플롯 표시 여부
    if is_display:
        plt.show()
    else:
        plt.close()
