import json
import logging
from pathlib import Path
from unittest import TestCase, main

import networkx as nx
import pytest
import yaml

from src.core.task import (
    Duration,
    Execution,
    Subtask,
    Task,
    TaskGraphBuilder,
    TemporalConstraint,
)
from src.utils.common import create_module_logger
from src.utils.config.constants import TASK_PATH
from src.utils.task import TaskUtil

logger = create_module_logger(__name__, module_log=True)


class TestTaskSystem(TestCase):
    def setUp(self):
        # JSON 데이터 로드
        self.file_path = Path(TASK_PATH) / "task_new.json"
        # Skip if file doesn't exist
        if not self.file_path.exists():
            self.skipTest(f"Task file not found: {self.file_path}")
        try:
            with open(self.file_path, "r") as file:
                # 파일 확장자에 따라 로더 선택
                if self.file_path.suffix == ".json":
                    self.task_data = json.load(file)
                elif self.file_path.suffix in [".yaml", ".yml"]:
                    self.task_data = yaml.safe_load(file)
                else:
                    raise ValueError(
                        f"Unsupported task file format: {self.file_path.suffix}"
                    )
        except Exception as e:
            self.fail(f"Failed to load task data from {self.file_path}: {e}")

    def test_instruction_parsing(self):
        # setUp에서 task_data 로드하므로 파일 경로는 필요 없음
        # 태스크 생성
        if not hasattr(self, "task_data"):  # setUp에서 스킵된 경우 처리
            self.skipTest("Task data not loaded in setUp.")
        tasks = Task.parse_instruction(self.task_data)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Cooking Toast")
        self.assertEqual(len(tasks[0].subtasks), 4)

        # 서브태스크 확인
        subtasks = tasks[0].subtasks
        self.assertEqual(subtasks[0].name, "Place_in Bread Toaster")
        self.assertEqual(subtasks[0].subtask_type, "Interaction")
        self.assertEqual(subtasks[1].name, "Toggle_on Toaster")
        self.assertEqual(subtasks[2].name, "Toggle_off Toaster")
        self.assertEqual(subtasks[3].name, "Set the Toast on a Table")

        # 테스트 통과 로그
        logger.info("test_instruction_parsing passed.")

    def test_task_decomposition(self):
        # setUp에서 task_data 로드
        if not hasattr(self, "task_data"):
            self.skipTest("Task data not loaded in setUp.")
        tasks = Task.parse_instruction(self.task_data)
        task = tasks[0]

        # 디컴포지션 테스트 (현재 데이터는 Repetition이 1이라 변경 없음)
        task.decompose_subtasks()

        self.assertEqual(len(task.subtasks), 5)  # Repetition이 1이므로 분해 X
        self.assertEqual(task.subtasks[0].name, "Place_in Bread Toaster_part_1")
        self.assertEqual(task.subtasks[0].subtask_type, "Interaction")
        logger.info("test_task_decomposition passed.")

    def test_task_graph(self):
        # setUp에서 task_data 로드
        if not hasattr(self, "task_data"):
            self.skipTest("Task data not loaded in setUp.")
        tasks = Task.parse_instruction(self.task_data)
        task_graph = TaskGraphBuilder()

        # 그래프 생성
        graph = task_graph.build_graph(tasks)

        # 그래프 노드 및 엣지 확인
        self.assertEqual(len(graph.nodes), 4)
        self.assertEqual(len(graph.edges), 3)  # TemporalConstraints에 기반한 엣지 수

        # 특정 엣지 확인
        self.assertTrue(graph.has_edge("Place_in Bread Toaster", "Toggle_on Toaster"))
        self.assertTrue(graph.has_edge("Toggle_on Toaster", "Toggle_off Toaster"))
        self.assertEqual(
            graph.nodes["Place_in Bread Toaster"]["subtask_type"], "Interaction"
        )
        logger.info("test_task_graph passed.")


# Fixtures
@pytest.fixture
def sample_execution():
    return Execution(
        objects={"plate": 1}, primitive_actions=["NAVIGATE_TO plate", "GRASP plate"]
    )


@pytest.fixture
def sample_duration():
    return Duration(type="Controllable", interval=5.0)


@pytest.fixture
def sample_constraint():
    return TemporalConstraint(
        constraint_type="After", subtask="Prep", interval=2.0, is_critical=False
    )


@pytest.fixture
def sample_subtask1(sample_execution, sample_duration):  # No constraint
    return Subtask(
        task_name="Wash",
        name="WashPlate1",
        repetition=1,
        subtask_type="Interaction",
        execution=sample_execution,
        duration=sample_duration,
        temporal_constraints=[],
    )


@pytest.fixture
def sample_subtask2(
    sample_execution, sample_duration, sample_constraint
):  # With constraint
    return Subtask(
        task_name="Wash",
        name="WashPlate2",
        repetition=1,
        subtask_type="Interaction",
        execution=sample_execution,
        duration=sample_duration,
        temporal_constraints=[sample_constraint],
    )


