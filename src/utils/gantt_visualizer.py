import json
from collections import defaultdict

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def find(parent, x):
    if parent[x] != x:
        parent[x] = find(parent, parent[x])
    return parent[x]


def union(parent, rank, x, y):
    root_x = find(parent, x)
    root_y = find(parent, y)
    if root_x != root_y:
        if rank[root_x] > rank[root_y]:
            parent[root_y] = root_x
        elif rank[root_x] < rank[root_y]:
            parent[root_x] = root_y
        else:
            parent[root_y] = root_x
            rank[root_x] += 1


def merge_groups(groups):
    parent = {}
    rank = {}

    # 초기화
    for group in groups:
        for item in group:
            if item not in parent:
                parent[item] = item
                rank[item] = 0

    # Union 연산 수행
    for group in groups:
        for i in range(1, len(group)):
            union(parent, rank, group[0], group[i])

    # 그룹화
    merged = defaultdict(set)
    for item in parent:
        root = find(parent, item)
        merged[root].add(item)

    return [sorted(list(group)) for group in merged.values()]


def load_json_data(file_path):
    with open(file_path, "r") as file:
        return json.load(file)


def assign_chain_numbers(subtask_names, dependencies, durations):
    """
    - subtask_names: 실행 순서대로 정렬된 서브태스크 리스트
    - dependencies: merge_groups()으로 병합된 서브태스크 그룹
    - durations: 각 서브태스크의 실행 시간 리스트
    - return: 체인 번호 리스트, dependency 없는 그룹의 줄 번호
    """
    chain_mapping = {}  # {서브태스크: 체인 번호}
    independent_tasks = set(subtask_names)  # 독립적인 태스크 찾기 위한 집합
    chain_order = {}  # {체인 그룹: 시작 시간}

    # Dependency 그룹 먼저 체인 번호 할당
    for chain_id, group in enumerate(dependencies, start=1):
        for subtask in group:
            chain_mapping[subtask] = chain_id
            if subtask in independent_tasks:
                independent_tasks.remove(subtask)  # 의존성이 있는 태스크 제거

    # 독립적인 태스크(Dependency가 없는 태스크) 그룹화
    if independent_tasks:
        independent_chain_id = len(dependencies) + 1  # 기존 체인 이후로 번호 부여
        for subtask in independent_tasks:
            chain_mapping[subtask] = independent_chain_id
        independent_chain_line = (
            independent_chain_id  # 독립 태스크가 위치한 줄 번호 저장
        )
    else:
        independent_chain_line = None  # 독립적인 태스크가 없으면 None

    # 각 체인의 시작 시간 찾기 (가장 먼저 시작하는 줄이 맨 위)
    chain_start_times = {
        chain_id: float("inf") for chain_id in set(chain_mapping.values())
    }
    for subtask, chain_id in chain_mapping.items():
        subtask_index = subtask_names.index(subtask)
        start_time = sum(durations[:subtask_index])  # 실행 순서에 따른 시작 시간
        if start_time < chain_start_times[chain_id]:
            chain_start_times[chain_id] = start_time

    # 시작 시간이 가장 빠른 체인부터 정렬 (제일 먼저 실행되는 줄이 맨 위)
    sorted_chains = sorted(chain_start_times, key=lambda x: chain_start_times[x])
    max_chain_id = len(sorted_chains)
    new_chain_mapping = {
        chain_id: max_chain_id - new_id for new_id, chain_id in enumerate(sorted_chains)
    }

    # 기존 chain_mapping을 정렬된 chain 번호로 업데이트
    final_chains = [new_chain_mapping[chain_mapping[name]] for name in subtask_names]

    return final_chains, new_chain_mapping.get(independent_chain_line, None)


