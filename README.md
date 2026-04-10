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

각 알고리즘은 개별 Python 스크립트로 직접 실행하거나, `scripts/run_all_251028_pdk.py`와 설정 YAML을 통해 전체 실험을 자동화할 수 있습니다.

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

### 2. 전체 실험 자동화 (`scripts/run_all_251028_pdk.py`)

-   **설명**: AI2-THOR 시뮬레이션 상에서 여러 알고리즘·씬·태스크 조합을 돌리는 배치 실행기입니다. 실행 대상과 씬 목록은 **YAML 설정**으로 조정하고, CLI는 설정 경로와 드라이런 위주입니다.
-   **설정 파일**: `scripts/run_all_config.yaml` (기본값). `scene_type`, `scene_lists`, `approaches`, `llm_scripts`, `task_folder_name`, `ablation_configs`, `init_prior_configs` 등을 이 파일에서 수정합니다.
-   **주요 기능** (설정 기준, 스크립트 내부 동작):
    -   `scene_type`에 해당하는 씬들을 `scene_lists`에서 읽어 순차 실행합니다.
    -   `approaches`에 나열된 스케줄러 스크립트 경로를 subprocess로 실행합니다.
    -   `llm_scripts`에 속한 베이스라인은 실패 시 재시도 로직을 탑니다.
-   **명령어** (저장소 루트에서):
    ```bash
    python scripts/run_all_251028_pdk.py
    python scripts/run_all_251028_pdk.py --config run_all_config.yaml --dry-run
    ```
-   **CLI 인자**:
    -   `--config`: 설정 YAML 경로. 상대 경로는 `scripts/` 디렉터리 기준입니다.
    -   `--dry-run`: 실제 실행 없이 수행될 실험 목록만 확인합니다.
    -   `--skip-completed`: 이미 결과 JSON이 있으면 해당 태스크를 건너뜁니다 (기본 동작과 맞춘 플래그).

### 3. 오프라인 단일 실행 (`scripts/offline/offline_experiment.py`)

-   **설명**: AI2-THOR 전체 시뮬레이션을 매번 실행하지 않고, planner-level schedule을 빠르게 비교하기 위한 오프라인 실행기입니다.
-   **지원 approach**:
    -   `bayesian`: 제안 방법의 오프라인 rollout
    -   `edf`: EDF baseline의 오프라인 adapter
    -   `cpm`: CPM baseline의 오프라인 adapter
-   **주요 특징**:
    -   baseline과 bayesian 모두 동일한 single-run schema로 저장됩니다.
    -   `oracle_reference_dir`가 주어지면 baseline 결과에 oracle comparison 섹션이 함께 포함됩니다.
    -   `nav_graph_source: ai2thor_controller`는 내부적으로 cache-first로 동작하며, 캐시가 없을 때만 AI2-THOR controller를 띄웁니다.

#### 단일 실행 예시

```bash
python scripts/offline/offline_experiment.py \
  --approach bayesian \
  --ablation-config DEFAULT \
  --init-prior-config CORRECT_ESTIMATE \
  --task-folder-name sampled_10_instruction_set_for_final_experiment_251203 \
  --case tasks_3_constraints_2 \
  --scene FloorPlan13 \
  --instruction 01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json \
  --beam-bound 1,1 5,5 10,10 \
  --nav-graph-source ai2thor_controller \
  --oracle-reference-dir assets/results/offline_exp_result/offline_oracle_reference \
  --output-path assets/results/offline_single_run.json
```

#### 결과 비교 예시

```bash
python scripts/offline/offline_experiment.py compare \
  --before assets/results/before.json \
  --after assets/results/after.json \
  --output-path assets/results/offline_compare.json
```

#### 주요 인자

