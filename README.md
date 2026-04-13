# AI2-THOR Task Scheduling Research Framework

이 프로젝트는 AI2-THOR 시뮬레이션 환경에서 가사 작업을 자동 수행하기 위한 태스크 스케줄링 및 실행 프레임워크입니다. 작업 소요 시간을 동적으로 추정하는 메인 스케줄러와 여러 비교 기준(Baseline) 알고리즘을 포함하며, 모니터링 업데이트 백엔드로 Gaussian Bayesian approximation과 particle filter를 모두 지원합니다.

## 프로젝트 구조 (`src` 폴더 기준)

-   `dag_bayesian.py`: 제안하는 메인 스케줄링 알고리즘(DAG-Bayesian)의 실행 파일입니다. 동적 계획, 실행 모니터링, 베이지안 소요 시간 추정 및 업데이트 기능을 통합합니다.
-   **`core/`**: 메인 스케줄러의 핵심 로직입니다.
    -   `scheduler.py`: 다음 행동을 결정하기 위한 정교한 탐색 기반 알고리즘을 구현한 스케줄러입니다.
    -   `agent.py`: 작업 소요 시간에 대한 지식을 관리하고, 모니터링 관측 후 posterior를 업데이트하는 에이전트 모델입니다.
    -   `monitoring.py`: Bayesian / particle-filter belief update, GT 샘플링, observation model, monitoring trigger policy를 구현합니다.
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

-   **권장 실행 환경**: 아래 예시는 프로젝트 Python 환경이 활성화되어 있다고 가정합니다. 예: `conda activate research`

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

-   **설명**: AI2-THOR 전체 시뮬레이션을 매번 띄우지 않고, planner-level schedule과 temporal constraint 성능을 빠르게 비교하기 위한 오프라인 실행기입니다.
-   **지원 approach**:
    -   `bayesian`: 제안 방법의 오프라인 rollout
    -   `edf`: EDF baseline adapter
    -   `cpm`: CPM baseline adapter
-   **주요 특징**:
    -   모든 approach가 동일한 single-run schema로 저장됩니다.
    -   `belief_update_method`로 `bayesian`과 `particle_filter`를 전환할 수 있습니다.
    -   `gt_distribution`으로 runtime GT duration 분포(`constant`, `gaussian`, `lognormal`, `gamma`, `mixture`)를 선택할 수 있습니다.
    -   PF 실행 시 `particle_distribution`을 따로 주지 않으면 기본적으로 현재 `gt_distribution`을 따라갑니다.
    -   `oracle_reference_dir`를 주면 결과 JSON에 oracle comparison 필드가 함께 포함됩니다.
    -   `nav_graph_source: ai2thor_controller`는 cache-first로 동작하며, 캐시가 없을 때만 AI2-THOR controller를 띄웁니다.
    -   `max_monitoring_per_critical_interval`를 지정하면 critical interval당 monitoring 실행 횟수 상한을 둘 수 있습니다. 값을 생략하면 uncapped입니다.

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
  --beam-bound 10,10 \
  --belief-update-method bayesian \
  --gt-distribution constant \
  --gt-seed 42 \
  --eta 0.1 \
  --nav-graph-source ai2thor_controller \
  --oracle-reference-dir assets/results/offline_oracle_reference \
  --output-path assets/results/offline_single_run.json
