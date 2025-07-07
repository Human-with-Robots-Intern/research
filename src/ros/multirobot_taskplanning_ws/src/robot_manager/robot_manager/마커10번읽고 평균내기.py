import numpy as np
from scipy.spatial.transform import Rotation as R

# Define the array
poses = np.array([
    [0.1045435, 0.03647691, 0.27324677, 0.46287933, 0.85703045, -0.22612133, 0.0105201],
    [0.10507831, 0.03696069, 0.27499041, 0.47279775, 0.8600928, -0.19157785, 0.00076571],
    [0.10399143, 0.03720534, 0.27339257, 0.4632556, 0.85694721, -0.22565965, 0.01065105],
    [0.1035335, 0.03539717, 0.27439103, 0.46631799, 0.86063184, -0.20449638, 0.00645028],
    [0.10319352, 0.03556902, 0.27498344, 0.46287076, 0.86057355, -0.21238415, 0.0075366],
    [0.10358235, 0.03570542, 0.27453125, 0.46277358, 0.86004096, -0.21457476, 0.01130622],
    [0.1031524, 0.03549161, 0.27258645, 0.46188882, 0.85981434, -0.21702263, 0.01670918],
    [0.10363545, 0.03519462, 0.27268233, 0.46275091, 0.8576982, -0.22352123, 0.01592639],
    [0.10391175, 0.03641117, 0.27341742, 0.4618417, 0.86003615, -0.21663719, 0.01041098],
    [0.10384101, 0.03631414, 0.27413839, 0.46342481, 0.8608497, -0.20983873, 0.01195639]
])

# 위치(position)와 방향(orientation) 데이터 분리
positions = poses[:, :3]  # 첫 3개 값이 위치
orientations = poses[:, 3:]  # 나머지가 쿼터니언

# 위치의 평균과 표준편차 계산
mean_position = np.mean(positions, axis=0)
std_position = np.std(positions, axis=0)

# 쿼터니안을 RPY로 변환
euler_angles = np.array([R.from_quat(q).as_euler('xyz') for q in orientations])

# RPY 각도의 평균과 표준편차 계산
mean_euler = np.mean(euler_angles, axis=0)
std_euler = np.std(euler_angles, axis=0)

# 위치와 RPY 모두에서 표준편차가 너무 큰 값을 제외
valid_indices = np.all(np.abs(positions - mean_position) < 2 * std_position, axis=1) & \
                np.all(np.abs(euler_angles - mean_euler) < 2 * std_euler, axis=1)

valid_positions = positions[valid_indices]
print("유효 포지션")
print(valid_positions)
valid_euler_angles = euler_angles[valid_indices]
print("유효 RPY angle")
print(valid_euler_angles)

if valid_positions.size == 0 or valid_euler_angles.shape[0] == 0:
    print("No valid poses found")
else:
    # 유효한 값들에 대해 최종 평균 계산
    final_mean_position = np.mean(valid_positions, axis=0)
    final_mean_euler = np.mean(valid_euler_angles, axis=0)

    # 최종 평균 RPY를 쿼터니안으로 변환
    final_mean_orientation = R.from_euler('xyz', final_mean_euler).as_quat()

    # 결과 출력
    print("Final Mean Position:", final_mean_position)
    print("Final Mean Orientation (Quaternion):", final_mean_orientation)
