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
- ~~액션캠 UVC 모드 전환 안 됨~~ → **2026-04-23 해결됨.** 아래 "실세계 녹화 파이프라인" 참고.
- `uvcvideo quirks` 재부팅 시 리셋될 수 있음 → `/etc/modprobe.d/`에 영구 설정 필요
- `docker exec -u root ros pip install openai` 컨테이너 재생성마다 필요 → Dockerfile에 추가 권장

---

# 실세계 녹화 파이프라인 (VLM realworld task별 자동 mp4 저장)

## 아키텍처

```
[laptop3 (host)]                              [remote PC (ttp 컨테이너)]
  /dev/video8 (XPRO 415 액션캠)                  run_all_251028_pdk.py
     │                                              │ worker(task) {
     │  ffmpeg -f v4l2 -i ...                       │   if not simulation:
     │      → H.264(libx264 ultrafast/crf 28)       │     with ActionCamRecorder(...):
     │      → MPEG-TS over HTTP :9986 ─── LAN ───▶  │       _run_script_and_log(...)
     │      (scripts/infra/serve_actioncam.sh)      │ }
                                                    │
                                                    ▼
                                        LOG_PATH/{ts}-worker_logs/videos/
                                          ├─ {stem}_try{N}.mp4 (fragmented H.264)
                                          └─ {stem}_try{N}.ffmpeg.log (recorder stderr)
```

- **laptop3**: `serve_actioncam.sh` 가 v4l2에서 MJPG을 받아 **libx264로 재인코딩**하여 MPEG-TS로 송출. 매 클라이언트 끊김마다 while-loop이 ffmpeg를 respawn.
- **ttp 컨테이너**: `src/utils/recording.py`의 `ActionCamRecorder` 컨텍스트 매니저가 TS를 pull, `-c:v copy`로 **fragmented mp4**에 remux 저장. task 시작=스트림 open, task 종료=close. retry loop로 서버 respawn 레이스 커버.
- **대역폭/용량**: H.264 CRF=28 ultrafast 기준 약 **0.5–1.5 Mbps**, 1분당 **~4–11 MB**.
- **재생 호환**: fragmented mp4라 Windows Media Player / VLC 모두 정상 재생 (중간에 끊겨도 직전 keyframe까지 재생 가능).

## 관련 파일

- `scripts/infra/serve_actioncam.sh` — laptop3 측 MJPG→H.264 MPEG-TS 서버
- `src/utils/recording.py` — ttp 측 `ActionCamRecorder`
- `scripts/run_all_251028_pdk.py` — worker에서 real-world일 때만 recorder 감싸기
- `~/.claude/projects/-home-laptop3-kyungtae-ws-research/memory/hardware_actioncam_xpro415_uvc_recipe.md` — 액션캠 UVC 바인딩 복구 레시피 (재부팅 시 필요)

## Knob (env overrides)

| 변수 | 기본값 | 의미 |
|---|---|---|
| `CAM_DEVICE` | `/dev/video8` | serve: v4l2 장치 |
| `CAM_PORT` | `9986` | serve: MPEG-TS HTTP 포트 |
| `CAM_SIZE` | `1280x720` | serve: 캡처 해상도 (카메라는 이것만 지원) |
| `CAM_PRESET` | `ultrafast` | serve: x264 preset |
| `CAM_CRF` | `28` | serve: x264 품질 (낮을수록 고품질/큰 파일) |
| `CAM_GOP` | `30` | serve: keyframe 간격 (프레임 단위) |
| `ACTIONCAM_HOST` | `192.168.0.9` | ttp recorder: laptop3 IP |
| `ACTIONCAM_PORT` | `9986` | ttp recorder: 서버 포트 |
| `ACTIONCAM_FLUSH_SECONDS` | `0` | ttp recorder: 사전 버퍼 flush (현재 구조에선 0 유지) |

---

# 재부팅 후 복구 체크리스트

랩탑/ttp PC를 껐다 켜거나, 액션캠을 뽑았다 꽂았을 때 녹화를 다시 쓰기 위한 순서.

## 1. laptop3 쪽 — 액션캠 UVC 바인딩

재부팅하면 `uvcvideo new_id` / `usb-storage unbind` 같은 커널 런타임 설정이 **전부 리셋**됩니다. `/etc/modprobe.d/`에 영구화 안 해둔 상태라 매번 확인 필요.

### 1-1. 액션캠 전원 ON + PC Cam 모드 진입
액션캠 본체에서 PC Cam / USB Webcam 모드를 선택. 액정에 진입 표시가 떠야 함.

### 1-2. USB 포트 선택 — **Thunderbolt(USB-C) 또는 USB 3.0 직결 포트**에 꽂기
Arduino 2개가 달린 USB 2.0 허브 경유는 **피할 것** (대역폭/전력 경합으로 stuck 발생). 액션캠 자체가 USB 2.0 장치라 속도 차이는 없지만 **허브를 단독으로 쓰는 것이 중요**.

### 1-3. 구성 판별

```bash
# sysfs 경로 재탐색 (포트 바꾸면 경로 달라짐)
for d in /sys/bus/usb/devices/*/idVendor; do [ "$(cat $d 2>/dev/null)" = "1f3a" ] && echo $(dirname $d); done
# 그 경로의 :1.0 bInterfaceClass
CAM_SYS=$(for d in /sys/bus/usb/devices/*/idVendor; do [ "$(cat $d 2>/dev/null)" = "1f3a" ] && dirname $d; done)
cat "$CAM_SYS/$(basename $CAM_SYS):1.0/bInterfaceClass"
```

