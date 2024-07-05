import matplotlib.pyplot as plt
import pandas as pd

from concept.task import get_all_subtasks


def visualize3(schedule):
    fig, ax = plt.subplots(figsize=(10, 8))

    for i, task in schedule.iterrows():
        task["duration"] = task["end"] - task["start"]
        ax.barh(
            task["name"],
            task["duration"],
            left=task["start"],
            color="skyblue",
            edgecolor="black",
        )

        ax.text(
            task["start"] + task["duration"] / 2,
            task["name"],
            f'{task["start"]}~{task["start"]+task["duration"]} ({task["duration"]})',
            ha="center",
            va="center",
            color="black",
        )

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Tasks")
    ax.set_title("Household Tasks Scheduling Gantt Chart")
    plt.grid(axis="x", linestyle="--", alpha=0.7)

    plt.show()


def visualize2(schedule):
    fig, ax = plt.subplots(figsize=(10, 8))

    for i, task in schedule.iterrows():
        ax.barh(
            task["name"],
            task["duration"],
            left=task["start"],
            color="skyblue",
            edgecolor="black",
        )

        ax.text(
            task["start"] + task["duration"] / 2,
            task["name"],
            f'{task["start"]}~{task["start"]+task["duration"]} ({task["duration"]})',
            ha="center",
            va="center",
            color="black",
        )

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Tasks")
    ax.set_title("Household Tasks Scheduling Gantt Chart")
    plt.grid(axis="x", linestyle="--", alpha=0.7)

    plt.show()


def visualize(tasks, schedule):

    subtask_task_dict = get_all_subtasks(tasks)
    # Create a DataFrame for visualization
    df = pd.DataFrame(schedule, columns=["Task", "Start", "End"])

    # Extract task names and phases
    df["Task_Name"] = df["Task"].apply(lambda x: subtask_task_dict[x])
    df["Subtask_Name"] = df["Task"]

    # Sort the DataFrame
    df.sort_values(by=["Start"], inplace=True)

    # Plot the Gantt chart
    fig, ax = plt.subplots(figsize=(10, 8))

    # Track y offsets for each task name to avoid overlap
    y_offsets = {task_name: 0 for task_name in df["Task_Name"].unique()}
    offset_increment = 0.3

    for i, task in df.iterrows():
        ax.barh(
            task["Task_Name"],
            task["End"] - task["Start"],
            left=task["Start"],
            color="skyblue",
            edgecolor="black",
        )
        # Adjust y position to prevent text overlap
        y_position = (
            list(df["Task_Name"].unique()).index(task["Task_Name"])
            + y_offsets[task["Task_Name"]]
        )
        ax.text(
            (task["Start"] + task["End"]) / 2,
            y_position,
            f'{task["Subtask_Name"]}',
            ha="center",
            va="center",
            color="black",
        )
        # Increment the offset for the next subtask of the same task name
        y_offsets[task["Task_Name"]] += 0.5 * offset_increment

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Tasks")
    ax.set_title("Household Tasks Scheduling Gantt Chart")
    plt.grid(axis="x", linestyle="--", alpha=0.7)

    plt.show()


# Example usage
# Assuming `tasks` and `schedule` are defined
# visualize(tasks, schedule)