```

#### PF 단일 실행 예시

```bash
python scripts/offline/offline_experiment.py \
  --approach bayesian \
  --ablation-config DEFAULT \
  --init-prior-config UNDER_ESTIMATE \
  --task-folder-name sampled_10_instruction_set_for_final_experiment_251203 \
  --case tasks_3_constraints_2 \
  --scene FloorPlan13 \
  --instruction 01_boil_potato_and_heat_the_bread_using_microwave_and_put_apple_and_lettuce_in_fridge.json \
  --beam-bound 10,10 \
  --belief-update-method particle_filter \
  --gt-distribution lognormal \
  --particle-distribution lognormal \
  --gt-seed 42 \
  --eta 0.1 \
  --nav-graph-source ai2thor_controller \
  --oracle-reference-dir assets/results/offline_oracle_reference \
  --output-path assets/results/offline_pf_single_run.json
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
-   `--init-prior-config`: 대표적으로 `UNDER_ESTIMATE`, `CORRECT_ESTIMATE`, `OVER_ESTIMATE`를 사용합니다.
-   `--beam-bound`: `10,10`처럼 `(width, depth)` 쌍을 전달합니다.
-   `--belief-update-method`: `bayesian` 또는 `particle_filter`를 선택합니다.
-   `--gt-distribution`: monitoring에 사용되는 runtime GT duration 분포입니다.
-   `--particle-distribution`: PF particle initialization 분포입니다. 생략 시 PF는 `gt_distribution`, 비-PF는 `gaussian`을 사용합니다.
-   `--eta`: monitoring trigger risk tolerance입니다.
-   `--max-monitoring-per-critical-interval`: critical interval당 monitoring 실행 횟수 상한입니다. 생략하면 uncapped입니다.
-   `--gt-seed`: GT sampling, observation model, PF initialization/resampling에 사용되는 seed입니다.
-   `--case`, `--cases`: 단일 case 또는 여러 case를 지정합니다.
-   `--instruction`, `--instructions`: 특정 instruction 파일만 선택해 실행합니다.
-   `--nav-graph-source`: `synthetic_grid` 또는 `ai2thor_controller` 중 하나를 선택합니다.
-   `--oracle-reference-dir`: 미리 생성된 oracle reference JSON 루트 경로입니다.
-   `--output-path`: JSON report 저장 경로입니다.

### 4. 오프라인 suite 실행 (`scripts/offline/run_experiment_suite.py`)

-   **설명**: offline 실험을 one-command로 돌리기 위한 thin orchestrator입니다. oracle reference preflight, offline batch, 결과 분석을 순서대로 호출합니다.
-   **지원 suite**:
    -   `scalability`: beam/lookahead와 monitoring on/off의 효과를 비교합니다.
    -   `eta_sensitivity`: Bayesian monitoring에서 `eta` 민감도를 비교합니다.
    -   `monitoring_budget`: critical interval당 monitoring 횟수 cap(`1`, `2`, `3`, `uncap`)을 비교합니다.
    -   `pf_vs_bayesian`: non-Gaussian GT에서 Bayesian vs Particle Filter를 비교합니다.
    -   `all`: `scalability -> eta_sensitivity -> monitoring_budget -> pf_vs_bayesian` 순서로 모두 실행합니다.
-   **기본 동작**:
    -   suite 실행 전 oracle reference preflight를 먼저 수행합니다.
    -   oracle preflight는 항상 `skip-completed` semantics로 동작합니다.
    -   각 suite 종료 후 `offline_comparison.py`를 자동 실행합니다.
    -   lower-level script인 `run_oracle_reference_batch.py`, `run_batch.py`, `offline_comparison.py`는 그대로 유지됩니다.

#### 권장 실행 예시

```bash
python scripts/offline/run_experiment_suite.py --suite scalability
python scripts/offline/run_experiment_suite.py --suite eta_sensitivity
python scripts/offline/run_experiment_suite.py --suite monitoring_budget
python scripts/offline/run_experiment_suite.py --suite pf_vs_bayesian
python scripts/offline/run_experiment_suite.py --suite all
```

#### Dry-run 예시

```bash
python scripts/offline/run_experiment_suite.py --suite monitoring_budget --dry-run
```

#### Suite별 config

-   `scripts/offline/scalability_config.yaml`
-   `scripts/offline/eta_sensitivity_config.yaml`
-   `scripts/offline/monitoring_budget_config.yaml`
-   `scripts/offline/pf_vs_bayesian_constant_bayesian_config.yaml`
-   `scripts/offline/pf_vs_bayesian_constant_particle_filter_config.yaml`
-   `scripts/offline/pf_vs_bayesian_gaussian_bayesian_config.yaml`
-   `scripts/offline/pf_vs_bayesian_gaussian_particle_filter_config.yaml`
-   `scripts/offline/pf_vs_bayesian_lognormal_bayesian_config.yaml`
-   `scripts/offline/pf_vs_bayesian_lognormal_particle_filter_config.yaml`
-   `scripts/offline/pf_vs_bayesian_mixture_bayesian_config.yaml`
-   `scripts/offline/pf_vs_bayesian_mixture_particle_filter_config.yaml`

#### 현재 suite 설계 요약