def plot_subtask_timeline(
    ax, subtaskNames, durations, chains, startTimes, xLimit, independent_line
):
    """
    - subtaskNames : list of str    (작업 이름)
    - durations    : list of float  (각 작업 소요 시간)
    - chains       : list of int    (체인 번호)
    - startTimes   : list of float  (시작 시간, 사전에 계산)
    - xLimit       : float          (x축 최대값)
    - independent_line : int         (독립적인 체인의 줄 번호)
    """
    # 막대 높이
    bar_height = 0.8

    # 체인 번호 최대값
    num_chains = max(chains)

    # 일반 체인용 파스텔 색상 팔레트
    pastel_colors = [
        (0.72, 0.85, 0.98),  # 연한 하늘색
        (0.98, 0.75, 0.75),  # 연한 핑크
        (0.80, 0.92, 0.77),  # 연한 연두
        (0.99, 0.88, 0.70),  # 살구색
        (0.91, 0.79, 0.98),  # 연보라
        (0.75, 0.85, 0.98),  # 연한 퍼플블루
        (0.99, 0.92, 0.75),  # 연한 노랑
        (0.79, 0.88, 0.99),  # 연한 블루
        (0.94, 0.80, 0.85),  # 연한 로즈핑크
        (0.85, 0.85, 0.85),  # 연한 그레이
    ]

    # 독립적인 체인 색상 (각 태스크마다 다르게 설정)
    independent_colors = [
        (0.55, 0.80, 0.90),  # 연한 하늘색
        (0.90, 0.60, 0.45),  # 부드러운 코랄
        (0.65, 0.85, 0.50),  # 부드러운 연두
        (0.80, 0.70, 0.40),  # 부드러운 금색
        (0.70, 0.60, 0.80),  # 부드러운 라벤더
        (0.80, 0.60, 0.85),  # 연한 라일락
        (0.75, 0.85, 0.60),  # 부드러운 올리브
        (0.60, 0.80, 0.80),  # 부드러운 민트
        (0.65, 0.70, 0.85),  # 부드러운 블루그레이
        (0.80, 0.75, 0.65),  # 부드러운 베이지
    ]

    independent_subtasks = [
        subtaskNames[i]
        for i in range(len(subtaskNames))
        if chains[i] == independent_line
    ]
    independent_task_colors = {
        task: independent_colors[i % len(independent_colors)]
        for i, task in enumerate(independent_subtasks)
    }

    # ---- 1) 메인 막대 그리기 ----
    for i in range(len(subtaskNames)):
        xPos = startTimes[i]
        yPos = chains[i]
        w = durations[i]

        # 독립적인 줄(independent_line)에 있는 경우 색상을 다르게 설정
        if yPos == independent_line:
            face_color = independent_task_colors[
                subtaskNames[i]
            ]  # 독립적인 태스크는 각각 다른 색
        else:
            # chain 번호가 6 초과하면 6개 색상 반복 사용
            color_index = (yPos - 1) % len(pastel_colors)
            face_color = pastel_colors[color_index]

        rect = Rectangle(
            (xPos, yPos - bar_height / 2),  # 왼쪽-하단 좌표
            w,  # 막대 너비
            bar_height,  # 막대 높이
            facecolor=face_color,
            edgecolor=(0.4, 0.4, 0.4),
            linewidth=0.8,
            alpha=0.9,
        )
        ax.add_patch(rect)

        # 막대 위에 텍스트
        ax.text(
            xPos + w / 2,
            yPos,
            subtaskNames[i],
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=(0.2, 0.2, 0.2),
        )

    # ---- 2) 같은 체인에서 연속(경계) / 틈(gap) 표시 ----
    for i in range(len(subtaskNames) - 1):
        # 앞뒤 subtask가 같은 chain에 속할 때만 검사(independet 끼리는 색이 다르니 검사 안함)
        if chains[i] == chains[i + 1] and chains[i] != independent_line:
            end_of_i = startTimes[i] + durations[i]
            start_of_i1 = startTimes[i + 1]
            yPos = chains[i]

            # (1) 연속 경계 (시간 차이 0)
            if abs(end_of_i - start_of_i1) < 1e-12:
                ax.plot(
                    [end_of_i, end_of_i],
                    [yPos - bar_height / 2, yPos + bar_height / 2],
                    color="k",
                    linewidth=1.2,
                )
            # (2) gap (end_of_i < start_of_i1)
            elif end_of_i < start_of_i1:
                gap_start = end_of_i
                gap_width = start_of_i1 - end_of_i

                # gap을 표시하기 위해 더 밝은 색상(혹은 투명도) 사용
                base_color = (
                    independent_task_colors[subtaskNames[i]]
                    if yPos == independent_line
                    else pastel_colors[(yPos - 1) % len(pastel_colors)]
                )
                lighter_color = tuple(bc + 0.5 * (1 - bc) for bc in base_color)

                gap_rect = Rectangle(
                    (gap_start, yPos - bar_height / 2),
                    gap_width,
                    bar_height,
                    facecolor=lighter_color,
                    edgecolor="none",
                    alpha=0.3,
                )
                ax.add_patch(gap_rect)

    # ---- 3) 축 설정 / 꾸미기 ----
    ax.set_xlim([0, xLimit])
    ax.set_ylim([0.4, num_chains + 0.6])

    # Y축 눈금 제거
    ax.set_yticks([])

    # Label 등
    ax.set_xlabel("Time")

    # Grid, 배경, 테두리 등
    ax.grid(axis="x", linestyle="-", color="0.9")
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(1.1)


def compute_start_times(durations):
    """
    durations: list of float
    return: (startTimes, totalTime)
    """
    startTimes = []
    currentTime = 0
    for d in durations:
        startTimes.append(currentTime)
        currentTime += d
    return startTimes, currentTime  # 마지막 시점 = totalTime


