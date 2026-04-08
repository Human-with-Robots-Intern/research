# AI2-THOR Task Scheduling Research Framework

이 프로젝트는 AI2-THOR 시뮬레이션 환경에서 가사 작업을 자동 수행하기 위한 태스크 스케줄링 및 실행 프레임워크입니다. 베이지안 추론을 통해 작업 소요 시간을 동적으로 학습하는 메인 스케줄러와 여러 비교 기준(Baseline) 알고리즘을 포함하고 있습니다.

## 프로젝트 구조 (`src` 폴더 기준)

-   `dag_bayesian.py`: 제안하는 메인 스케줄링 알고리즘(DAG-Bayesian)의 실행 파일입니다. 동적 계획, 실행 모니터링, 베이지안 소요 시간 추정 및 업데이트 기능을 통합합니다.
-   **`core/`**: 메인 스케줄러의 핵심 로직입니다.
    -   `scheduler.py`: 다음 행동을 결정하기 위한 정교한 탐색 기반 알고리즘을 구현한 스케줄러입니다.
    -   `agent.py`: 작업 소요 시간에 대한 지식을 관리하고, 베이지안 추론을 통해 이를 업데이트하는 에이전트 모델입니다.
-   **`scheduler/`**: 스케줄러의 보조 모듈입니다.
    -   `action_handler.py`: 시뮬레이터에서 원시 행동(primitive action)을 실행하고 소요 시간을 예측합니다.
    -   `constraint_handler.py`: 태스크 간의 시간적 제약 조건 및 의존성을 관리합니다.
    -   `heuristic_manager.py`: 스케줄러의 탐색을 안내하기 위한 휴리스틱 비용을 계산합니다.
-   **`baselines/`**: 성능 비교를 위한 다른 스케줄링/계획 알고리즘 구현체입니다.
    -   `cpm.py`: 주 경로 방법(Critical Path Method) 기반 스케줄러.
    -   `edf/`: 가장 빠른 마감 우선(Earliest Deadline First) 스케줄러.
    -   `cap/`: Code as Policies. 자연어 명령을 Python 코드로 변환하여 실행하는 LLM 기반 플래너.
    -   `progprompt/`: ProgPrompt. 자연어로부터 Python과 유사한 계획을 생성하는 LLM 기반 플래너.
-   **`models/`**: 태스크, 상태, 결과 등 프로젝트 전반에서 사용되는 데이터 구조를 정의합니다.
    -   `task.py`: `Task`, `Subtask` 등의 클래스를 정의합니다.
    -   `dataclass.py`: `SchedulerState`, `SimulationNode` 등 상태 저장을 위한 데이터 클래스를 정의합니다.
-   **`simulation/`**: AI2-THOR 시뮬레이터와의 상호작용을 담당합니다.
    -   `runner_ai2thor.py`: 시뮬레이터 컨트롤러를 초기화하고 태스크를 실행하는 함수를 포함합니다.
-   **`experiments/`**: 오프라인 비교 실험과 분석용 실행기를 포함합니다.
    -   `offline_harness.py`: DAG-Bayesian, EDF, CPM을 동일한 결과 스키마로 오프라인 실행하는 in-process 실험 실행기입니다.
    -   `exact_oracle.py`: 작은 deterministic 설정에서 scheduler 결과를 비교하기 위한 exhaustive oracle baseline입니다.
-   **`utils/`**: 입출력, 로깅, NLP, 시각화 등 범용 유틸리티 함수를 포함합니다.
-   `tune.py`: `Optuna`를 사용한 하이퍼파라미터 튜닝 스크립트입니다.

## 실행 방법

각 알고리즘은 개별 Python 스크립트로 직접 실행하거나, `scripts/run_all.py`를 통해 전체 실험을 자동화할 수 있습니다.

### 1. 개별 알고리즘 실행

#### DAG Bayesian, CPM, EDF

-   **설명**: `dag_bayesian.py`, `baselines/cpm.py`, `baselines/edf/dag_edf.py` 스크립트는 실행 시 `assets/tasks`에 정의된 태스크 목록을 보여주고 사용자에게 수행할 태스크를 선택하라고 요청합니다.
-   **명령어**:
    ```bash
    # 예시: CPM 베이스라인 실행
    python src/baselines/cpm.py --scene FloorPlan1
    ```
-   **인자**:
    -   `--scene`: 시뮬레이션 환경을 지정합니다 (예: `FloorPlan1`, `FloorPlan422`).

#### CAP, ProgPrompt (LLM 기반)

-   **설명**: Code as Policies 및 ProgPrompt 베이스라인은 실행 시 수행할 작업을 자연어 명령어 형태로 직접 받습니다.
-   **명령어**:
    ```bash
    # 예시: CAP 베이스라인 실행
    python src/baselines/cap/cap_ai2thor.py --instruction "make a coffee and toast a bread"
    ```