-   `scalability`
    -   approaches: `bayesian`, `edf`, `cpm`
    -   ablation: `DEFAULT`, `NONE_MONITORING`
    -   GT: `constant`
    -   prior: `CORRECT_ESTIMATE`
    -   beam: `[1,1]`, `[5,5]`, `[10,10]`, `[20,20]`
-   `eta_sensitivity`
    -   approach: `bayesian`
    -   ablation: `DEFAULT`
    -   GT: `constant`
    -   prior: `UNDER_ESTIMATE`, `CORRECT_ESTIMATE`, `OVER_ESTIMATE` (`eta_sensitivity_config.yaml` 기준)
    -   beam: `[10,10]` (η만 스윕)
    -   eta: `0.01`, `0.1`, `0.5`, `0.9`
-   `monitoring_budget`
    -   approach: `bayesian`
    -   ablation: `DEFAULT`
    -   GT: `constant` (scalability·η suite와 동일 GT로 budget 효과만 비교)
    -   prior: `CORRECT_ESTIMATE`
    -   beam: `[10,10]`
    -   eta: `0.1`
    -   monitoring budget: `1`, `2`, `3`, `uncap`
-   `pf_vs_bayesian`
    -   approach: `bayesian`
    -   ablation: `DEFAULT`
    -   GT: `constant`, `gaussian`, `lognormal`, `mixture`
    -   belief: `bayesian` vs `particle_filter`
    -   prior: `UNDER_ESTIMATE`, `CORRECT_ESTIMATE`, `OVER_ESTIMATE`
    -   beam: `[10,10]`
    -   eta: `0.1`

### 5. 오프라인 oracle reference 생성 (`scripts/offline/run_oracle_reference_batch.py`)

-   **설명**: oracle을 batch baseline으로 함께 저장하는 대신, deterministic oracle reference를 먼저 일괄 생성한 뒤 이후 baseline 결과와 비교하는 방식입니다.
-   **설정 파일**: `scripts/offline/oracle_reference_config.yaml`
-   **명령어**:
    ```bash
    cd scripts/offline && python run_oracle_reference_batch.py --config oracle_reference_config.yaml
    python scripts/offline/run_oracle_reference_batch.py --config scripts/offline/oracle_reference_config.yaml
    ```
-   **출력 경로**:
    -   single-run oracle reference:
        `assets/results/offline_oracle_reference/<task_folder>/<scene>/<case>/<instruction>.json`
    -   batch summary:
        `assets/results/offline_oracle_reference/_batch_summary/offline_oracle_reference_<timestamp>.json`
-   **Oracle JSON vs 배치 GT (`gt_seed` / `gt_distribution`)**:
    -   Oracle reference는 `offline_harness` 안에서 **deterministic exact oracle**로 생성되며, 내부적으로 reference용 설정에 **`gt_distribution: constant`**가 고정됩니다(`ExperimentConfig` 병합). `oracle_reference_config.yaml`에 `gt_seed` 항목이 없어도 됩니다.
    -   베이지안(및 PF) **오프라인 배치**는 각 suite YAML의 **`gt_seed`**, **`gt_distribution`**으로 모니터링·GT 샘플링을 돌립니다. 재현성을 위해 suite 간 비교할 때는 **`gt_seed`를 맞추는 것**을 권장합니다.
    -   `offline_comparison`의 **makespan_gap**은 배치 `scheduler_makespan`과 oracle의 **`optimal_schedule_time`** 차이입니다. Oracle 쪽은 위 결정적 탐색 값이고, 배치 쪽 품질·TCSR은 해당 run의 GT 설정에 의존합니다.

### 6. 오프라인 batch 실행 (`scripts/offline/run_batch.py`)

-   **설명**: YAML config를 읽어 offline 실험을 일괄 실행합니다. `run_experiment_suite.py` 없이도 특정 config만 직접 돌릴 수 있습니다.
-   **명령어**:
    ```bash
    # scripts/offline 에서 파일명만 지정
    cd scripts/offline && python run_batch.py --config batch_config.yaml
    # 저장소 루트에서 repo-relative 경로 지정 가능
    python scripts/offline/run_batch.py --config scripts/offline/scalability_config.yaml
    ```
