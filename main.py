from scheduler.solver import SchedulingProblem
from scheduler.task import Task
from visualizer import *


def main():

    tasks = {
        "Cook_Steak": Task(
            "Cook_Steak",
            [
                ("Start", 5, "Controllable"),
                ("Continue", 20, "Uncontrollable"),
                ("End", 10, "Controllable"),
            ],
        ),
        "Wash_Dishes": Task(
            "Wash_Dishes",
            [
                ("Start", 5, "Controllable"),
                ("Continue", 5, "Controllable"),
                ("End", 5, "Controllable"),
            ],
        ),
        "Clean_Living_Room": Task(
            "Clean_Living_Room",
            [
                ("Start", 5, "Controllable"),
                ("Continue", 5, "Controllable"),
                ("End", 5, "Controllable"),
            ],
        ),
        "Laundry": Task(
            "Laundry",
            [
                ("Start", 5, "Controllable"),
                ("Continue", 45, "Uncontrollable"),
                ("End", 5, "Controllable"),
            ],
        ),
    }

    # Create and define the scheduling problem
    scheduler = SchedulingProblem(tasks)

    # Solve the problem
    status = scheduler.solve()
    print("Status:", status)

    # Extract and print the schedule
    schedule = scheduler.extract_schedule()
    for task, start, end in schedule:
        print(f"{task}: Start at {start}, Complete at {end}")

    # Visualize the schedule
    ScheduleVisualizer.visualize(schedule)


if __name__ == "__main__":
    main()