@pytest.fixture
def sample_subtask_repeat(sample_execution, sample_duration):  # With repetition
    return Subtask(
        task_name="Wash",
        name="WashMultiple",
        repetition=3,
        subtask_type="Interaction",
        execution=sample_execution,
        duration=sample_duration,
        temporal_constraints=[],
    )


# 테스트 케이스
def test_subtask_creation(sample_subtask1):
    """Subtask 객체 생성 및 기본 속성 확인"""
    assert sample_subtask1.name == "WashPlate1"
    assert sample_subtask1.repetition == 1
    assert sample_subtask1.subtask_type == "Interaction"
    assert len(sample_subtask1.temporal_constraints) == 0
    assert not sample_subtask1.decomposed  # Initially not decomposed


def test_subtask_with_constraint(sample_subtask2):
    """TemporalConstraint가 있는 Subtask 생성 확인"""
    assert len(sample_subtask2.temporal_constraints) == 1
    assert sample_subtask2.temporal_constraints[0].subtask == "Prep"
    assert sample_subtask2.temporal_constraints[0].constraint_type == "After"


def test_subtask_decompose_no_repeat(sample_subtask1):
    """Repetition=1인 Subtask 분해 시 자기 자신 반환 확인"""
    decomposed = sample_subtask1.decompose()
    assert isinstance(decomposed, list)
    assert len(decomposed) == 1
    assert decomposed[0] is sample_subtask1


def test_subtask_decompose_with_repeat(sample_subtask_repeat):
    """Repetition > 1인 Subtask 분해 및 내부 제약 조건 확인"""
    decomposed = sample_subtask_repeat.decompose()
    assert isinstance(decomposed, list)
    assert len(decomposed) == 3
    assert decomposed[0].name == "WashMultiple_part_1"
    assert decomposed[1].name == "WashMultiple_part_2"
    assert decomposed[2].name == "WashMultiple_part_3"
    assert decomposed[0].repetition == 1
    assert decomposed[1].repetition == 1
    assert decomposed[2].repetition == 1
    assert decomposed[0].subtask_type == "Interaction"
    assert len(decomposed[0].temporal_constraints) == 0
    assert len(decomposed[1].temporal_constraints) == 1
    assert decomposed[1].temporal_constraints[0].constraint_type == "After"
    assert decomposed[1].temporal_constraints[0].subtask == "WashMultiple_part_1"
    assert len(decomposed[2].temporal_constraints) == 1
    assert decomposed[2].temporal_constraints[0].constraint_type == "After"
    assert decomposed[2].temporal_constraints[0].subtask == "WashMultiple_part_2"


def test_task_creation(sample_subtask1, sample_subtask2):
    """Task 객체 생성 및 기본 속성 확인"""
    task = Task(name="DishWashing", subtasks=[sample_subtask1, sample_subtask2])
    assert task.name == "DishWashing"
    assert len(task.subtasks) == 2


def test_task_decompose_subtasks(sample_subtask1, sample_subtask_repeat):
    """Task 내 Subtask 분해 및 제약 조건 업데이트 확인"""
    final_sub = Subtask(
        task_name="Wash",
        name="FinalStep",
        repetition=1,
        subtask_type="End",
        execution=Execution(None, []),
        duration=Duration("Fixed", 1.0),
        temporal_constraints=[TemporalConstraint("After", "WashMultiple", 0, False)],
    )
    task = Task(
        name="ComplexWash", subtasks=[sample_subtask1, sample_subtask_repeat, final_sub]
    )
    original_subtask_count = len(task.subtasks)
    task.decompose_subtasks()  # 분해 실행

    assert len(task.subtasks) == (
        original_subtask_count - 1 + sample_subtask_repeat.repetition
    )
    final_step_in_task = next(s for s in task.subtasks if s.name == "FinalStep")
    assert len(final_step_in_task.temporal_constraints) == 1
    assert final_step_in_task.temporal_constraints[0].subtask == "WashMultiple_part_3"
    assert final_step_in_task.temporal_constraints[0].constraint_type == "After"


def test_task_graph_builder(sample_subtask1, sample_subtask2):
    """TaskGraphBuilder가 제약 조건에 따라 그래프를 올바르게 생성하는지 확인"""
    task = Task(name="DishWashing", subtasks=[sample_subtask1, sample_subtask2])
    builder = TaskGraphBuilder()
    graph = builder.build_graph([task])

    assert isinstance(graph, nx.DiGraph)
    assert "WashPlate1" in graph.nodes
    assert "WashPlate2" in graph.nodes
    assert "Prep" in graph.nodes

    assert graph.has_edge("Prep", "WashPlate2")
    edge_data = graph.get_edge_data("Prep", "WashPlate2")
    assert edge_data["info"]["Interval"] == 2.0
    assert edge_data["info"]["IsCritical"] is False
    assert edge_data["info"]["Type"] == "After"

    assert len(list(graph.predecessors("WashPlate1"))) == 0


# Task.from_dict, Subtask.from_dict 등 딕셔너리 파싱 관련 테스트 추가 필요
# TemporalConstraint 타입 ("Before" 등)에 따른 엣지 방향 테스트 추가 필요
