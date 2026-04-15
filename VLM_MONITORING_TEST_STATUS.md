# VLM Monitoring 실물 실험 테스트 상태

## 현재 상태
- 브랜치: `kyt/feature/vlm-monitoring-realworld`
- ROS 컨테이너: 재시작 후 드라이버/무빗/리얼센스 재실행 필요
- VLM 파이프라인: 코드 완성, 카메라→VLM→progress 반환 확인됨 (progress=0, 검은 이미지였음)
- **핵심 해결 이슈**: `uvcvideo quirks`가 `0xFFFFFFFF`로 설정되어 모든 카메라가 검은 화면이었음 → `sudo sh -c 'echo 0 > /sys/module/uvcvideo/parameters/quirks'`로 해결 (재부팅하면 리셋될 수 있음)

## ROS 컨테이너 시작 후 필수 작업

### 1. uvcvideo quirks 확인/수정 (호스트에서)
```bash
cat /sys/module/uvcvideo/parameters/quirks
# 0이 아니면:
sudo sh -c 'echo 0 > /sys/module/uvcvideo/parameters/quirks'
```

### 2. 컨테이너 내 openai 설치 (컨테이너 재생성 시마다)
```bash
docker exec -u root ros pip install openai
```

### 3. 카메라 디바이스 권한 (컨테이너 재시작 시마다)
```bash
docker exec -u root ros chmod 666 /dev/video6
```

### 4. 드라이버/무빗/리얼센스 실행
유저가 직접 실행함 (별도 터미널에서)

## 테스트 명령어

### ROS 쪽 단독 테스트 (이 랩탑에서)
```bash
curl -s -X POST http://localhost:8000/execute_translated_action \
  -H "Content-Type: application/json" \
  -d '{"action_parts": [0, 20, 33, 33], "instruction": "Cook Sausage"}'
```
기대 응답: `{"success": true, "progress": <0~130>}`

### 다른 PC에서 전체 파이프라인 테스트
```bash
PYTHONPATH=/app:/app/src ROS_BRIDGE_URL=http://192.168.0.9:8000 python3 -m src.dag_bayesian --ros --scene FloorPlan301 --task-folder-name FloorPlan301 --case "" --instruction cook_sausage_test.json
```

## 카메라 상황
- **내장 웹캠**: `/dev/video6` (컨테이너 내부 기준). 호스트에서는 `/dev/video0`. quirks 수정 후 정상 동작.
- **RealSense D435**: USB 2.1로만 잡힘 (이 랩탑 USB 3.0 포트 문제). 프레임 수신 불가. Thunderbolt 포트 또는 USB 3.0 허브 필요.
- **액션캠 (XPRO 415)**: USB에 인식되나 UVC 모드 전환 안 됨.
- **카메라 디바이스 인덱스**: `ros_bridge_server.py`의 `CAMERA_DEVICE_INDEX = 6`

## VLM 로그 위치
`assets/results/vlm_logs/<timestamp>/`
- `input_frame.jpg` — VLM에 보낸 이미지
- `vlm_log.json` — instruction, object_id, prompt_key, VLM 응답, parsed progress

## 변경된 파일 (ROS 컨테이너 쪽)
- `ros/ttp_ws/ttp_client/ttp_client/ros_bridge_server.py` — cv2.VideoCapture 기반 카메라, monitoring시 VLM 호출
- `ros/ttp_ws/ttp_client/ttp_client/ros_communicate.py` — communicate() dict 반환
- `ros/ttp_ws/ttp_client/ttp_client/vlm_progress_estimator.py` — VLM 프롬프트, OpenAI 호출, 로그 저장

## 변경된 파일 (TTP 컨테이너 쪽)
- `src/dag_bayesian.py` — ROS 모드 observation mode 변경, .json instruction, vlm_progress 전달
- `src/utils/ros_executor.py` — instruction 전달, progress 추출
- `src/core/monitoring.py` — BeliefUpdateContext에 vlm_progress, observe()에서 분기
- `src/core/agent.py` — update_monitoring_belief()에 vlm_progress 파라미터

## 아키텍처 흐름
```
TTP: dag_bayesian → ros_executor.execute_subtask("MONITORING stove")
  → POST /execute_translated_action {action_parts: [0,20,33,33], instruction: "Cook Sausage"}
  → ROS bridge: communicate() → RobotManager service → 5.9s 대기
  → capture frame from /dev/video6
  → VLM (gpt-4.1-mini): object_id=33→stove + instruction에서 "sausage" → sausage 프롬프트
  → progress (0~130, step 10) 반환
  → {"success": true, "progress": 70}
  → TTP: agent.update_monitoring_belief(state, vlm_progress=70)
  → monitoring.py: observation = prior_mean * (progress/100) → Bayesian update
```

## 미해결
- RealSense USB 3.0 연결 문제 (이 랩탑 하드웨어/포트 구조)
- 액션캠 UVC 모드 전환 안 됨
- `uvcvideo quirks` 재부팅 시 리셋될 수 있음 → `/etc/modprobe.d/`에 영구 설정 필요
- `docker exec -u root ros pip install openai` 컨테이너 재생성마다 필요 → Dockerfile에 추가 권장
