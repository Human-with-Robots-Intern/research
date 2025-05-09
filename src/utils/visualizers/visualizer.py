# utils/visualizers/visualizer.py

from pathlib import Path

from .dag import visualize_graph
from .gantt import plot_completed_subtasks_gantt

# 예: viz_utils.py에 정의된 VIS_PATH 등을 import할 수도 있음
# from .viz_utils import VIS_PATH


def visualize(approach, output_path, constraints, plan=None):
    """
    DAG + Gantt 차트를 함께 시각화 및 저장하는 함수 (예시).
    """

    save_folder_path = Path(output_path) / "metadata"
    save_folder_path.mkdir(exist_ok=True)

    # DAG 시각화
    dag_save_path = save_folder_path / f"{approach}_task_graph.png"
    visualize_graph(constraints, save_path=dag_save_path)

    # Gantt 시각화 (plan이 있으면)
    if plan:
        gantt_save_path = save_folder_path / f"{approach}_gantt_chart.png"
        plot_completed_subtasks_gantt(plan, save_path=gantt_save_path)
