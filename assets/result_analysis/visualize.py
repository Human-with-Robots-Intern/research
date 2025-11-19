import matplotlib.pyplot as plt
import numpy as np

# --- 데이터 준비 (평균값) ---
# 순서: [Under(60s), Correct(100s), Over(140s)]
data = {
    'Ours (Default)': {
        'tsr': [90.6, 87.9, 87.5], 
        'mk': [327.2, 328.3, 336.7],
        'color': 'red', 'marker': '*', 'style': '-'
    },
    'Ours (w/o Mon.)': { # Ablation
        'tsr': [61.2, 79.7, 59.4], 
        'mk': [311.5, 319.9, 339.7],
        'color': 'orange', 'marker': 'D', 'style': ':'
    },
    'EDF': {
        'tsr': [59.5, 90.8, 59.7], 
        'mk': [348.3, 350.8, 373.8],
        'color': 'gray', 'marker': '^', 'style': '-.'
    },
    'CPM': {
        'tsr': [59.7, 91.9, 60.0], 
        'mk': [356.5, 362.3, 404.1],
        'color': 'gray', 'marker': 's', 'style': '--'
    }
}

# --- 그래프 그리기 ---
fig, ax = plt.subplots(figsize=(8, 6))

# 각 Method별 궤적 그리기
for name, d in data.items():
    # 점 찍기
    ax.plot(d['mk'], d['tsr'], label=name, color=d['color'], 
            marker=d['marker'], linestyle=d['style'], 
            linewidth=2 if 'Default' in name else 1, markersize=10 if 'Default' in name else 6)
    
    # 방향성 표시 (Under -> Correct -> Over) - 옵션
    # ax.arrow(d['mk'][0], d['tsr'][0], d['mk'][1]-d['mk'][0], d['tsr'][1]-d['tsr'][0], 
    #          color=d['color'], alpha=0.3, width=0.5)

# --- 영역 하이라이트 (핵심) ---

# 1. Ours: Tight Cluster (Robustness)
from matplotlib.patches import Ellipse
ours_center = (np.mean(data['Ours (Default)']['mk']), np.mean(data['Ours (Default)']['tsr']))
cluster_circle = Ellipse(ours_center, width=30, height=6, angle=0, 
                         color='red', alpha=0.1)
ax.add_patch(cluster_circle)
ax.text(ours_center[0], ours_center[1]+4, "Robust & Efficient\n(Sweet Spot)", 
        color='red', ha='center', fontweight='bold')

# # 2. Baselines: Unstable Swing
# ax.annotate('Performance\nSwing', xy=(350, 90), xytext=(380, 75),
#             arrowprops=dict(facecolor='gray', arrowstyle='->', connectionstyle="arc3,rad=.2"),
#             color='gray', ha='center')
# ax.annotate('', xy=(360, 60), xytext=(380, 75),
#             arrowprops=dict(facecolor='gray', arrowstyle='->', connectionstyle="arc3,rad=-.2"),
#             color='gray')


# --- 축 및 설정 ---
ax.set_xlabel("Makespan (s) ↓ (Efficiency)", fontsize=12, fontweight='bold')
ax.set_ylabel("Temporal Success Rate (%) ↑ (Robustness)", fontsize=12, fontweight='bold')
ax.set_title("Performance Stability across Belief Conditions", fontsize=14, fontweight='bold')

# 그리드 및 범위
ax.grid(True, linestyle='--', alpha=0.5)
# 범례
ax.legend(loc='lower left', fontsize=10)

# 각 점이 무슨 조건인지 텍스트 표시 (Ours에만 표시해 깔끔하게)
# for i, txt in enumerate(['Under', 'Correct', 'Over']):
#     ax.text(data['Ours (Default)']['mk'][i], data['Ours (Default)']['tsr'][i]-3, txt, 
#             fontsize=8, color='red', ha='center')

plt.tight_layout()
plt.show()