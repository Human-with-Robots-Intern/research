import matplotlib.pyplot as plt
import networkx as nx
from anytree.exporter import UniqueDotExporter


def visualize_tree(schedules):
    UniqueDotExporter(schedules).to_picture("results/task_tree.png")


def visualize_graph(G):
    pos = nx.spring_layout(G, k=0.5)  # k 값 조정
    plt.figure(figsize=(10, 8))  # fig 크기 조정
    edge_labels = {(u, v): f"{d['info']['Interval']}" for u, v, d in G.edges(data=True)}
    node_colors = "lightblue"
    edge_colors = [
        "red" if data["info"]["Urgency"] else "blue"
        for _, _, data in G.edges(data=True)
    ]

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
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color="black")

    # 범례를 추가하기 위한 핸들 생성
    red_edge = plt.Line2D([0], [0], color="red", lw=2)
    blue_edge = plt.Line2D([0], [0], color="blue", lw=2)

    plt.legend(
        [red_edge, blue_edge], ["Urgent", "Not Urgent"], loc="best", frameon=True
    )

    plt.title("Directed Acyclic Graph (DAG) with Edge Info")
    plt.savefig("results/task_graph.png")
    plt.show()