-   **인자**:
    -   `--instruction`: LLM이 계획으로 변환할 자연어 명령어입니다.
-   **참고**: `OPENAI_API_KEY` 환경변수 설정이 필요합니다.

### 2. 전체 실험 자동화 (`scripts/run_all.py`)

-   **설명**: 이 스크립트는 여러 알고리즘, 씬, 태스크 조합에 대한 실험을 자동으로 실행하고 결과를 관리하는 메인 실행기입니다.
-   **주요 기능**:
    -   지정된 `scene_type` (kitchen, bathroom)에 따라 여러 씬에서 순차적으로 실험을 실행합니다.
    -   사전에 정의된 모든 알고리즘(`approaches` 변수)에 대해 태스크를 수행합니다.
    -   LLM 기반 접근 방식 (`cap`, `progprompt`)은 실패 시 재시도 로직을 포함하여 안정성을 높입니다.
    -   기타 알고리즘 (`cpm`, `edf`, `dag_bayesian`)은 표준 입력(stdin)을 통해 태스크를 자동으로 전달하여 실행합니다.
-   **명령어**:
    ```bash
    python scripts/run_all.py --scene_type kitchen
    ```
-   **인자**:
    -   `--scene_type`: `kitchen` 또는 `bathroom` 중 하나를 선택하여 관련 씬들에서 실험을 진행합니다.
    -   `--predefined`: `assets/tasks/nl_instructions`의 자연어 명령어 대신 1부터 20까지의 숫자 입력을 사용하려면 이 플래그를 추가합니다.
    -   `--capture-output`: 자식 프로세스의 로그를 터미널에 실시간으로 표시하는 대신, 실행이 끝난 후 한 번에 보기 원할 때 사용합니다.

### 3. 오프라인 실험 실행 (`scripts/offline_experiment.py`)

-   **설명**: AI2-THOR 전체 시뮬레이션을 매번 실행하지 않고, planner-level schedule을 빠르게 비교하기 위한 오프라인 실행기입니다.
-   **지원 planner**:
    -   `bayesian`: 제안 방법의 오프라인 rollout
    -   `edf`: EDF baseline의 오프라인 adapter
    -   `cpm`: CPM baseline의 오프라인 adapter
-   **주요 특징**:
    -   동일한 report schema로 `makespan`, `schedule_tcsr`, `compute_time` 등을 비교할 수 있습니다.
    -   `--nav-graph-source ai2thor_controller`를 사용하면 AI2-THOR controller에서 navigation graph를 직접 읽어 offline planner에 사용할 수 있습니다.
    -   offline 결과는 planner-level schedule 비교에 적합하며, 실제 AI2-THOR simulation makespan과는 primitive 실행/pose 차이로 인해 소폭 차이가 날 수 있습니다.

#### 오프라인 grid 실행

```bash
python scripts/offline_experiment.py run \
  --planner-type edf \
  --case tasks_3_constraints_2 \
  --scene FloorPlan13 \
  --instructions 01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json \
  --beam-width-values 1 \
  --beam-depth-values 1 \
  --nav-graph-source ai2thor_controller \
  --output-path assets/results/offline_edf_compare.json
```

#### exact oracle 비교

```bash
python scripts/offline_experiment.py oracle-compare \
  --planner-type bayesian \
  --cases tasks_2_constraints_1 tasks_3_constraints_1 \
  --scene FloorPlan13 \
  --beam-width-values 1 5 10 \
  --beam-depth-values 1 5 10 \
  --oracle-time-limit-seconds 30 \
  --output-path assets/results/oracle_compare.json
```

#### 주요 인자

-   `--planner-type`: `bayesian`, `edf`, `cpm` 중 하나를 선택합니다.
-   `--case`, `--cases`: 단일 case 또는 여러 case를 지정합니다.
-   `--instructions`: 특정 instruction 파일만 선택해 실행합니다.
-   `--nav-graph-source`: `synthetic_grid` 또는 `ai2thor_controller` 중 하나를 선택합니다.
-   `--init-prior-mean`, `--init-prior-variance`: planner와 simulation 사이의 조건 정렬에 사용합니다.
-   `--output-path`: JSON report 저장 경로입니다.

### 4. 결과 해석 시 주의사항

-   offline harness는 planner-level 비교를 빠르게 반복하기 위한 도구입니다.
-   `offline makespan == scheduler makespan`은 맞출 수 있어도, `simulation makespan`은 AI2-THOR의 실제 primitive 실행 결과에 따라 약간 달라질 수 있습니다.
-   baseline인 EDF/CPM도 동일하게 offline과 AI2-THOR planner-level schedule은 정렬할 수 있지만, 실제 simulation 시간은 완전히 동일하지 않을 수 있습니다.