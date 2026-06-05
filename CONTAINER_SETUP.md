# ROS 컨테이너 세팅 가이드

## 컨테이너 재생성 후 필수 세팅

### 공통 세팅 (자동 적용됨)

**참고**: 컨테이너 재생성 후 `.bashrc`에 자동으로 다음이 설정됩니다:
- `source /opt/ros/humble/setup.bash`
- `source /app/ros/ttp_ws/install/setup.bash` (워크스페이스가 빌드된 경우)
- `export DISPLAY=:99`
- `cd /app`

따라서 `docker compose exec ros bash`로 접속하면 자동으로 ROS 환경이 설정됩니다.

**수동 설정이 필요한 경우**:
```bash
# ROS 컨테이너 접속
docker compose exec ros bash

# (자동 설정이 안 된 경우에만 수동 실행)
export DISPLAY=:99
source /opt/ros/humble/setup.bash
source /app/ros/ttp_ws/install/setup.bash
cd /app
```

---

## 터미널별 실행 순서

### 터미널 1: UR 드라이버 실행
```bash
docker compose exec ros bash
# (ROS 환경은 자동으로 설정됨)

# UR 드라이버 실행
ros2 launch ur_robot_driver ur_control.launch.py ur_type:=ur5e robot_ip:=192.168.10.11 launch_rviz:=false
```

**참고**: UR5e teaching pendant에서 "External Control" 모드를 활성화해야 합니다.

### 터미널 2: MoveIt 실행
```bash
docker compose exec ros bash
# (ROS 환경은 자동으로 설정됨)

# MoveIt 실행
ros2 launch ur_moveit_config ur_moveit.launch.py ur_type:=ur5e launch_rviz:=true
```

### 터미널 3: Object Detector 실행
```bash
docker compose exec ros bash
# (ROS 환경은 자동으로 설정됨)

# Object Detector 실행
ros2 run object_detect_topic object_detector_11
```

### 터미널 4: Robot Manager Server 실행
```bash
docker compose exec ros bash
# (ROS 환경은 자동으로 설정됨)

# Robot Manager Server 실행
ros2 run robot_manager_state_transition robot_manager_service_server_05_ur5e
```

---

## 로그 확인

### ROS Bridge Server 로그 (HTTP 200/500 응답 확인)
```bash
# 호스트 터미널에서
docker logs -f ros
```

### 특정 노드 로그 확인
```bash
# ROS 컨테이너 내에서
ros2 topic echo /robot_manager/status
ros2 service list
ros2 topic list
```

---

## 실행 순서 요약

1. **터미널 1**: UR 드라이버 실행 (`ur_control.launch.py`)
2. **터미널 2**: MoveIt 실행 (`ur_moveit.launch.py`)
3. **터미널 3**: Object Detector 실행
4. **터미널 4**: Robot Manager Server 실행
5. **로그 확인**: `docker logs -f ros` (별도 터미널)

---

## 주의사항

- `ros_bridge_server`는 `docker-compose.yml`에서 자동으로 실행됩니다 (uvicorn)
- UR5e teaching pendant에서 "External Control" 모드를 활성화해야 합니다
- 네트워크 설정은 `docker-compose.yml`에 이미 포함되어 있습니다 (`CYCLONEDDS_URI`)
- **컨테이너 재생성 후**: `.bashrc`에 자동으로 ROS 환경이 설정되므로, `docker compose exec ros bash`만 실행하면 됩니다
- 만약 자동 설정이 작동하지 않으면, 수동으로 `source /opt/ros/humble/setup.bash` 등을 실행하세요

---

## 빠른 실행 스크립트 (선택사항)

컨테이너 재생성 후 `.bashrc`에 자동 설정이 되어 있으므로, 단순히 다음만 실행하면 됩니다:

```bash
docker compose exec ros bash
```

자동 설정이 작동하지 않는 경우에만 다음을 사용하세요:

```bash
docker compose exec ros bash -c "export DISPLAY=:99 && source /opt/ros/humble/setup.bash && source /app/ros/ttp_ws/install/setup.bash && cd /app && bash"
```

