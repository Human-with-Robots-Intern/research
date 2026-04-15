# LaMMA-P Baseline 셋업 가이드

> 다 읽었으면 이 파일 삭제해주세요.

---

## 개요

LaMMA-P(ICRA 2025)는 LLM + PDDL planner를 사용하는 multi-agent task planning baseline입니다.
우리 프로젝트의 ai2thor 환경에서 CAP, ProgPrompt 등 다른 baseline과 동일한 인터페이스로 동작하도록 통합했습니다.

**논문**: https://arxiv.org/abs/2409.20560

---

## 실행 전 셋업 (처음 한 번만)

### 1. Fast Downward Planner 빌드

git에 소스가 올라가있지 않습니다. 직접 clone 후 빌드해야 합니다.

```bash
cd src/baselines/lammap/
git clone https://github.com/aibasel/downward.git
cd downward
python3 build.py
```

빌드 완료 확인:
```bash
python3 fast-downward.py --help
```

> 빌드에 cmake, g++ 필요합니다. 도커 컨테이너(ttp)에는 이미 설치되어 있습니다.

### 2. OpenAI API Key 설정

```bash
# src/baselines/lammap/api_key.txt 파일에 키 입력
echo "sk-proj-xxxx..." > src/baselines/lammap/api_key.txt
```

---

## 실행 방법

### 방법 1: 단독 실행 (테스트용)

```bash
# 도커 컨테이너 안에서
python3 -m src.baselines.lammap.lammap_ai2thor \
    --scene FloorPlan1 \
    --instruction "Place the apple in the fridge" \
    --openai-api-key-file src/baselines/lammap/api_key \
    --gpt-version gpt-4o
```

### 방법 2: run_all을 통한 실행 (실험용)

`scripts/run_all_config.yaml`에서 lammap 활성화:
```yaml
llm_scripts:
  - "src/baselines/lammap/lammap_ai2thor.py"
```

실행:
```bash
python3 scripts/run_all_251028_pdk.py
```

> run_all은 `--instruction`에 JSON 파일명(예: `01_boil_potato_and_heat_the_bread.json`)을 전달합니다.
> lammap_ai2thor.py가 파일명에서 자연어 태스크를 자동 추출합니다.

---

## 실행 파이프라인

```
instruction ("Place the apple in the fridge")
    │
    ▼
[1] ai2thor 컨트롤러 초기화 (~5초)
    │
    ▼
[2] 씬 객체 정보 추출 → LaMMA-P 형식 변환 (~0.1초)
    │
    ▼
[3] LLM으로 태스크 분해/할당/PDDL 생성 (~60초, OpenAI API 호출 4~6회)
    │  └─ decompose → allocate → problem summary → PDDL problem files
    │
    ▼
[4] Fast Downward로 PDDL 풀기 (~1초)
    │
    ▼
[5] LLM으로 plan → 실행코드 변환 (~15초, OpenAI API 호출 2회)
    │  └─ translate_to_mimic_format → validate_and_fix
    │
    ▼
[6] 생성 코드 파싱 → primitive actions 변환
    │  └─ GoToObject → NAVIGATE_TO
    │     PickupObject → GRASP
    │     PutObject → PLACE_INSIDE / PLACE_ON_TOP
    │     SwitchOn/Off → TOGGLE_ON / TOGGLE_OFF
    │     OpenObject → OPEN, CloseObject → CLOSE
    │     SliceObject → SLICE
    │
    ▼
[7] Action handler로 ai2thor 실행 (~3~5분)
    │
    ▼
[8] 결과 저장 (trajectory_log.json)
```

**태스크 1개 총 소요시간: 약 5~7분** (대부분 LLM API 호출 + ai2thor 실행 시간)

---

## 디렉토리 구조

```
src/baselines/lammap/
├── lammap_ai2thor.py          # 메인 엔트리포인트 (이것만 실행하면 됨)
├── action_adapter.py          # LaMMA-P 코드 → primitive actions 변환
├── plantocode.py              # PDDL plan → Python 코드 변환 (LLM)
├── api_key.txt                # OpenAI API 키 (직접 입력 필요)
├── .gitignore
│
├── scripts/
│   └── pddlrun_llmseparate.py # PDDL 계획 생성 핵심 로직
│
├── resources/
│   ├── allactionrobot.pddl    # PDDL 도메인 (전체 액션)
│   ├── robot1~28.pddl         # 로봇별 PDDL 도메인
│   ├── robots.py              # 로봇 정의
│   └── actions.py             # 액션 정의
│
├── data/
│   └── pythonic_plans/        # LLM 프롬프트 템플릿 (5개)
│
└── downward/                  # Fast Downward (git clone 필요, .gitignore 처리됨)
```

---

## 주의사항

- **OpenAI API 비용**: 태스크 1개당 API 호출 6~8회 발생 (gpt-4o 기준)
- **cloud_rendering**: headless 환경에서는 `--cloud-rendering` 또는 Xvfb 필요
- **로컬 화면 확인**: 도커 컨테이너에서 호스트 디스플레이로 보려면 `/tmp/.X11-unix` 마운트 + `DISPLAY=:1` 설정 필요 (GLX 에러 발생 가능, 실행 자체는 영향 없음)
- **GPT 모델**: 기본 gpt-4o, `--gpt-version`으로 변경 가능

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `API key file not found` | api_key.txt에 키 미입력 | `src/baselines/lammap/api_key.txt`에 키 입력 |
| `fast-downward.py not found` | downward 미빌드 | 위 셋업 1번 참고 |
| 컨트롤러 초기화에서 멈춤 | X server 없음 | `--cloud-rendering` 추가 또는 Xvfb 실행 |
| `thor-Linux64 <defunct>` | Unity 렌더러 crash | Xvfb 실행 확인: `Xvfb :99 -screen 0 1024x768x24 &` |

---

> **다 읽었으면 이 파일 삭제해주세요.**
