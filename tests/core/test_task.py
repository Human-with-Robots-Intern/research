import json
import logging
from pathlib import Path
from unittest import TestCase, main

from core.task import Task, TaskGraphBuilder
from utils.constants import TASK_PATH
from utils.common.util import create_module_logger

logger = create_module_logger(__name__, module_log=True)


class TestTaskSystem(TestCase):
    def setUp(self):
        # JSON 데이터 로드
        file_path = Path(TASK_PATH) / f"task_new.json"

        with open(file_path, "r") as file:
            self.json_data = json.load(file)

    def test_instruction_parsing(self):
        # 태스크 생성
        tasks = Task.parse_instruction(self.json_data)

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
        tasks = Task.parse_instruction(self.json_data)
        task = tasks[0]

        # 디컴포지션 테스트 (현재 데이터는 Repetition이 1이라 변경 없음)
        task.decompose_subtasks()

        self.assertEqual(len(task.subtasks), 5)  # Repetition이 1이므로 분해 X
        self.assertEqual(task.subtasks[0].name, "Place_in Bread Toaster_part_1")
        logger.info("test_task_decomposition passed.")

    def test_task_graph(self):
        tasks = Task.parse_instruction(self.json_data)
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
