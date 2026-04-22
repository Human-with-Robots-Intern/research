"""Regression tests for primitive-action normalization edge cases."""

from src.models.task import Duration, Execution, Subtask, Task
from src.utils.io_utils import task_io
from src.utils.task.task_util import TaskUtil


def test_refine_primitive_actions_preserves_wait_duration(monkeypatch) -> None:
    """WAIT durations should not be treated as object ids during normalization."""

    monkeypatch.setattr(
        TaskUtil,
        "_load_object_ids",
        staticmethod(
            lambda _scene: {
                "all_object_ids_in_scene": ["Faucet|01", "Pot|01", "Sink|01"],
                "object_map_in_scene": {"RECEPTACLE": ["Sink|01"]},
                "object_categories": {"RECEPTACLE": ["Sink"]},
            }
        ),
    )
    monkeypatch.setattr(
        task_io,
        "load_scene_positions",
        lambda _scene: {
            "Faucet|01": (0.0, 0.0, 0.0),
            "Pot|01": (0.0, 0.0, 0.0),
            "Sink|01": (0.0, 0.0, 0.0),
        },
    )

    task = Task(
        name="Demo",
        subtasks=[
            Subtask(
                task_name="Demo",
                name="Turn Off Faucet after Filling Pot",
                repetition=1,
                subtask_type="Interaction",
                execution=Execution(
                    objects={},
                    primitive_actions=["WAIT 2.0", "TOGGLE_OFF Faucet|01"],
                ),
                duration=Duration(type="Interaction", interval=2),
                temporal_constraints=[],
            )
        ],
    )

    refined = TaskUtil.check_obj_id("mock_scene.json", [task])
    primitive_actions = refined[0].subtasks[0].execution.primitive_actions

    assert primitive_actions[0] == "WAIT 2.0"
    assert primitive_actions[1] == "TOGGLE_OFF Faucet|01"
