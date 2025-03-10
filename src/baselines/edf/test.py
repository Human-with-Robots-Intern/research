import heapq
import json
from typing import List, Optional, Tuple
import networkx as nx
import matplotlib.pyplot as plt
import os

from utils.task_util import build_tasks_and_constraints
from utils.make_gantt import plot_gantt_chart
from utils.action_handler import ActionHandler  # Import ActionHandler
from utils.constants import NAV_STEP_DURATION  # Import NAV_STEP_DURATION # No need. 상수 파일에 있음
from utils.task import Task  # Import Task

from ithor.handlers.navigation_handler import build_navigation_graph
from utils.runner_ai2thor import execute_subtask, init_ai2thor

# with open("data/FloorPlan1_navigation_time.json") as f: # 삭제
#     data = json.load(f) # 삭제


class EDFInfo:
    """
    EDF를 위해 전역적으로 필요한 정보를 한 곳에 모으는 구조체:
    - current time: 현재 시간
    - is_urgent: 현재 시간에 긴급한 태스크가 있는지 여부
    - before_urgent: 긴급한 태스크가 있는 경우, 전에 실행한 태스크 이름
    - after_urgent: 긴급한 태스크가 있는 경우, 후에 실행할 태스크 이름
    - finished_subtasks: 완료된 태스크 리스트
    - remaining_subtasks: 남은 태스크 리스트
    - final_loc: 마지막 위치
    """

    def __init__(self, subtasks, constraints: nx.DiGraph, nav_graph):  # Add nav_graph
        # edge 정보 [('Prepare and Cook Fried Egg', 'Turn off stove after cooking', {'info': {'Type': 'After', 'Interval': 15, 'IsCritical': True}})]
        self.graph = constraints
        self.subtasks = subtasks
        # 아래는 모두 업데이트 필요
        self.current_time: float = 0.0
        self.is_critical: bool = False
        self.before_subtask: Optional[str] = None  # 이름만 포함됨
        self.after_subtask: Optional[str] = None  # 이름만 포함됨
        self.finished_subtasks: List[Task] = []
        self.remaining_subtasks: List[Task] = subtasks
        self.final_loc: str = "agent"
        self.after_loc: str = None  # dependency 가 있는 경우에만 존재하고, 가야할 위치.
        # time slot 끝나는 시간임
        self.dependence_start_time: float = 0.0
        self.nav_graph = nav_graph  # Store nav_graph

    def update(self, subtask):
        """
        완료된 subtask를 받아 위 정보들을 update 함
        """
        self.finished_subtasks.append(subtask)
        self.remaining_subtasks.remove(subtask)
        self.final_loc = subtask.execution.primitive_actions[-1].split(" ")[-1]
        self.current_time += subtask.duration.interval
        # 근데 critical 이 두 개가 중첩이 되면..? 일단 나중에 생각..
        if self.is_critical and self.graph.in_edges(subtask.name):
            self.is_critical = False
            self.before_subtask = None
            self.after_subtask = None
        if self.graph.out_edges(
            subtask.name, data=True
        ):  # 나가는 화살표가 있다는건 dependency 하다는 것.
            self.dependence_start_time = (
                self.current_time
                + list(self.graph.out_edges(subtask.name, data=True))[0][2]["info"][
                    "Interval"
                ]
            )
            self.is_critical = list(self.graph.out_edges(subtask.name, data=True))[0][
                2
            ]["info"][
                "IsCritical"
            ]  # Interval, Type, IsCritical
            self.before_subtask = list(self.graph.out_edges(subtask.name, data=True))[
                0
            ][0]
            self.after_subtask = list(self.graph.out_edges(subtask.name, data=True))[0][
                1
            ]

            for sub in self.subtasks:
                if sub.name == self.after_subtask:
                    self.after_loc = sub.execution.primitive_actions[0].split(" ")[-1]
        print(f"{subtask.name} 의 {self.is_critical=}")