-   **자주 쓰는 config**:
    -   `scripts/offline/scalability_config.yaml`
    -   `scripts/offline/eta_sensitivity_config.yaml`
    -   `scripts/offline/monitoring_budget_config.yaml`
    -   `scripts/offline/pf_vs_bayesian_*_config.yaml`
-   **현재 batch 규칙** (`src/experiments/batch_runner.py`):
    -   **`bayesian`만** YAML의 전체 **`beam_bound`** 목록과 **`ablation_configs`** 스윕 대상입니다(실제 **beam search** 폭·깊이 스윕).
    -   **`edf` / `cpm`** 은 **beam search를 쓰지 않습니다.** YAML의 `beam_bound` 목록은 알고리즘에 반영되지 않으며, 오프라인 CLI·메타데이터 통일을 위해 **`beam_bound`의 첫 `(width, depth)`만** subprocess 인자로 넘길 뿐입니다. 결과 파일명도 `edf.json` / `cpm.json`처럼 beam 접미사가 없습니다. 스케일러빌리티 표의 **beam 축은 베이지안 전용**이고, EDF/CPM은 **고정된 베이스라인 한 점**으로만 나란히 둡니다.
    -   **`edf` / `cpm`** 은 **`DEFAULT` ablation 한 번만** 실행합니다(`NONE_MONITORING` 등 다른 ablation YAML 항목은 적용되지 않음).
    -   따라서 `edf`/`cpm`은 `NONE_MONITORING` 결과 파일을 만들지 않습니다.
    -   `max_monitoring_per_critical_intervals`는 현재 **`bayesian` + `DEFAULT`** 변형에서만 스윕됩니다.
-   **추가 batch 설정 키**:
    -   `belief_update_method`: `bayesian` 또는 `particle_filter`
    -   `gt_distribution`: `constant`, `gaussian`, `lognormal`, `gamma`, `mixture`
    -   `particle_distribution`: PF particle initialization 분포
    -   `factor_alpha`: synthetic Gaussian observation variance 계수 override
    -   `max_monitoring_per_critical_intervals`: critical interval당 monitoring cap 목록

#### 결과 저장 구조

-   result JSON:
    `assets/results/offline_exp_result/<suite_dir>/<task_folder>/<init_prior>/<scene>/<case>/<instruction_stem>/<baseline>/<file>.json`
-   worker log:
    `logs/<run_timestamp>/<suite_name>/<task_folder>/<init_prior>/<scene>/<case>/<instruction_stem>/<baseline>/<file>.log`
-   batch summary:
    `assets/results/offline_exp_result/<suite_dir>/_batch_summary/<suite_name>_<timestamp>.json`

`init prior`는 모든 suite에서 공통 상위 폴더로 유지됩니다. 따라서 `scalability`, `eta_sensitivity`, `monitoring_budget`도 `CORRECT_ESTIMATE/` 폴더를 명시적으로 갖습니다.

#### 파일명 규칙

-   `bayesian`: `DEFAULT__w10_d10[__eta0.1][__gtgaussian][__mb2].json`
-   `particle_filter`: `DEFAULT__w10_d10[__eta0.1]__gtlognormal[__pdistlognormal][__mb2].json`
-   `edf`: `edf.json`
-   `cpm`: `cpm.json`

즉 baseline 이름은 파일명이 아니라 상위 baseline 폴더로 표현됩니다.

#### PF-vs-Bayesian batch 실행 예시

```bash
python scripts/offline/run_batch.py \
  --config scripts/offline/pf_vs_bayesian_lognormal_particle_filter_config.yaml

python scripts/offline/run_batch.py \
  --config scripts/offline/pf_vs_bayesian_lognormal_bayesian_config.yaml
```

### 7. 결과 비교 분석 (`assets/result_analysis/offline_comparison.py`)

-   **설명**: oracle reference와 각 approach의 batch 결과를 비교하여 세 가지 산출물을 생성합니다.
    1.  `offline_comparison_raw.json`: scene/case/instruction별 oracle 필드 + approach별 makespan/computation_time gap
    2.  `offline_analysis_summary.json`: approach/case별 집계 지표
    3.  `offline_analysis_tol_sweep.json`: 저장된 `detail_log`를 재채점하여 tolerance별 TCSR을 다시 계산한 결과
