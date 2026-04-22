"""Regression tests for held-object semantic repair in TaskUtil."""

from src.models.task import Duration, Execution, Subtask, Task
from src.utils.task.task_util import TaskUtil


def _make_subtask(name: str, actions: list[str]) -> Subtask:
    return Subtask(
        task_name="Synthetic Task",
        name=name,
        repetition=1,
        subtask_type="Interaction",
        execution=Execution(objects={}, primitive_actions=actions),
        duration=Duration(type="Interaction", interval=0),
        temporal_constraints=[],
    )


def test_repair_inserts_grasp_only_when_container_is_current_anchor() -> None:
    task = Task(
        name="Cook Egg",
        subtasks=[
            _make_subtask(
                "Place Egg on StoveBurner",
                [
                    "NAVIGATE_TO Egg|1",
                    "GRASP Egg|1",
                    "NAVIGATE_TO Pan|1",
                    "PLACE_INSIDE Pan|1",
                    "NAVIGATE_TO StoveBurner|1",
                    "PLACE_ON_TOP StoveBurner|1",
                ],
            )
        ],
    )

    TaskUtil.repair_held_object_semantics([task])

    assert task.subtasks[0].execution.primitive_actions == [
        "NAVIGATE_TO Egg|1",
        "GRASP Egg|1",
        "NAVIGATE_TO Pan|1",
        "PLACE_INSIDE Pan|1",
        "GRASP Pan|1",
        "NAVIGATE_TO StoveBurner|1",
        "PLACE_ON_TOP StoveBurner|1",
    ]


def test_repair_uses_cross_subtask_history_for_pot_to_sink() -> None:
    task = Task(
        name="Boil Potato",
        subtasks=[
            _make_subtask(
                "Place Potato in Pot",
                [
                    "NAVIGATE_TO Potato|1",
                    "GRASP Potato|1",
                    "NAVIGATE_TO Pot|1",
                    "PLACE_INSIDE Pot|1",
                ],
            ),
            _make_subtask(
                "Fill Pot with Water",
                [
                    "NAVIGATE_TO Sink|1|SinkBasin",
                    "PLACE_INSIDE Sink|1|SinkBasin",
                    "TOGGLE_ON Faucet|1",
                ],
            ),
        ],
    )

    TaskUtil.repair_held_object_semantics([task])

    assert task.subtasks[1].execution.primitive_actions == [
        "GRASP Pot|1",
        "NAVIGATE_TO Sink|1|SinkBasin",
        "PLACE_INSIDE Sink|1|SinkBasin",
        "TOGGLE_ON Faucet|1",
    ]


def test_repair_inserts_navigate_and_grasp_when_anchor_has_drifted() -> None:
    task = Task(
        name="Cook Egg",
        subtasks=[
            _make_subtask(
                "Place Egg in Pan",
                [
                    "NAVIGATE_TO Egg|1",
                    "GRASP Egg|1",
                    "NAVIGATE_TO Pan|1",
                    "PLACE_INSIDE Pan|1",
                ],
            ),
            _make_subtask(
                "Move Pan to Stove",
                [
                    "NAVIGATE_TO CounterTop|1",
                    "PLACE_ON_TOP StoveBurner|1",
                ],
            ),
        ],
    )

    TaskUtil.repair_held_object_semantics([task])

    assert task.subtasks[1].execution.primitive_actions == [
        "NAVIGATE_TO CounterTop|1",
        "NAVIGATE_TO Pan|1",
        "GRASP Pan|1",
        "PLACE_ON_TOP StoveBurner|1",
    ]
