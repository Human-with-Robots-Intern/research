# 연구 실험 환경 설정 및 실행 가이드

이 문서는 우분투(Ubuntu) 환경에서 연구 실험을 재현하기 위한 설정 및 실행 방법을 안내합니다.
NVIDIA GPU가 없는 환경(CPU 전용)에서도 동작하도록 구성되어 있으며, Docker를 사용하여 환경을 구축합니다.
---

## 1. 세팅 (Setup)

### 1-1. 도커(Docker) 설치

실험 환경은 Docker 컨테이너 위에서 구동됩니다. 아직 Docker가 설치되어 있지 않다면 아래 명령어로 설치해주세요.

```bash
# 필수 패키지 설치
sudo apt update
sudo apt install ca-certificates curl gnupg

# Docker 공식 GPG 키 추가
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker 저장소 설정
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker Engine 설치
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# sudo 없이 docker 명령어 사용하기 설정 
sudo usermod -aG docker $USER
(설정 후 재부팅 또는 로그아웃/로그인 필요)
```

### 1-2. 프로젝트 다운로드 (Git Clone)
*(현재 단계에서는 생략합니다. 제공받은 압축 파일을 해제하거나 코드가 있는 디렉토리로 이동해주세요.)*

```ini
# .env 파일 예시
프로젝트 루트에 .env.example파일의 파일명에서 .exmple을 지워서 .env파일로 만들어줍니다.
터미널에서 whoami를 입력해서 나오는이름을 USERNAME에 입력해주세요
본인의 OPENAI API 키를 입력해주세요
OPENAI_API_KEY=sk-your-openai-api-key-here
```
> **주의:** `OPENAI_API_KEY`는 실제 사용 가능한 키를 입력해야 LLM 기반 실험이 정상 작동합니다.

### 1-3. 화면 설정 (Display Setup)

시뮬레이터 화면을 로컬 디스플레이에 띄우기 위해 호스트의 X Server 접근 권한을 허용해야 합니다.
터미널에서 아래 명령어를 한 번 실행해주세요. (재부팅 시 초기화될 수 있으므로, 실행 전 매번 확인하거나 `.bashrc`에 추가해도 됩니다.)

```
xhost +local:docker
```

### 1-4. 도커 컨테이너 실행

배포용 설정 파일(`docker-compose-dist.yml`)을 사용하여 컨테이너를 빌드하고 실행합니다.
디스플레이 설정을 컨테이너에 전달합니다.

```bash

DISPLAY=$DISPLAY docker compose -f docker-compose-dist.yml up ttp -d --build

# gpu가 존재하면서 cuda 12.5를 사용 가능한 경우
DISPLAY=$DISPLAY docker compose docker-compose.yml up ttp -d --build
```
> 최초 실행 시 이미지를 빌드하느라 시간이 다소 소요될 수 있습니다.

---

## 2. 실행 (Execution)

### 2-1. 실험 설정 (Config)

실험의 파라미터는 `scripts/run_all_config.yaml` 파일에서 수정할 수 있습니다.
주요 설정 항목은 다음과 같습니다.


### 2-2. 실험 코드 실행

컨테이너 내부로 진입하여 실험 스크립트를 실행합니다.

1. **컨테이너 접속**
   ```
   docker exec -it ttp_dist bash
   # gpu 세팅으로 container를 만든 경우
   docker exec -it ttp bash
   ```

2. **실험 스크립트 실행**
   컨테이너 내부 쉘에서 다음 명령어를 입력합니다.
   ```
   python3 scripts/run_all_251028_pdk.py
   ```
   
   - 실행 시 설정된 시뮬레이터 화면이 로컬 모니터에 팝업됩니다.
   - 로그는 터미널에 출력되며, 결과 파일은 `assets/results/` 경로 등에 저장됩니다.
   - 최초실행시 ai2thor 빌드로인해 3분이상 걸릴 수 있습니다.


