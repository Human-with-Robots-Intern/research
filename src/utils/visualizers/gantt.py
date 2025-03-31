# utils/viz/gantt.py

from typing import List, Optional

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from core.dataclass import CompletedEntry
from core.task import Subtask


def compute_start_times(durations: List[float]):
    """
    각 서브태스크 duration에 따라 시작 시간을 누적 계산.
    Returns: (startTimes, totalTime)
    """
    start_times = []
    current_time = 0.0
    for d in durations:
        start_times.append(current_time)
        current_time += d
    return start_times, current_time


def assign_chain_numbers(
    subtask_names: List[str], dependencies: List[List[str]], durations: List[float]
):
    """
    subtask_names: 실행 순서대로 정렬된 서브태스크 리스트
    dependencies: merge_groups()로 병합된 서브태스크 그룹
    durations: 각 서브태스크의 실행 시간 리스트

    return: (chains, independent_line)
      - chains: 각 subtask별로 할당된 체인 번호 리스트
      - independent_line: 의존성 없는 그룹(= 독립태스크)용 체인 번호
    """
    chain_mapping = {}
    independent_tasks = set(subtask_names)

    # Dependency 그룹 먼저 체인 번호 할당
    for chain_id, group in enumerate(dependencies, start=1):
        for subtask in group:
            chain_mapping[subtask] = chain_id
            if subtask in independent_tasks:
                independent_tasks.remove(subtask)

    # 독립적인 태스크 처리
    if independent_tasks:
        independent_chain_id = len(dependencies) + 1
        for t in independent_tasks:
            chain_mapping[t] = independent_chain_id
        independent_chain_line = independent_chain_id
    else:
        independent_chain_line = None

    # 각 체인의 시작 시간
    chain_start_times = {cid: float("inf") for cid in set(chain_mapping.values())}
    for subtask, cid in chain_mapping.items():
        idx = subtask_names.index(subtask)
        st_time = sum(durations[:idx])  # 단순 누적
        if st_time < chain_start_times[cid]:
            chain_start_times[cid] = st_time

    # 시작 시간이 빠른 체인을 위쪽으로
    sorted_chains = sorted(chain_start_times, key=lambda x: chain_start_times[x])
    max_chain_id = len(sorted_chains)
    new_chain_mapping = {
        chain_id: (max_chain_id - i) for i, chain_id in enumerate(sorted_chains)
    }

    # 최종 체인 리스트
    final_chains = [new_chain_mapping[chain_mapping[n]] for n in subtask_names]

    # independent_chain_line 업데이트
    final_independent_line = (
        new_chain_mapping[independent_chain_line]
        if independent_chain_line in new_chain_mapping
        else None
    )

    return final_chains, final_independent_line


