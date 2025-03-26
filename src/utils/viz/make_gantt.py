import matplotlib.pyplot as plt
import numpy as np

def gantt_chart(completed_subtasks: list):
    """
    완료된 subtasks(예: CompletedEntry 객체)를 기반으로 Gantt 차트를 생성한다.
    각 완료 엔트리는 다음 속성을 가진다고 가정:
      - subtask: 실행된 Subtask (subtask.name 로 이름 접근)
      - start_time: subtask 실행 시작 시각
      - end_time: subtask 실행 종료 시각

    작업 사이에 대기(wait) 시간이 있다면, 해당 구간을 "Wait" 바로 표시한다.
    """
    # 완료 엔트리를 실행 시작 시간 기준으로 정렬
    sorted_entries = sorted(completed_subtasks, key=lambda entry: entry.start_time)

    gantt_data = []
    current_time = 0.0
    for entry in sorted_entries:
        # 만약 이전 작업 종료와 현재 작업 시작 사이에 간격이 있다면 wait bar 추가
        if entry.start_time > current_time:
            gantt_data.append(
                {
                    "name": f"Wait until {entry.subtask.name}",
                    "start": current_time,
                    "end": entry.start_time,
                }
            )
        # 현재 subtask bar 추가
        gantt_data.append(
            {
                "name": entry.subtask.name,
                "start": entry.start_time,
                "end": entry.end_time,
            }
        )
        current_time = entry.end_time

    # 각 bar의 이름, 시작 시각, 지속시간 계산
    task_names = [item["name"] for item in gantt_data]
    start_times = [item["start"] for item in gantt_data]
    durations = [item["end"] - item["start"] for item in gantt_data]

    # y축 위치 설정
    y_pos = np.arange(len(task_names))

    # Gantt 차트 생성
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(y_pos, durations, left=start_times, color="skyblue")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(task_names)
    ax.invert_yaxis()  # 위쪽에 가장 먼저 실행된 작업을 표시
    ax.set_xlabel("Time")
    ax.set_title("Gantt Chart for Completed Subtasks")

    # 각 bar 중앙에 시작 및 종료 시각 텍스트 표시
    for i, bar in enumerate(bars):
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
    plt.show()