- `0e` → **구성 A (표준 UVC)**. 1-4 건너뛰고 바로 1-5로.
- `08` → **구성 B (Mass Storage)**. 1-4 실행.

### 1-4. (구성 B일 때만) 복구 레시피

```bash
BASENAME=$(basename $CAM_SYS)
echo -n "${BASENAME}:1.0" | sudo tee /sys/bus/usb/drivers/usb-storage/unbind
echo "1f3a 1002" | sudo tee /sys/bus/usb/drivers/uvcvideo/new_id
# 그다음 USB 케이블을 물리적으로 뽑았다 다시 꽂기 (주입만으로는 전환 안 됨)
# 꽂은 뒤 다시 1-3 판별 → 0e 나올 때까지 반복
```

### 1-5. 카메라 프레임 테스트

```bash
timeout 5 ffmpeg -loglevel error -f v4l2 -input_format mjpeg -video_size 1280x720 -framerate 30 -i /dev/video8 -t 3 -c:v copy /tmp/cam_check.mp4 ; ls -la /tmp/cam_check.mp4
```
**3~5 MB 파일** 생성되면 카메라 OK. 0 byte거나 매우 작으면 **USB 케이블 뽑았다 꽂기 + 액션캠 전원 재시작** 반복.

### 1-6. ffmpeg 미설치면 설치
```bash
which ffmpeg || sudo apt install -y ffmpeg
```

### 1-7. 방화벽 확인 (ufw 쓰는 경우)
```bash
sudo ufw status | grep 9986 || sudo ufw allow 9986/tcp
```

### 1-8. 서버 기동
```bash
bash scripts/infra/serve_actioncam.sh
```
splash 뒤에 `Input #0 ...mjpeg 1280x720 30fps` 가 뜨면 대기 상태. 클라가 붙으면 `Output #0, mpegts...` 와 `frame=N fps=30 bitrate=~1Mbit/s speed=1x` 로그가 나오면 정상 스트리밍.

## 2. ttp 쪽 (원격 PC)

### 2-1. 브랜치 최신화
```bash
cd ~/pdk_ws/research
git pull --rebase origin kyt/feature/vlm-monitoring-realworld
```

### 2-2. 컨테이너 내부 ffmpeg (최초 1회 또는 컨테이너 재생성 후)
```bash
docker exec -u root ttp bash -c 'apt-get update && apt-get install -y ffmpeg'
```
영구화하려면 ttp 컨테이너 Dockerfile에 `RUN apt-get install -y ffmpeg` 추가 권장.

### 2-3. 연결성 확인
```bash
docker exec ttp ffmpeg -y -i http://192.168.0.9:9986 -t 3 -c:v copy /tmp/ttp_check.mp4 && docker exec ttp ls -la /tmp/ttp_check.mp4
```
**~500 KB 이상** 파일 나오면 전 경로 정상. 실패하면 laptop3 쪽 1-3/1-5부터 재확인.

### 2-4. run_all 실행
```bash
python3 scripts/run_all_251028_pdk.py --config <config.yaml>
```

## 3. 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| ttp `.ffmpeg.log`에 `Connection refused` 반복 | 서버가 respawn 중. 내장 retry(30s 예산) 안에서 성공하는지 확인. 계속 실패면 laptop3 쪽 서버가 안 돌거나 stuck — 1-3, 1-8 재확인 |
| `.ffmpeg.log`에 `Could not write header ... incorrect codec parameters` | TS input probe 실패. 이미 `-probesize 10M -analyzeduration 10s`로 넓혔음. 그래도 나면 probe 값 더 키울 것 |
| laptop3 서버 로그 `speed=0.56x`, `Broken pipe` | 클라이언트 probe 실패로 backpressure. ttp 측 recording.py pull 최신(`51ddc9d2`+)인지 확인 |
| 녹화 파일 0 byte 또는 수 KB | v4l2 input이 프레임 못 뱉는 상태. 카메라 펌웨어 stuck — 액션캠 본체 전원 OFF/ON → PC Cam 재진입 → 케이블 재연결 |
| Windows Media Player `0xC00D36C4` | mp4 moov atom 누락. 현재 구조는 fragmented mp4라 발생 안 해야 정상. 여전히 나면 ttp 측 recording.py가 최신(`frag_keyframe+empty_moov+default_base_moof`) 인지 확인 |
| 구성이 B에서 A로 안 넘어감 | 주입(usb-storage unbind + uvcvideo new_id) 단계를 **생략**한 채 뽑았다 꽂기만 했을 가능성. 1-4 순서 그대로 실행 필요 |

## 4. 주의사항

- **동시 한 클라이언트만**: ffmpeg `-listen 1` 제약. run_all의 `max_workers`는 **1**로 유지 (real-world는 로봇 공유로 어차피 직렬).
- **서버 장기 운용 시 카메라 stuck 가능**: 반복된 open/close 누적으로 UVC 드라이버 상태 나빠질 수 있음. 주기적으로 stuck 나면 **물리 재연결 + 1-3~1-8 순서** 재실행이 가장 확실.
- **장기적 개선안**: 현재 `-listen 1` + while-loop 구조는 매 task마다 서버 재시작이라 구조적 약점이 있음. 안정성을 올리려면 mediamtx / nginx-rtmp 같은 **포트를 계속 열어두는** 전용 스트리밍 서버로 바꾸는 게 정석. 당장은 현재 구조로 돌아감.

