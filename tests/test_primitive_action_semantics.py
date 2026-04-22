from __future__ import annotations

from src.utils.task.primitive_action_semantics import (
    choose_primary_issue_group,
    classify_issue_group,
    find_held_object_semantic_issues,
)


def _task(subtask_name: str, actions: list[str]) -> list[dict]:
    return [
        {
            "Task": "Synthetic Task",
            "Subtasks": [
                {
                    "Name": subtask_name,
                    "Executions": {"PrimitiveActions": actions},
                }
            ],
        }
    ]


def test_detects_place_without_hold_for_fill_pot() -> None:
    task_data = _task(
        "Fill Pot with Water",
        [
            "NAVIGATE_TO Pot|1",
            "PLACE_INSIDE Sink|1|SinkBasin",
            "TOGGLE_ON Faucet|1",
        ],
    )

    issues = find_held_object_semantic_issues(task_data)

    assert len(issues) == 1
    assert issues[0].issue_type == "place_without_hold"
    assert classify_issue_group(issues[0]) == (
        "Pot placed into sink without first grasping pot"
    )


def test_groups_stove_after_pan_as_missing_regrasp() -> None:
    task_data = _task(
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

    issues = find_held_object_semantic_issues(task_data)

    assert len(issues) == 1
    assert classify_issue_group(issues[0]) == (
        "Container placed onto stove after ingredient placement, without re-grasp"
    )
    assert choose_primary_issue_group(issues) == (
        "Container placed onto stove after ingredient placement, without re-grasp"
    )


def test_valid_pick_and_place_sequence_has_no_semantic_issue() -> None:
    task_data = _task(
        "Place Bread in Microwave",
        [
            "NAVIGATE_TO Bread|1",
            "GRASP Bread|1",
            "NAVIGATE_TO Microwave|1",
            "PLACE_INSIDE Microwave|1",
        ],
    )

    assert find_held_object_semantic_issues(task_data) == []