def main():
    # 3개(ours, cpm, edf)json 파일 불러오기

    ours_data = load_json_data("assets/gantt_data/ours.json")
    cpm_data = load_json_data("assets/gantt_data/cpm.json")
    edf_data = load_json_data("assets/gantt_data/edf.json")

    ours_data.keys()
    for task in ours_data.keys():
        ## 후처리(notion 에 있음)
        ours = ours_data[task]
        cpm = cpm_data[task]
        edf = edf_data[task]

        # subtask_name 순서 뽑기
        ours_subtask_names = ours["complete_schedule"]
        cpm_subtask_names = cpm["complete_schedule"]
        edf_subtask_names = edf["complete_schedule"]

        # subtask가 각각 걸린 시간 뽑기(schedule 순서대로)
        ours_durations = []
        cpm_durations = []
        edf_durations = []
        for name in ours_subtask_names:
            ours_durations.append(ours[name]["scheduler"])
        for name in cpm_subtask_names:
            cpm_durations.append(cpm[name]["scheduler"])
        for name in edf_subtask_names:
            edf_durations.append(edf[name]["scheduler"])

        # 겹치는 dependency 있으면 한 그룹으로 묶기
        ours_dependency = merge_groups(ours["constraints"])
        cpm_dependency = merge_groups(cpm["constraints"])
        edf_dependency = merge_groups(edf["constraints"])

        # 체인 번호 할당 (ours, cpm, edf 각각 수행)
        chains_ours, independent_line_ours = assign_chain_numbers(
            ours_subtask_names, ours_dependency, ours_durations
        )
        chains_cpm, independent_line_cpm = assign_chain_numbers(
            cpm_subtask_names, cpm_dependency, cpm_durations
        )
        chains_edf, independent_line_edf = assign_chain_numbers(
            edf_subtask_names, edf_dependency, edf_durations
        )

        # 1) 시작 시간 / 총 시간 계산
        ours_startTimes, ours_totalTime = compute_start_times(ours_durations)
        cpm_startTimes, cpm_totalTime = compute_start_times(cpm_durations)
        edf_startTimes, edf_totalTime = compute_start_times(edf_durations)

        # 가장 짧은 total time
        minTimeAll = min(ours_totalTime, cpm_totalTime, edf_totalTime)
        # 가장 긴 total time (x축 공통 범위)
        maxTimeAll = max(ours_totalTime, cpm_totalTime, edf_totalTime)

        # 2) figure/subplots 생성
        fig, axes = plt.subplots(
            nrows=3, ncols=1, figsize=(10, 8), sharex=False, constrained_layout=True
        )
        fig.suptitle("Three DataSets with Shortest End-Time Mark", fontsize=14)

        # (3-1) 첫 번째 데이터셋
        plot_subtask_timeline(
            axes[0],
            ours_subtask_names,
            ours_durations,
            chains_ours,
            ours_startTimes,
            maxTimeAll,
            independent_line_ours,
        )
        axes[0].set_title("OURS")
        # 빨간 세로선 (가장 짧은 total time)
        axes[0].axvline(minTimeAll, color="r", linewidth=2)
        # label을 가로로 달고 싶다면 다음처럼 text 추가
        axes[0].text(
            minTimeAll,
            axes[0].get_ylim()[1],
            "Shortest End",
            color="r",
            ha="left",
            va="top",
        )

        # (3-2) 두 번째 데이터셋
        plot_subtask_timeline(
            axes[1],
            cpm_subtask_names,
            cpm_durations,
            chains_cpm,
            cpm_startTimes,
            maxTimeAll,
            independent_line_cpm,
        )
        axes[1].set_title("CPM")
        axes[1].axvline(minTimeAll, color="r", linewidth=2)
        axes[1].text(
            minTimeAll,
            axes[1].get_ylim()[1],
            "Shortest End",
            color="r",
            ha="left",
            va="top",
        )

        # (3-3) 세 번째 데이터셋
        plot_subtask_timeline(
            axes[2],
            edf_subtask_names,
            edf_durations,
            chains_edf,
            edf_startTimes,
            maxTimeAll,
            independent_line_edf,
        )
        axes[2].set_title("EDF")
        axes[2].axvline(minTimeAll, color="r", linewidth=2)
        axes[2].text(
            minTimeAll,
            axes[2].get_ylim()[1],
            "Shortest End",
            color="r",
            ha="left",
            va="top",
        )

        plt.show()
        # Save the plot to a file
        fig.savefig(f"assets/gantt_data/{task}.png", dpi=300)


if __name__ == "__main__":
    main()
