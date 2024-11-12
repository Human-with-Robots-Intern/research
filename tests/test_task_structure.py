import json
from unittest import TestCase, main

from src.core.task import ScheduledTask, Scheduler, Task, TaskGraph


class TestTaskSystem(TestCase):
    def setUp(self):
        # JSON 데이터 로드
        self.json_data = json.loads(
            """
            [
                {
                    "Task": "Cooking Toast",
                    "Subtasks": [
                        {
                            "Name": "Place_in Bread Toaster",
                            "Repetition": 1,
                            "Type": "Interaction",
                            "Duration": {
                                "Type": "Controllable",
                                "Interval": 1
                            },
                            "Executions": {
                                "Objects": {
                                    "Bread": 1,
                                    "Toaster": 1
                                },
                                "PrimitiveActions": [
                                    "Grasp Bread",
                                    "Place_in Bread Toaster"
                                ]
                            },
                            "TemporalConstraints": []
                        },
                        {
                            "Name": "Toggle_on Toaster",
                            "Repetition": 1,
                            "Type": "Interaction",
                            "Duration": {
                                "Type": "Controllable",
                                "Interval": 1
                            },
                            "Executions": {
                                "Objects": {
                                    "Toaster": 1
                                },
                                "PrimitiveActions": [
                                    "Toggle_on Toaster"
                                ]
                            },
                            "TemporalConstraints": [
                                {
                                    "Type": "After",
                                    "Subtask": "Place_in Bread Toaster",
                                    "Interval": 0,
                                    "Urgency": false
                                }
                            ]
                        },
                        {
                            "Subtask": "Toggle_off Toaster",
                            "Repetition": 1,
                            "Type": "Interaction",
                            "Duration": {
                                "Type": "Controllable",
                                "Interval": 1
                            },
                            "Executions": {
                                "Objects": {
                                    "Toaster": 1
                                },
                                "PrimitiveActions": [
                                    "Toggle_off Toaster"
                                ]
                            },
                            "TemporalConstraints": [
                                {
                                    "Type": "After",
                                    "Subtask": "Toggle_on Toaster",
                                    "Interval": 5,
                                    "Urgency": true
                                }
                            ]
                        },
                        {
                            "Subtask": "Set the Toast on a Table",
                            "Repetition": 1,
                            "Type": "Interaction",
                            "Duration": {
                                "Type": "Controllable",
                                "Interval": 1
                            },
                            "Executions": {
                                "Objects": {
                                    "Toast": 1,
                                    "Table": 1
                                },
                                "PrimitiveActions": [
                                    "Grasp Toast",
                                    "Place_on Table Toast"
                                ]
                            },
                            "TemporalConstraints": [
                                {
                                    "Type": "After",
                                    "Subtask": "Toggle_off Toaster",
                                    "Interval": 0,
                                    "Urgency": false
                                }
                            ]
                        }
                    ]
                }
            ]
            """
        )

    def test_task_parsing(self):
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

    def test_task_decomposition(self):
        tasks = Task.parse_instruction(self.json_data)
        task = tasks[0]

        # 디컴포지션 테스트 (현재 데이터는 Repetition이 1이라 변경 없음)
        task.decompose_subtasks()

        self.assertEqual(len(task.subtasks), 4)  # Repetition이 1이므로 분해 X
        self.assertEqual(task.subtasks[0].name, "Place_in Bread Toaster")

    def test_task_graph(self):
        tasks = Task.parse_instruction(self.json_data)
        task_graph = TaskGraph()

        # 그래프 생성
        task_graph.build_graph(tasks)

        # 그래프 노드 및 엣지 확인
        graph = task_graph.get_graph()
        self.assertEqual(len(graph.nodes), 4)
        self.assertEqual(len(graph.edges), 3)  # TemporalConstraints에 기반한 엣지 수

        # 특정 엣지 확인
        self.assertTrue(graph.has_edge("Place_in Bread Toaster", "Toggle_on Toaster"))
        self.assertTrue(graph.has_edge("Toggle_on Toaster", "Toggle_off Toaster"))

    def test_scheduler_simulation(self):
        tasks = Task.parse_instruction(self.json_data)
        subtasks = tasks[0].subtasks

        # 서브태스크를 기반으로 스케줄 생성
        task_plan = [
            ScheduledTask(
                name=subtask.name, start=0, end=0, duration=subtask.duration.interval
            )
            for subtask in subtasks
        ]

        scheduler = Scheduler(task_plan)

        # 스케줄 시뮬레이션
        simulated_plan = scheduler.simulate_task_plan()

        self.assertEqual(len(simulated_plan), 4)  # 4개의 서브태스크 스케줄 확인
        self.assertGreater(
            simulated_plan[0].end, simulated_plan[0].start
        )  # 종료 시간 > 시작 시간 확인
        self.assertGreater(
            simulated_plan[-1].end, simulated_plan[-2].end
        )  # 각 서브태스크가 순차적으로 실행됨을 확인


if __name__ == "__main__":
    main()