-   `--approach`: `bayesian`, `edf`, `cpm` 중 하나를 선택합니다.
-   `--ablation-config`: 현재 offline batch에서는 사실상 `bayesian`에만 의미가 있습니다.
-   `--init-prior-config`: `CORRECT_ESTIMATE`, `OVER_ESTIMATE_110` 등 초기 prior 설정 이름입니다.
-   `--beam-bound`: `1,1 5,5 10,10`처럼 `(width, depth)` 쌍 목록을 전달합니다. 실제 beam sweep은 `bayesian`에만 적용됩니다.
-   `--case`, `--cases`: 단일 case 또는 여러 case를 지정합니다.
-   `--instruction`, `--instructions`: 특정 instruction 파일만 선택해 실행합니다.
-   `--nav-graph-source`: `synthetic_grid` 또는 `ai2thor_controller` 중 하나를 선택합니다.
-   `--oracle-reference-dir`: 미리 생성된 oracle reference JSON 루트 경로입니다.
-   `--output-path`: JSON report 저장 경로입니다.

### 4. 오프라인 oracle reference 생성 (`scripts/offline/run_oracle_reference_batch.py`)

-   **설명**: oracle을 baseline approach로 같이 돌리는 대신, 먼저 deterministic oracle reference를 일괄 생성한 뒤 이후 baseline 결과와 비교하는 방식입니다.
-   **설정 파일**: `scripts/offline/oracle_reference_config.yaml`
-   **명령어**:
    ```bash
    cd scripts/offline && python run_oracle_reference_batch.py --config oracle_reference_config.yaml
    python scripts/offline/run_oracle_reference_batch.py --config scripts/offline/oracle_reference_config.yaml
    ```
-   **출력 경로**:
    -   single-run oracle reference:
        `assets/results/offline_exp_result/offline_oracle_reference/<task_folder>/<scene>/<case>/<instruction>.json`
    -   batch summary:
        `assets/results/offline_exp_result/offline_oracle_reference/_batch_summary/offline_oracle_reference_<timestamp>.json`

### 5. 오프라인 batch 실행 (`scripts/offline/run_batch.py`)

-   **설명**: `scripts/offline/batch_config.yaml`을 읽어 offline 실험을 일괄 실행합니다.
-   **명령어**:
    ```bash
    # scripts/offline 에서 파일명만 지정
    cd scripts/offline && python run_batch.py --config batch_config.yaml
    # 저장소 루트에서 repo-relative 경로 지정 가능
    python scripts/offline/run_batch.py --config scripts/offline/batch_config.yaml
    ```
-   **현재 batch 규칙**:
    -   `bayesian`만 `beam_bound`와 `ablation_configs`를 모두 sweep합니다.
    -   `edf`, `cpm`은 `DEFAULT` 한 번만 실행합니다.
    -   따라서 `edf`/`cpm`은 `NONE_MONITORING` 결과 파일을 만들지 않습니다.
-   **출력 경로**:
    -   single-run result:
        `assets/results/offline_exp_result/offline_batch/<task_folder>/<scene>/<case>/<instruction_stem>/<variant>.json`
    -   batch summary:
        `assets/results/offline_exp_result/offline_batch/_batch_summary/offline_batch_<timestamp>.json`
-   **variant naming 규칙**:
    -   `bayesian`: `bayesian__{ablation}__{init_prior}__w{width}_d{depth}.json`
    -   `edf`, `cpm`: `{approach}__DEFAULT__{init_prior}.json`

### 6. 결과 비교 분석 (`assets/result_analysis/offline_comparison.py`)

-   **설명**: oracle reference와 각 approach의 batch 결과를 비교하여 두 가지 산출물을 생성합니다.
    1.  `offline_comparison_raw.json`: scene/case/instruction별 oracle 필드 + approach별 makespan/computation_time gap
    2.  `offline_analysis_summary.json`: approach/case별 집계 지표 (sr, tsr, makespan, makespan_sr_1, makespan_gap, makespan_gap_sr_1, computation_time, computation_time_gap)
-   **명령어**:
    ```bash
    python -m assets.result_analysis.offline_comparison \
      --base_dir assets/results/offline_exp_result \
      --task_folder sampled_10_instruction_set_for_final_experiment_251203
    ```