-   **명령어**:
    ```bash
    python -m assets.result_analysis.offline_comparison \
      --base_dir assets/results \
      --batch_dirname offline_exp_result/offline_batch_pf_vs_bayesian \
      --oracle_dirname offline_oracle_reference \
      --task_folder sampled_10_instruction_set_for_final_experiment_251203 \
      --tolerance-sweep 5.0 8.0 12.5 15.0
    ```
-   **주요 인자**:
    -   `--base_dir`: oracle/batch 결과 루트를 포함하는 경로입니다.
    -   `--batch_dirname`: batch 결과 디렉터리 이름입니다. 예: `offline_exp_result/offline_batch_scalability`
    -   `--oracle_dirname`: oracle reference 디렉터리 이름입니다. 기본값은 `offline_oracle_reference`입니다.
    -   `--task_folder`: oracle reference와 batch 하위에 있는 task 폴더명입니다.
    -   `--skip_oracle_violated`: oracle 자체 스케줄이 constraint를 위반한 instruction을 집계에서 제외합니다.
    -   `--tolerance-sweep`: batch scheduler를 재실행하지 않고, 저장된 `detail_log`로 tolerance별 TCSR을 다시 계산합니다.
-   **출력 경로**: `--base_dir` 또는 `--output_dir` 아래에 저장됩니다.

#### `offline_analysis_summary.json` 읽는 법

집계 단위는 **approach_key × case**입니다. 같은 `case` 아래의 모든 scene·instruction이 평균에 포함됩니다.

-   **approach_key 생성 원칙**:
    -   가능하면 `meta_data` 기반으로 생성합니다.
    -   `init_prior_config`, `baseline_name`, `ablation_config`, `beam_width`, `beam_depth`, `eta`, `gt_distribution`, `particle_distribution`, `monitoring_budget_per_critical`를 key에 반영합니다.
    -   예:
        -   `CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1`
        -   `UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtlognormal`
        -   `CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__mb2` (monitoring_budget, `constant` GT)
-   **두 번째 키**: case 폴더명. 예: `tasks_2_constraints_2`
-   **값(지표 객체)**: 아래 필드는 모두 해당 `(approach_key, case)` 셀의 통계입니다.

| 필드 | 의미 |
|------|------|
| `n_instructions` | 해당 `(approach_key, case)`에 평균을 낸 instruction 수(배치 JSON이 있는 oracle-matched 행만; approach마다 다를 수 있음) |
| `sr` | 완료율(%) |
| `tsr` | 평균 schedule TCSR(%) |
| `makespan` | 평균 planner makespan(초) |
| `makespan_sr_1` | 완료된 instruction만 모아 평균한 makespan |
| `makespan_gap` | `(scheduler_makespan - oracle optimal_schedule_time)` 평균 |
| `makespan_gap_sr_1` | 완료된 instruction만 대상으로 한 makespan gap |
| `computation_time` | 평균 planner computation time(초) |
| `computation_time_gap` | `(batch computation_time - oracle computation_time)` 평균 |

`--skip_oracle_violated`를 켜면 oracle JSON의 constraint 위반 instruction이 집계에서 빠집니다. `--tolerance-sweep`는 평가 기준만 바꾸는 post-hoc 재채점이며, scheduler의 실제 행동이나 makespan을 다시 생성하지는 않습니다.

### 8. Navigation Graph Cache

-   `nav_graph_source: ai2thor_controller`를 사용하면 navigation graph를 `assets/cache/ai2thor_nav_graphs/<scene>.json`에 캐시합니다.
-   캐시가 존재하면 offline 실행은 이 파일을 우선 사용하고, 캐시가 없을 때만 controller를 초기화합니다.
-   따라서 같은 scene에 대한 반복 offline 실험에서는 AI2-THOR 초기화 비용이 크게 줄어듭니다.

### 9. 결과 해석 시 주의사항

-   offline harness는 planner-level 비교를 빠르게 반복하기 위한 도구입니다.
-   `offline makespan == scheduler makespan`은 맞출 수 있어도, `simulation makespan`은 AI2-THOR의 실제 primitive 실행 결과에 따라 약간 달라질 수 있습니다.
-   baseline인 EDF/CPM도 동일하게 offline과 AI2-THOR planner-level schedule은 정렬할 수 있지만, 실제 simulation 시간은 완전히 동일하지 않을 수 있습니다.