class EDFNodeInfo:
    """
    EDF를 위해 필요한 정보 저장(subtask 마다 한 개씩 생김)
    """

    def __init__(self, edfinfo, subtask, graph, action_handler):  # Add action_handler
        self.edfinfo = edfinfo  # current_time, is_urgent, before_urgent, after_urgent, finished_subtasks, remaining_subtasks, final_loc
        self.subtask = subtask
        self.graph = graph  # constraints 를 저장한 graph
        self.name = self.subtask.name
        self.execution_time = subtask.duration.interval
        self.final_loc = subtask.execution.primitive_actions[-1].split(" ")[-1]
        self.deadline = self.execution_time
        self.is_critical = False
        self.is_dependent = True if self.name == self.edfinfo.after_subtask else False
        self.finished_time = 0
        self.start_time = 0
        self.wait_time = 0
        self.action_handler = action_handler  # Store action_handler

    def update(self):
        """
        subtask의 deadline을 update
        """
        # 실행시간 업데이트
        self.start_time = self.edfinfo.current_time
        self.execution_time = self.calculate_execution_time()
        self.subtask.duration.interval = self.execution_time
        self.is_critical = (
            self.edfinfo.is_critical
        )  # 전역적으로 현재 무조건 돌아가야할 task가 있는지
        self.is_dependent = True if self.name == self.edfinfo.after_subtask else False
        print(self.is_critical)
        self.arrival_time = self.edfinfo.dependence_start_time
        print(f"{self.name} 으악 도착시간 :: !!!!! {self.arrival_time}")
        if self.is_critical:  # 긴급한 task가 있는 경우
            # 현재 위치로부터 after_subtask까지 가는데 걸리는 시간
            if self.is_dependent:
                # 얘의 navi time은 현재 위치에서 after_loc까지 가는데 걸리는 시간
                # navigate_time = data[self.edfinfo.final_loc][self.edfinfo.after_loc]
                start_pos = self.get_position(self.edfinfo.final_loc)
                end_pos = self.get_position(self.edfinfo.after_loc)
                navigate_path = self.action_handler._find_shortest_path(
                    start_pos, end_pos
                )
                navigate_time = len(navigate_path) * NAV_STEP_DURATION

                print(f"{self.edfinfo.dependence_start_time=}")
                self.deadline = self.edfinfo.dependence_start_time - navigate_time
                print("얜가?")
            else:
                # 얘의 navi time은 수행할 subtask의 마지막 위치에서 final_loc까지 가는데 걸리는 시간
                # navigate_time = data[self.final_loc][self.edfinfo.after_loc]

                start_pos = self.get_position(self.final_loc)
                end_pos = self.get_position(self.edfinfo.after_loc)
                navigate_path = self.action_handler._find_shortest_path(
                    start_pos, end_pos
                )
                navigate_time = len(navigate_path) * NAV_STEP_DURATION

                self.deadline = (
                    self.edfinfo.current_time + navigate_time + self.execution_time
                )
        else:  # 긴급한 task가 없는 경우
            self.deadline = self.edfinfo.current_time + self.execution_time
            if self.is_dependent and self.edfinfo.current_time < self.deadline:
                # 이렇게 한 이유는 현재 시간이 timeslot 보다 이르면 도착해서 기다려야함
                self.deadline = self.edfinfo.dependence_start_time

    def calculate_execution_time(self):
        """
        subtask의 실행 시간 계산
        """
        self.execution_time = 0
        for command in self.subtask.execution.primitive_actions:
            action = command.split(" ")[0]
            obj = command.split(" ")[-1]
            if action == "NAVIGATE_TO":
                # self.execution_time += data[self.final_loc][obj] # Remove data lookup

                # NEW: Use ActionHandler to find the shortest path and calculate time
                start_pos = self.get_position(self.edfinfo.final_loc)  # 시작 위치
                end_pos = self.get_position(obj)  # end_pos obj
                navigate_path = self.action_handler._find_shortest_path(
                    start_pos, end_pos
                )
                self.execution_time += len(navigate_path) * NAV_STEP_DURATION
                self.final_loc = obj
            else:
                self.execution_time += 1
        return self.execution_time

    def get_position(self, obj_id: str) -> Tuple[float, float, float]:
        """
        객체 ID로부터 위치 정보를 가져오는 함수
        """
        # 이 부분은 실제 환경에 따라 달라질 수 있습니다.
        # 여기서는 간단하게 객체 ID를 키로 사용하여 위치 정보를 저장하고 있다고 가정합니다.
        # 실제로는 scene 상태나 다른 방식으로 위치 정보를 얻어야 할 수 있습니다.
        # return self.scene_positions.get(obj_id)
        return (0, 0, 0)  # 임시
        # 만약 scene_positions에 해당 객체 ID가 없다면 None을 반환하거나,
        # 혹은 적절한 기본 위치 정보를 반환하도록 구현해야 합니다.

    def finished(self):
        # 일단 timeslot 정보 저장
        # 얘는 EDF info update 하고 나서 시행
        if self.is_dependent:
            self.start_time = max(self.arrival_time, self.start_time)
            self.finished_time = max(
                self.arrival_time + self.execution_time, self.edfinfo.current_time
            )
            self.wait_time = self.finished_time - self.edfinfo.current_time

            # if self.edfinfo.current_time < self.finished_time:
            #     self.wait_time = self.finished_time - self.edfinfo.current_time
            #     print(f"Task {self.name} 기다린 시간 : {self.wait_time}")
        else:
            self.finished_time = self.edfinfo.current_time
        print(f"Task {self.name} 기다린 시간 : {self.wait_time}")
        print(f"Task {self.name} 실행시간 : {self.execution_time}")
        print(f"Task {self.name} 시작시각 : {self.start_time}")
        print(f"Task {self.name} 끝난 시각 : {self.finished_time}")

    def is_executable(self):
        """
        subtask가 dependency 때문에 실행 가능한지 여부 반환
        """
        if self.graph.in_edges(self.name):  # dependency가 있는 경우
            if list(self.graph.in_edges(self.name))[0][0] in [
                finish_subtask.name for finish_subtask in self.edfinfo.finished_subtasks
            ]:
                # 앞 subtask 가 finished_subtasks에 있어야 실행 가능
                return True
            else:
                return False
        # dependency가 없는 경으면 그냥 실행 가능
        return True

    def __lt__(self, other):
        if self.deadline == other.deadline:
            return self.is_dependent
        return self.deadline < other.deadline