-   **주요 인자**:
    -   `--base_dir`: `offline_oracle_reference/`와 `offline_batch/`를 포함하는 루트 경로입니다.
    -   `--task_folder`: oracle reference와 batch 하위에 있는 task 폴더명입니다.
    -   `--skip_oracle_violated`: oracle 자체 스케줄이 constraint를 위반한 instruction을 집계에서 제외합니다.
-   **출력 경로**: `--base_dir` (또는 `--output_dir`) 아래에 저장됩니다.

#### `offline_analysis_summary.json` 읽는 법

집계 단위는 **approach × case**입니다. 같은 `case` 아래의 **모든 scene·instruction**이 평균에 포함됩니다 (per-instruction 값은 `offline_comparison_raw.json` 참고).

-   **최상위 키 (approach_key)**: 배치 결과 파일 stem에서 유도됩니다.
    -   `cpm`, `edf`: 파일명이 `cpm__DEFAULT__…`, `edf__DEFAULT__…` 형태일 때 각각 한 키.
    -   Bayesian: `bayesian__{ablation}__{beam}` — 예) `bayesian__DEFAULT__w10_d10` (`bayesian__DEFAULT__CORRECT_ESTIMATE__w10_d10.json` → ablation + beam만 유지).
-   **두 번째 키**: case 폴더명 — 예) `tasks_2_constraints_2`.
-   **값(지표 객체)**: 아래 필드는 모두 해당 (approach, case) 셀에 대한 통계입니다.

| 필드 | 의미 |
|------|------|
| `sr` | **완료율(%)**. `n`개 instruction 중 batch JSON의 `completed == true`인 비율 × 100. |
| `tsr` | **평균 schedule TSR(%)**. instruction마다 `timing_success_rate_sched`(0~1)를 평균한 뒤 × 100. 정의는 `calculate_timing_success_rate`와 동일. |
| `makespan` | **평균 planner makespan**(초). batch의 `scheduler_makespan`이 있는 instruction만 평균. |
| `makespan_sr_1` | 완료된 instruction만 모아 같은 방식으로 평균한 makespan (실패·중단 run 제외). |
| `makespan_gap` | instruction별 `(scheduler_makespan - oracle optimal_schedule_time)`의 평균(초). 양수면 oracle보다 길게 걸린 경우가 평균적으로 많음. |
| `makespan_gap_sr_1` | 위 gap을 **완료된** instruction만으로 평균. |
| `computation_time` | batch `computation_time`(초) 평균. |
| `computation_time_gap` | instruction별 `(batch computation_time - oracle computation_time)` 평균(초). |

`--skip_oracle_violated`를 켜면, oracle JSON의 `steps[].detail_log`에 `[False]`가 있는 instruction은 집계에서 빠집니다. Oracle이 제약을 어긴 채로 기록된 경우 `optimal_schedule_time`이 왜곡되어 gap이 부정확해질 수 있어 사용합니다.

### 7. Navigation Graph Cache

-   `nav_graph_source: ai2thor_controller`를 사용하면 navigation graph를 `assets/cache/ai2thor_nav_graphs/<scene>.json`에 캐시합니다.
-   캐시가 존재하면 offline 실행은 이 파일을 우선 사용하고, 캐시가 없을 때만 controller를 초기화합니다.
-   따라서 같은 scene에 대한 반복 offline 실험에서는 AI2-THOR 초기화 비용이 크게 줄어듭니다.

### 8. 결과 해석 시 주의사항

-   offline harness는 planner-level 비교를 빠르게 반복하기 위한 도구입니다.
-   `offline makespan == scheduler makespan`은 맞출 수 있어도, `simulation makespan`은 AI2-THOR의 실제 primitive 실행 결과에 따라 약간 달라질 수 있습니다.
-   baseline인 EDF/CPM도 동일하게 offline과 AI2-THOR planner-level schedule은 정렬할 수 있지만, 실제 simulation 시간은 완전히 동일하지 않을 수 있습니다.