import matplotlib.pyplot as plt
import pandas as pd


def visualize(tasks, schedule):
    # Create a DataFrame for visualization
    df = pd.DataFrame(schedule, columns=["Task", "Start", "End"])

    # Extract task names and phases
    df["Task_Name"] = df["Task"].apply(lambda x: x.split(":")[0])
    df["Subtask_Name"] = df["Task"].apply(lambda x: x.split(":")[-1])

    # Sort the DataFrame
    df.sort_values(by=["Start"], inplace=True)

    # Plot the Gantt chart
    fig, ax = plt.subplots(figsize=(10, 6))

    for i, task in df.iterrows():
        ax.barh(
            task["Task_Name"],
            task["End"] - task["Start"],
            left=task["Start"],
            color="skyblue",
            edgecolor="black",
        )
        ax.text(
            (task["Start"] + task["End"]) / 2,
            task["Task_Name"],
            f'{task["Subtask_Name"]}',
            ha="center",
            va="center",
            color="black",
        )

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Tasks")
    ax.set_title("Household Tasks Scheduling Gantt Chart")
    plt.grid(axis="x", linestyle="--", alpha=0.7)

    plt.show()
