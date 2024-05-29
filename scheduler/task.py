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


def get_all_controllable_subtasks(tasks):
    controllable_subtasks = []
    for task in tasks.values():
        controllable_subtasks.extend(task.get_controllable_subtasks())
    return controllable_subtasks
