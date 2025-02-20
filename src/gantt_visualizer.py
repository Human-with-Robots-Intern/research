## 

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

def plot_subtask_timeline(ax, subtaskNames, durations, chains, startTimes, xLimit):
    """
    - subtaskNames : list of str    (작업 이름)
    - durations    : list of float  (각 작업 소요 시간)
    - chains       : list of int    (체인 번호)
    - startTimes   : list of float  (시작 시간, 사전에 계산)
    - xLimit       : float          (x축 최대값)
    """
    # 막대 높이
    bar_height = 0.8
    
    # 체인 번호 최대값
    num_chains = max(chains)

    # 파스텔 색상 팔레트 (6개)
    pastel_colors = [
        (0.8,  0.87, 0.96),  # 연한 하늘색
        (0.93, 0.80, 0.80),  # 연한 분홍
        (0.80, 0.93, 0.80),  # 연한 연두
        (0.94, 0.87, 0.80),  # 연한 오렌지
        (0.85, 0.80, 0.94),  # 연보라
        (0.96, 0.89, 0.76)   # 기타
    ]
    
    # ---- 1) 메인 막대 그리기 ----
    for i in range(len(subtaskNames)):
        xPos = startTimes[i]
        yPos = chains[i]
        w    = durations[i]

        # chain 번호가 6 초과하면 6개 색상 반복 사용
        color_index = (yPos - 1) % len(pastel_colors)
        face_color = pastel_colors[color_index]

        rect = Rectangle(
            (xPos, yPos - bar_height/2),  # 왼쪽-하단 좌표
            w,                            # 막대 너비
            bar_height,                   # 막대 높이
            facecolor=face_color,
            edgecolor=(0.4, 0.4, 0.4),
            linewidth=0.8,
            alpha=0.9
        )
        ax.add_patch(rect)

        # 막대 위에 텍스트
        ax.text(
            xPos + w/2,
            yPos,
            subtaskNames[i],
            ha='center',
            va='center',
            fontsize=10,
            fontweight='bold',
            color=(0.2, 0.2, 0.2)
        )

    # ---- 2) 같은 체인에서 연속(경계) / 틈(gap) 표시 ----
    for i in range(len(subtaskNames) - 1):
        # 앞뒤 subtask가 같은 chain에 속할 때만 검사
        if chains[i] == chains[i+1]:
            end_of_i    = startTimes[i]   + durations[i]
            start_of_i1 = startTimes[i+1]
            yPos        = chains[i]

            # (1) 연속 경계 (시간 차이 0)
            if abs(end_of_i - start_of_i1) < 1e-12:
                ax.plot([end_of_i, end_of_i],
                        [yPos - bar_height/2, yPos + bar_height/2],
                        color='k', linewidth=1.2)
            # (2) gap (end_of_i < start_of_i1)
            elif end_of_i < start_of_i1:
                gap_start = end_of_i
                gap_width = start_of_i1 - end_of_i
                
                # gap을 표시하기 위해 더 밝은 색상(혹은 투명도) 사용
                base_color = pastel_colors[(yPos - 1) % len(pastel_colors)]
                lighter_color = tuple(bc + 0.5*(1 - bc) for bc in base_color)

                gap_rect = Rectangle(
                    (gap_start, yPos - bar_height/2),
                    gap_width,
                    bar_height,
                    facecolor=lighter_color,
                    edgecolor='none',
                    alpha=0.3
                )
                ax.add_patch(gap_rect)

    # ---- 3) 축 설정 / 꾸미기 ----
    ax.set_xlim([0, xLimit])
    ax.set_ylim([0.4, num_chains + 0.6])

    # Label 등
    ax.set_xlabel('Time')
    ax.set_ylabel('체인 번호')
    
    # Grid, 배경, 테두리 등
    ax.grid(axis='x', linestyle='-', color='0.9')
    ax.set_facecolor('white')
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(1.1)

    # (MATLAB의 set(gca, 'FontName','Malgun Gothic') 등은
    # Python에서 rcParams 설정 등을 통해 별도로 처리 가능합니다.)

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

    # key(이름) 기준으로 뽑아오기

    # 후처리(notion 에 있음)

    # 번호매기는것



    # 1) 세 쌍의 데이터 예시
    subtaskNames1 = [
        'wash egg',
        'prepare egg fry',
        'wash potato',
        'wait turn off cooking egg',
        'turn off cooking egg',
        'prepare cook potato',
        'wash plate',
        'wait turn off cooking potato',
        'turn off cooking potato'
    ]
    durations1 = [2, 10, 2, 8, 1, 10, 4, 6, 10]
    chains1   = [4, 3, 2, 3, 3, 2, 1, 2, 2]

    subtaskNames2 = [
        'wash potato',
        'wash egg',
        'prepare cook potato',
        'prepare egg fry',
        'wait turn off cooking potato',
        'wait turn off cooking egg',
        'wash plate',
        'turn off cooking potato',
        'turn off cooking egg'
    ]
    durations2 = [3, 7, 8, 2, 1, 3, 2, 4, 5]
    chains2   = [2, 3, 2, 3, 2, 3, 1, 2, 3]

    subtaskNames3 = [
        'wash egg',
        'wash potato',
        'prepare egg fry',
        'wash plate',
        'prepare cook potato',
        'wait turn off cooking egg',
        'wait turn off cooking potato',
        'turn off cooking egg',
        'turn off cooking potato'
    ]
    durations3 = [2, 3, 10, 2, 5, 4, 8, 3, 4]
    chains3   = [3, 2, 3, 1, 2, 3, 2, 3, 2]

    # 2) 시작 시간 / 총 시간 계산
    startTimes1, totalTime1 = compute_start_times(durations1)
    startTimes2, totalTime2 = compute_start_times(durations2)
    startTimes3, totalTime3 = compute_start_times(durations3)

    # 가장 짧은 total time
    minTimeAll = min(totalTime1, totalTime2, totalTime3)
    # 가장 긴 total time (x축 공통 범위)
    maxTimeAll = max(totalTime1, totalTime2, totalTime3)

    # 3) figure/subplots 생성
    fig, axes = plt.subplots(nrows=3, ncols=1, 
                             figsize=(10, 8), 
                             sharex=False,
                             constrained_layout=True)
    fig.suptitle('Three DataSets with Shortest End-Time Mark', fontsize=14)

    # (3-1) 첫 번째 데이터셋
    plot_subtask_timeline(axes[0], subtaskNames1, durations1, chains1, startTimes1, maxTimeAll)
    axes[0].set_title('Dataset #1')
    # 빨간 세로선 (가장 짧은 total time)
    axes[0].axvline(minTimeAll, color='r', linewidth=2)
    # label을 가로로 달고 싶다면 다음처럼 text 추가
    axes[0].text(minTimeAll, axes[0].get_ylim()[1], 'Shortest End',
                 color='r', ha='left', va='top')

    # (3-2) 두 번째 데이터셋
    plot_subtask_timeline(axes[1], subtaskNames2, durations2, chains2, startTimes2, maxTimeAll)
    axes[1].set_title('Dataset #2')
    axes[1].axvline(minTimeAll, color='r', linewidth=2)
    axes[1].text(minTimeAll, axes[1].get_ylim()[1], 'Shortest End',
                 color='r', ha='left', va='top')

    # (3-3) 세 번째 데이터셋
    plot_subtask_timeline(axes[2], subtaskNames3, durations3, chains3, startTimes3, maxTimeAll)
    axes[2].set_title('Dataset #3')
    axes[2].axvline(minTimeAll, color='r', linewidth=2)
    axes[2].text(minTimeAll, axes[2].get_ylim()[1], 'Shortest End',
                 color='r', ha='left', va='top')

    plt.show()


if __name__ == "__main__":
    main()