def update_nodes(remaining_nodes, edfinfo):
    print("Update subtasks")
    print(f"current time: {edfinfo.current_time}\n")
    for node in remaining_nodes:
        node.update()
        print(f"Task {node.name} deadline: {node.deadline}")
    print("-----------------")
    return remaining_nodes


def create_queue(remaining_nodes):
    # 우선순위 큐 (heap) 사용하여 마감 기한이 빠른 순으로 태스크 실행
    queue = []
    for node in remaining_nodes:
        # 시간 제약이 있는 경우 앞에 해야하는 subtask가 끝나야 실행 가능
        if node.is_executable():
            print(f"Task {node.name} is executable")
            heapq.heappush(queue, node)
    return queue


def list_task_files():
    data_dir = "tasks"
    return [f for f in os.listdir(data_dir) if f.endswith(".json")]


def get_user_task_choice(task_files):
    print("Available task files:")
    for i, file in enumerate(task_files):
        print(f"{i + 1}. {file}")
    choice = int(input("Select a task file by number: ")) - 1
    return task_files[choice]


def load_task_data_from_file(task_file_name):
    with open(f"tasks/{task_file_name}") as f:
        return json.load(f)


def main():

    task_files = list_task_files()

    # task_file_name = get_user_task_choice(task_files)
    # Manually set the task file for testing purposes
    task_file_name = get_user_task_choice(task_files)
    # Load the chosen task data
    task_data = load_task_data_from_file(task_file_name)
    controller = init_ai2thor()
    nav_graph = build_navigation_graph(controller)
    subtasks, constraints = build_tasks_and_constraints(task_data, True)
    action_handler = ActionHandler(nav_graph)
    # 그래프 저장
    plt.figure(figsize=(10, 10))
    nx.draw(constraints, with_labels=True, font_weight="bold")
    plt.savefig("result/constraints.png")

    edfinfo = EDFInfo(subtasks, constraints, nav_graph)
    finished_nodes = []
    remaining_nodes = []

    for subtask in subtasks:
        remaining_nodes.append(EDFNodeInfo(edfinfo, subtask, constraints, action_handler))

    print("-----------------")
    while remaining_nodes:
        # 모든 subtasks를 업데이트
        remaining_nodes = update_nodes(remaining_nodes, edfinfo)

        # 현재 가능한 태스크들로 큐 생성
        queue = create_queue(remaining_nodes)

        # 큐에서 우선순위가 가장 높은 태스크(마감기한이 빠른 태스크)를 꺼냄
        if queue:
            current_node = heapq.heappop(queue)
            # pop 을 했는데 in edge 가 있으면 남은 시간 채워줘야함. 아니면 그럴 필요 없음
            edfinfo.update(current_node.subtask)
            current_node.finished()
            finished_nodes.append(current_node)
            remaining_nodes.remove(current_node)

            # 종료 시간 출력
            print(
                f"\nTask {current_node.name} 의 종료 시각 {current_node.finished_time}"
            )
            print("-----------------")

    return task_file_name, edfinfo.finished_subtasks, finished_nodes


if __name__ == "__main__":
    task_file_name, finished_subtasks, finished_nodes = main()
    plot_gantt_chart(task_file_name, finished_nodes, "result", True)
    # plot_gantt_chart(finished_nodes, True)
    for i, subtask in enumerate(finished_subtasks):
        print(subtask.name, finished_nodes[i].finished_time)

    print("Done")
