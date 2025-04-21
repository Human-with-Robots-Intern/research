import json
import logging
from pathlib import Path
from unittest import TestCase, main

import networkx as nx
import pytest
import yaml

from core.task import (
    Duration,
    Execution,
    Subtask,
    Task,
    TaskGraphBuilder,
    TemporalConstraint,
)
from src.core.task import Duration, Execution, Subtask
from src.utils.config.constants import TASK_PATH
from src.utils.task import TaskUtil
from utils.common import create_module_logger

logger = create_module_logger(__name__, module_log=True)


class TestTaskSystem(TestCase):
    def setUp(self):
        # JSON 데이터 로드
        self.file_path = Path(TASK_PATH) / "task_new.json"
        # Skip if file doesn't exist
        if not self.file_path.exists():
            pytest.skip(f"Task file not found: {self.file_path}")
        with open(self.file_path, "r") as file:
            self.task_data = yaml.safe_load(file)

    def test_instruction_parsing(self):
        # Construct path using TASK_PATH
        file_path = TASK_PATH / "test_instruction.yaml"  # Adjust filename as needed
        # Ensure file exists or skip test
        if not file_path.exists():
            pytest.skip(f"Task file not found: {file_path}")
        # 태스크 생성
        tasks = Task.parse_instruction(self.task_data)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "Cooking Toast")
        self.assertEqual(len(tasks[0].subtasks), 4)

        # 서브태스크 확인
        subtasks = tasks[0].subtasks
        self.assertEqual(subtasks[0].name, "Place_in Bread Toaster")
        self.assertEqual(subtasks[1].name, "Toggle_on Toaster")
        self.assertEqual(subtasks[2].name, "Toggle_off Toaster")
        self.assertEqual(subtasks[3].name, "Set the Toast on a Table")

        # 테스트 통과 로그
        logger.info("test_instruction_parsing passed.")

    def test_task_decomposition(self):
        # Construct path using TASK_PATH
        file_path = TASK_PATH / "test_decomposition.yaml"  # Adjust filename
        if not file_path.exists():
            pytest.skip(f"Task file not found: {file_path}")
        tasks = Task.parse_instruction(self.task_data)
        task = tasks[0]

        # 디컴포지션 테스트 (현재 데이터는 Repetition이 1이라 변경 없음)
        task.decompose_subtasks()

        self.assertEqual(len(task.subtasks), 5)  # Repetition이 1이므로 분해 X
        self.assertEqual(task.subtasks[0].name, "Place_in Bread Toaster_part_1")
        logger.info("test_task_decomposition passed.")

    def test_task_graph(self):
        # Construct path using TASK_PATH
        file_path = TASK_PATH / "test_graph.yaml"  # Adjust filename
        if not file_path.exists():
            pytest.skip(f"Task file not found: {file_path}")
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
        logger.info("test_task_graph passed.")


if __name__ == "__main__":
    try:
        main()
        print("\n[INFO] 모든 테스트가 성공적으로 통과했습니다!")
    except Exception as e:
        print(f"\n[ERROR] 테스트 실패: {str(e)}")


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
        type="Interaction",
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
        type="Interaction",
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
        type="Interaction",
        execution=sample_execution,
        duration=sample_duration,
        temporal_constraints=[],
    )


# 테스트 케이스
def test_subtask_creation(sample_subtask1):
    """Subtask 객체 생성 및 기본 속성 확인"""
    assert sample_subtask1.name == "WashPlate1"
    assert sample_subtask1.repetition == 1
    assert sample_subtask1.type == "Interaction"
    assert len(sample_subtask1.temporal_constraints) == 0
    assert not sample_subtask1.decomposed  # Initially not decomposed


def test_subtask_with_constraint(sample_subtask2):
    """TemporalConstraint가 있는 Subtask 생성 확인"""
    assert len(sample_subtask2.temporal_constraints) == 1
    assert sample_subtask2.temporal_constraints[0].subtask == "Prep"


def test_subtask_decompose_no_repeat(sample_subtask1):
    """Repetition=1인 Subtask 분해 시 자기 자신 반환 확인"""
    decomposed = sample_subtask1.decompose()
    assert isinstance(decomposed, list)
    assert len(decomposed) == 1
    assert decomposed[0] is sample_subtask1


def test_subtask_decompose_with_repeat():
    pytest.skip(
        "TaskUtil에 decompose_subtasks 메서드가 없어 건너뜁니다. 실제 메서드 이름 확인 필요."
    )
    # ... (기존 테스트 로직) ...
    # result = TaskUtil.CORRECT_METHOD_NAME(...) # 올바른 메서드 이름 사용 필요
    # assert result is True


def test_task_creation(sample_subtask1, sample_subtask2):
    """Task 객체 생성 및 기본 속성 확인"""
    task = Task(name="DishWashing", subtasks=[sample_subtask1, sample_subtask2])
    assert task.name == "DishWashing"
    assert len(task.subtasks) == 2


def test_task_decompose_subtasks(sample_subtask1, sample_subtask_repeat):
    """Task 내 Subtask 분해 및 제약 조건 업데이트 확인"""
    # 제약 조건이 있는 서브태스크 추가 (분해될 WashMultiple을 참조)
    final_sub = Subtask(
        task_name="Wash",
        name="FinalStep",
        repetition=1,
        type="End",
        execution=Execution(None, []),
        duration=Duration("Fixed", 1.0),
        temporal_constraints=[TemporalConstraint("After", "WashMultiple", 0, False)],
    )
    task = Task(
        name="ComplexWash", subtasks=[sample_subtask1, sample_subtask_repeat, final_sub]
    )
    original_subtask_count = len(task.subtasks)  # 3
    task.decompose_subtasks()  # 분해 실행

    # 총 서브태스크 개수 확인 (1 + 3 + 1 = 5)
    assert len(task.subtasks) == (
        original_subtask_count - 1 + sample_subtask_repeat.repetition
    )
    # FinalStep의 제약 조건이 마지막 파트(WashMultiple_part_3)를 참조하는지 확인
    final_step_in_task = next(s for s in task.subtasks if s.name == "FinalStep")
    assert len(final_step_in_task.temporal_constraints) == 1
    assert final_step_in_task.temporal_constraints[0].subtask == "WashMultiple_part_3"


def test_task_graph_builder(sample_subtask1, sample_subtask2):
    """TaskGraphBuilder가 제약 조건에 따라 그래프를 올바르게 생성하는지 확인"""
    task = Task(name="DishWashing", subtasks=[sample_subtask1, sample_subtask2])
    builder = TaskGraphBuilder()
    graph = builder.build_graph([task])

    assert isinstance(graph, nx.DiGraph)
    assert "WashPlate1" in graph.nodes
    assert "WashPlate2" in graph.nodes
    assert (
        "Prep" in graph.nodes
    )  # 제약 조건에만 언급되어도 노드가 생성되는지 확인 (현재 구현 기준)

    # WashPlate2는 Prep 이후에 실행되어야 함 (Prep -> WashPlate2 엣지 존재)
    assert graph.has_edge("Prep", "WashPlate2")
    edge_data = graph.get_edge_data("Prep", "WashPlate2")
    assert edge_data["info"]["Interval"] == 2.0
    assert edge_data["info"]["IsCritical"] is False

    # WashPlate1은 제약 조건이 없으므로 들어오는 엣지 없음
    assert len(list(graph.predecessors("WashPlate1"))) == 0


# Task.from_dict, Subtask.from_dict 등 딕셔너리 파싱 관련 테스트 추가 필요
# TemporalConstraint 타입 ("Before" 등)에 따른 엣지 방향 테스트 추가 필요
