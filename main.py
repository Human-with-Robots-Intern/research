from scheduling_problem import SchedulingProblem
from task import tasks
from visualization import ScheduleVisualizer


def main():
    # Create and define the scheduling problem
    scheduler = SchedulingProblem(tasks)
    scheduler.define_variables()
    scheduler.set_objective()
    scheduler.add_constraints()

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
