import matplotlib.pyplot as plt
import networkx as nx


def visualize_graph(G, is_display):
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
    plt.savefig("results/task_graph.png")

    # Display the plot
    if is_display:
        plt.show()