def plot_subtask_timeline(
    ax,
    subtask_names: List[str],
    durations: List[float],
    chains: List[int],
    start_times: List[float],
    x_limit: float,
    independent_line: Optional[int],
):
    """
    여러 서브태스크(혹은 스케줄) 비교용 Gantt 차트.
    ax: matplotlib Axes
    x_limit: x축 최대값
    independent_line: 의존성 없는 체인을 표시할 때 사용
    """
    bar_height = 0.8
    num_chains = max(chains) if chains else 1

    # 파스텔 컬러
    pastel_colors = [
        (0.72, 0.85, 0.98),
        (0.98, 0.75, 0.75),
        (0.80, 0.92, 0.77),
        (0.99, 0.88, 0.70),
        (0.91, 0.79, 0.98),
        (0.75, 0.85, 0.98),
        (0.99, 0.92, 0.75),
        (0.79, 0.88, 0.99),
        (0.94, 0.80, 0.85),
        (0.85, 0.85, 0.85),
    ]

    # 독립태스크용 팔레트
    independent_colors = [
        (0.55, 0.80, 0.90),
        (0.90, 0.60, 0.45),
        (0.65, 0.85, 0.50),
        (0.80, 0.70, 0.40),
        (0.70, 0.60, 0.80),
        (0.80, 0.60, 0.85),
        (0.75, 0.85, 0.60),
        (0.60, 0.80, 0.80),
        (0.65, 0.70, 0.85),
        (0.80, 0.75, 0.65),
    ]

    # 독립 서브태스크 목록
    if independent_line is not None:
        independent_subtasks = [
            subtask_names[i]
            for i in range(len(subtask_names))
            if chains[i] == independent_line
        ]
        # 독립 subtasks 마다 고유 색상
        independent_task_colors = {
            task: independent_colors[i % len(independent_colors)]
            for i, task in enumerate(independent_subtasks)
        }
    else:
        independent_subtasks = []
        independent_task_colors = {}

    # Gantt 막대
    for i, name in enumerate(subtask_names):
        x_pos = start_times[i]
        y_pos = chains[i]
        w = durations[i]

        if (independent_line is not None) and (y_pos == independent_line):
            face_color = independent_task_colors.get(name, (0.8, 0.8, 0.8))
        else:
            color_idx = (y_pos - 1) % len(pastel_colors) if y_pos > 0 else 0
            face_color = pastel_colors[color_idx]

        rect = Rectangle(
            (x_pos, y_pos - bar_height / 2),
            w,
            bar_height,
            facecolor=face_color,
            edgecolor=(0.4, 0.4, 0.4),
            linewidth=0.8,
            alpha=0.9,
        )
        ax.add_patch(rect)
        # text
        ax.text(
            x_pos + w / 2,
            y_pos,
            name,
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=(0.2, 0.2, 0.2),
        )

    # 같은 chain에서 연속 / gap 표시
    for i in range(len(subtask_names) - 1):
        if chains[i] == chains[i + 1] and chains[i] != independent_line:
            end_of_i = start_times[i] + durations[i]
            start_of_i1 = start_times[i + 1]
            y_pos = chains[i]

            # 연속(시간 차이 0)
            if abs(end_of_i - start_of_i1) < 1e-12:
                ax.plot(
                    [end_of_i, end_of_i],
                    [y_pos - bar_height / 2, y_pos + bar_height / 2],
                    color="k",
                    linewidth=1.2,
                )
            # gap
            elif end_of_i < start_of_i1:
                gap_start = end_of_i
                gap_width = start_of_i1 - end_of_i

                # base color
                if y_pos == independent_line:
                    base_color = independent_task_colors[subtask_names[i]]
                else:
                    base_color = pastel_colors[(y_pos - 1) % len(pastel_colors)]
                # 더 밝게
                lighter_color = tuple(bc + 0.5 * (1 - bc) for bc in base_color)

                gap_rect = Rectangle(
                    (gap_start, y_pos - bar_height / 2),
                    gap_width,
                    bar_height,
                    facecolor=lighter_color,
                    edgecolor="none",
                    alpha=0.3,
                )
                ax.add_patch(gap_rect)

    ax.set_xlim([0, x_limit])
    ax.set_ylim([0.4, num_chains + 0.6])
    ax.set_yticks([])
    ax.set_xlabel("Time")
    ax.grid(axis="x", linestyle="-", color="0.9")
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(1.1)


def plot_completed_subtasks_gantt(
    completed_subtasks: List[CompletedEntry], save_path: Optional[str] = None
):
    """
    완료된 Subtask 리스트(예: CompletedEntry 형태) 기반으로 Gantt를 그린다.
    entry 형식: {"subtask": object, "start_time": float, "end_time": float}
    """
    if not completed_subtasks:
        print("No completed subtasks.")
        return

    # 시작 시간 기준 정렬
    sorted_entries = sorted(completed_subtasks, key=lambda e: e.start_time)
    gantt_data = []
    current_time = 0.0

    for entry in sorted_entries:
        st_time = entry.start_time
        ed_time = entry.end_time
        sb_name = getattr(entry.subtask, "name")

        # 대기 구간
        if st_time > current_time:
            gantt_data.append(
                {"name": f"Wait until {sb_name}", "start": current_time, "end": st_time}
            )
        gantt_data.append({"name": sb_name, "start": st_time, "end": ed_time})
        current_time = ed_time

    # Matplotlib
    _, ax = plt.subplots(figsize=(10, 6))
    task_names = [g["name"] for g in gantt_data]
    start_times = [g["start"] for g in gantt_data]
    durations = [g["end"] - g["start"] for g in gantt_data]

    y_pos = np.arange(len(task_names))
    bars = ax.barh(y_pos, durations, left=start_times, color="skyblue")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(task_names)
    ax.invert_yaxis()  # 처음 수행된 작업이 위
    ax.set_xlabel("Time")
    ax.set_title("Gantt Chart (Completed Subtasks)")

    for i, _ in enumerate(bars):
        st = start_times[i]
        et = st + durations[i]
        ax.text(
            st + durations[i] / 2,
            y_pos[i],
            f"{st:.1f} - {et:.1f}",
            ha="center",
            va="center",
            color="black",
            fontsize=8,
            fontweight="bold",
        )

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300)
        print(f"Saved Gantt to: {save_path}")
        plt.close()
    else:
        plt.show()
