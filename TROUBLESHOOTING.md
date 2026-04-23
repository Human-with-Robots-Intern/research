# Real-World 실험 트러블슈팅 가이드

실제 실험 중 발생할 수 있는 하드웨어/소프트웨어 문제와 해결 방법 정리.

---

## 1. USB / 시리얼 장치 인식

### 1-1. Arduino가 `/dev/ttyACM*`에 안 잡힘

**증상:** `lsusb`에 Arduino(Vendor ID `2341`)가 안 보이고, `/dev/ttyACM*`가 생성되지 않음.

**원인 및 해결:**

| 순서 | 확인 사항 | 해결 |
|------|----------|------|
| 1 | USB 케이블이 **충전 전용**인지 확인 | 데이터 케이블로 교체 |
| 2 | USB 허브를 경유하는 경우, 허브 자체가 `lsusb`에 보이는지 확인 | 허브 뺐다 다시 꽂기, 허브↔PC 케이블 교체 |
| 3 | 위 모두 해도 안 되면 PC에 직접 연결해서 보드 자체 문제인지 분리 | 다른 포트에 꽂기, 케이블 교체 |

**확인 명령어:**
```bash
lsusb                          # Arduino SA Uno R3 (CDC ACM) 보이는지
lsusb -t                       # USB 트리에서 허브/장치 연결 구조 확인
ls -la /dev/ttyACM* /dev/ttyUSB*   # 시리얼 디바이스 확인
```

### 1-2. USB 재연결 후 포트 번호가 바뀜 (ttyUSB0 → ttyUSB1 등)

**증상:** USB 장치를 뺐다 꽂거나 순서가 바뀌면 `/dev/ttyUSB0`이 `/dev/ttyUSB1`로 변경됨.

**해결:** udev rule로 symlink를 설정해두면 포트 번호가 바뀌어도 코드 수정 불필요.

현재 설정:
- `/dev/arduino` → Arduino (`ttyACM*`)
- `/dev/gripper` → Robotiq 그리퍼 (`ttyUSB*`)

**확인:**
```bash
ls -la /dev/arduino /dev/gripper
```

symlink가 올바른 장치를 가리키지 않으면 udev rule 확인:
```bash
cat /etc/udev/rules.d/*arduino* /etc/udev/rules.d/*gripper* /etc/udev/rules.d/*serial* 2>/dev/null
```

### 1-3. Arduino 시리얼 포트를 열면 보드가 리셋됨

**증상:** Arduino에 시리얼 연결을 새로 열면 DTR 신호로 인해 보드가 자동 리셋되어, LED 모드(`btn1TaskMode`) 등 설정이 기본값으로 돌아감.

**주의사항:**
- `docker exec`로 Arduino 시리얼 포트를 직접 열지 말 것 (상태 확인 목적이라도 안 됨)
- `ros_bridge_server`가 이미 포트를 점유하고 있으므로 외부에서 열면 충돌 + 리셋 발생

**Arduino 상태 확인 방법:**
```bash
docker logs ros --timestamps -f 2>&1 | grep -i "arduino\|Sent to Arduino\|duration"
```

**컨테이너 재시작 시:** Arduino는 리셋되지만, 첫 액션 요청 시 instruction 기반으로 T1/T2가 자동 재전송됨.

---

## 2. RealSense D435 카메라

### 2-1. USB 2.0으로만 인식되어 프레임 수신 불가

**증상:** `Frame didn't arrive within 5 seconds` 에러. `lsusb -t`에서 D435가 Bus 03 (480M, USB 2.0)에 잡힘.

**원인:** laptop3의 일반 USB-A 포트가 모두 USB 2.0 허브(Bus 03)에 연결됨. D435는 USB 3.0 대역폭 필요.

**해결:**
- Thunderbolt 4 포트(Bus 04, 10000M)에 연결하면 USB 3.0으로 잡힐 가능성 있음
- 현재는 OpenCV `VideoCapture`로 대체 카메라 사용 중

**확인:**
```bash
lsusb -t   # D435가 5000M 이상 버스에 잡혀있는지 확인
```

---

## 3. Docker / ROS 컨테이너

### 3-1. 컨테이너에서 시리얼 장치 접근 불가

**증상:** 컨테이너 내부에서 `/dev/arduino`나 `/dev/gripper`를 못 찾음.

**확인:**
```bash
docker inspect ros | grep -A5 Devices   # 장치 매핑 확인
docker exec ros ls -la /dev/arduino /dev/gripper
```

**해결:** `docker-compose.yml` 또는 `docker run`에 `--device` 옵션으로 장치가 매핑되어 있는지 확인. USB 재연결 후 symlink가 바뀌었으면 컨테이너 재시작 필요할 수 있음.

### 3-2. ROS 로그 실시간 모니터링

```bash
# Arduino 관련 로그
docker logs ros --timestamps -f 2>&1 | grep -i "arduino\|Sent to Arduino\|duration"

# 전체 로그
docker logs ros -f

# 최근 N줄만
docker logs ros --tail 50
```

---

## 4. 빠른 진단 체크리스트

실험 시작 전 아래를 순서대로 확인:

```bash
# 1. 시리얼 장치 인식 확인
ls -la /dev/arduino /dev/gripper

# 2. USB 장치 트리 확인
lsusb -t

# 3. ROS 컨테이너 상태
docker ps | grep ros

# 4. ROS 컨테이너 내부에서 장치 접근 가능한지
docker exec ros ls -la /dev/arduino /dev/gripper

# 5. 카메라 정상 동작 확인
docker exec ros python3 -c "import cv2; cap=cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'Camera FAIL'); cap.release()"
```
