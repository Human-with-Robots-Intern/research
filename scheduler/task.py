class Task:
    def __init__(self, name, phases):
        self.name = name
        self.phases = phases

    def get_controllable_subtasks(self):
        return [
            f"{self.name}_{phase}"
            for phase, duration, task_type in self.phases
            if task_type == "Controllable"
        ]

    def get_duration(self):
        return sum(duration for _, duration, _ in self.phases)


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


def get_all_controllable_subtasks(tasks):
    controllable_subtasks = []
    for task in tasks.values():
        controllable_subtasks.extend(task.get_controllable_subtasks())
    return controllable_subtasks
