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
    -   `belief_robustness.py`: scheduler를 배제한 PF-vs-Bayesian Monte Carlo 벤치마크입니다. Reviewer 10 대응용 non-Gaussian robustness 비교와 trigger calibration 분석에 사용합니다.
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
-   **주요 특징**: approach 공통 스키마, `belief_update_method`·`gt_distribution`·PF용 `particle_distribution`, `oracle_reference_dir`, `nav_graph_source`(캐시 우선), `max_monitoring_per_critical_interval`(선택) 등. 세부는 `python scripts/offline/offline_experiment.py --help`.

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

PF는 `--belief-update-method particle_filter`와 `--gt-distribution` / `--particle-distribution`만 맞춰 바꾸면 됩니다.

#### 결과 비교 예시

```bash
python scripts/offline/offline_experiment.py compare \
  --before assets/results/before.json \
  --after assets/results/after.json \
  --output-path assets/results/offline_compare.json
```

#### 주요 인자

`--approach`, `--beam-bound`, `--belief-update-method`, `--gt-distribution`, `--gt-seed`, `--eta`, `--case`/`--instruction`, `--nav-graph-source`, `--oracle-reference-dir`, `--output-path` 등. `--ablation-config`는 배치에서 주로 베이지안에 적용됩니다.

### 4. 오프라인 suite 실행 (`scripts/offline/run_experiment_suite.py`)

-   **설명**: offline 실험을 one-command로 돌리기 위한 thin orchestrator입니다. oracle reference preflight, offline batch, 결과 분석을 순서대로 호출합니다.
-   **지원 suite**:
    -   `scalability`: beam/lookahead와 monitoring on/off의 효과를 비교합니다.
    -   `eta_sensitivity`: Bayesian monitoring에서 `eta` 민감도를 비교합니다.
    -   `monitoring_budget`: critical interval당 monitoring 횟수 cap(`1`, `2`, `3`, `uncap`)을 비교합니다.
    -   `pf_vs_bayesian`: non-Gaussian GT에서 Bayesian vs Particle Filter를 비교합니다.
    -   `all`: `scalability -> eta_sensitivity -> monitoring_budget -> pf_vs_bayesian` 순서로 모두 실행합니다.
-   **기본 동작**: suite마다 oracle reference preflight(`skip-completed`) → `run_batch.py` → 끝나면 `offline_comparison.py` 호출. 동일 단계는 `run_oracle_reference_batch.py` / `run_batch.py` / `offline_comparison.py`로 단독 실행도 가능합니다.

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

#### 설정 파일 (`scripts/offline/`)

`scalability_config.yaml`, `eta_sensitivity_config.yaml`, `monitoring_budget_config.yaml`, `oracle_reference_config.yaml`, `pf_vs_bayesian_<gt>_<belief>_config.yaml` 패턴 등. 출력 경로만 바꿔 oracle을 다시 뽑을 때는 `oracle_reference_regen_config.yaml`처럼 `oracle_reference_dir`만 조정한 복제본을 쓰면 됩니다.

#### Suite 한 줄 요약

스윕 범위·prior는 **각 YAML**이 정본입니다. 개념만 보면: **`scalability`**는 베이지안(beam·`NONE_MONITORING` 등) + EDF/CPM 비교 한 점, **`eta_sensitivity`**는 베이지안·prior·η, **`monitoring_budget`** / **`pf_vs_bayesian`**는 이름 그대로. 배치에서 beam·ablation을 어떻게 적용하는지는 **6. 오프라인 batch** 절을 보면 됩니다.

### 5. 오프라인 oracle reference 생성 (`scripts/offline/run_oracle_reference_batch.py`)

Deterministic oracle reference를 먼저 만들고 배치 결과와 비교합니다.

-   **설정**: `scripts/offline/oracle_reference_config.yaml` (기본 `assets/results/offline_oracle_reference/…`)
-   **명령어**:
    ```bash
    cd scripts/offline && python run_oracle_reference_batch.py --config oracle_reference_config.yaml
    python scripts/offline/run_oracle_reference_batch.py --config scripts/offline/oracle_reference_config.yaml
    ```
-   **출력**: `…/offline_oracle_reference/<task_folder>/<scene>/<case>/<instruction>.json`, 요약은 `_batch_summary/`.
-   **배치와의 관계**: oracle 쪽은 harness에서 **GT `constant` 고정**의 결정적 값. 배치는 suite YAML의 **`gt_seed` / `gt_distribution`**을 따르므로, 비교 시 시드·분포를 맞출지 스스로 정하면 됩니다. `offline_comparison`의 **`makespan_gap`**은 배치 makespan − oracle **`optimal_schedule_time`**.

### 6. 오프라인 batch 실행 (`scripts/offline/run_batch.py`)

YAML을 읽어 일괄 실행합니다 (`run_experiment_suite.py` 없이도 동일 config로 가능).

```bash
cd scripts/offline && python run_batch.py --config scalability_config.yaml
python scripts/offline/run_batch.py --config scripts/offline/scalability_config.yaml
```

-   **규칙 요약** (`batch_runner.py`): **`beam_bound`·`ablation_configs`·(일부) monitoring cap 전체 스윕은 베이지안만.** EDF/CPM은 beam 미사용, YAML의 ablation 목록과 무관하게 **`DEFAULT` 한 번**, 산출물은 `edf.json` / `cpm.json`.
-   **YAML에서 자주 보는 키**: `belief_update_method`, `gt_distribution`, `particle_distribution`, `factor_alpha`, `max_monitoring_per_critical_intervals` 등(타입·허용값은 코드·샘플 YAML 참고).

#### 결과 경로

`assets/results/offline_exp_result/<suite_dir>/<task_folder>/<init_prior>/…/<baseline>/<파일>.json` — 로그는 `logs/<run_timestamp>/…`, 요약은 `<suite_dir>/_batch_summary/`. 대부분 suite는 prior가 `CORRECT_ESTIMATE/` 한 종류이고, **`eta_sensitivity`** 만 `init_prior_configs`에 따라 prior 폴더가 여러 개 생깁니다. 베이지안 파일명에 beam·η·GT 등이 붙고, EDF/CPM은 위와 같이 고정 파일명입니다.

### 7. 결과 비교 분석 (`assets/result_analysis/offline_comparison.py`)

`offline_comparison_raw.json`, `offline_analysis_summary.json`, `offline_analysis_tol_sweep.json` 세 종류를 만듭니다. summary·tol_sweep 셀에는 평균에 쓰인 행 수인 **`n_instructions`**가 들어갑니다.

```bash
python -m assets.result_analysis.offline_comparison \
  --base_dir assets/results \
  --batch_dirname offline_exp_result/offline_batch_pf_vs_bayesian \
  --oracle_dirname offline_oracle_reference \
  --task_folder sampled_10_instruction_set_for_final_experiment_251203 \
  --tolerance-sweep 5.0 8.0 12.5 15.0
```

`--batch_dirname`, `--oracle_dirname`, `--task_folder`, `--skip_oracle_violated`, `--tolerance-sweep` 등은 `python -m assets.result_analysis.offline_comparison --help` 참고. 집계 단위는 **`approach_key` × case**이고, 키는 run `meta_data`에서 유도됩니다. **한 instruction 폴더에 예전 설정 JSON이 남아 있으면** 키가 섞여 평균이 오염될 수 있으니, 설정 변경 후에는 오래된 파일을 정리한 뒤 돌리는 것이 안전합니다.

### 8. Scheduler-Free Belief Robustness Benchmark (`scripts/offline/belief_distribution_benchmark.py`)

PF와 Bayesian belief update 자체를 **scheduler 없이** 비교할 때 쓰는 Monte Carlo 벤치마크입니다. GT 분포, GT mean shift, prior mismatch, observation family를 바꿔가며 `late_trigger_rate`, `calibration_error`, `trigger_abs_error` 등을 직접 비교합니다.

-   **기본 용도**: 탐색형 범용 benchmark
-   **Reviewer 10 대응용 용도**: `--preset reviewer10`으로 고정된 revision 설정 + reviewer용 CSV + LaTeX table 생성

#### 일반 실행 예시

```bash
python scripts/offline/belief_distribution_benchmark.py \
  --output-dir assets/results/offline_exp_result/belief_distribution_benchmark \
  --episodes 200 \
  --gt-distributions gaussian lognormal mixture \
  --gt-mean-multipliers 1.0 \
  --prior-configs UNDER_ESTIMATE CORRECT_ESTIMATE OVER_ESTIMATE \
  --etas 0.1 \
  --observation-families gaussian same_as_gt \
  --pf-particle-distributions gaussian
```

-   `--gt-variance`를 **생략**하면 family-specific GT variance preset을 사용합니다.
    -   `gaussian`: 대략 `mean=100, std=30`
    -   `lognormal`, `mixture`: 더 넓은 stress preset
-   `--gt-mean-multipliers`는 `base_duration`에 곱해 GT mean을 만듭니다.
    -   예: `base_duration=100`, `--gt-mean-multipliers 0.6 1.0 1.4`면 GT mean이 `60 / 100 / 140`

#### Reviewer 10 preset 예시

```bash
python scripts/offline/belief_distribution_benchmark.py \
  --preset reviewer10 \
  --output-dir assets/results/offline_exp_result/belief_reviewer10_comparison \
  --episodes 200 \
  --no-episode-csv
```

이 preset은 내부적으로 다음을 고정합니다.

-   `gt_distributions = gaussian, lognormal, mixture`
-   `gt_mean_multipliers = 0.6, 1.0, 1.4`
-   `prior_configs = UNDER_ESTIMATE, CORRECT_ESTIMATE, OVER_ESTIMATE`
-   `eta = 0.1`
-   `observation_families = gaussian, same_as_gt`
-   `pf-particle-distributions = gaussian`
-   reviewer용 CSV 출력 + LaTeX table 생성

주요 산출물:

-   `belief_benchmark_summary.json`, `belief_benchmark_summary.csv`
-   `belief_reviewer10_main_shared_gaussian.csv`
-   `belief_reviewer10_main_same_as_gt.csv`
-   `belief_reviewer10_pf_likelihood_upgrade.csv`
-   `latex_tables/tab_belief_robustness_main_shared_gaussian.tex`
-   `latex_tables/tab_belief_robustness_main_same_as_gt.tex`

#### 구 스크립트 호환성

`scripts/offline/reviewer10_belief_comparison.py`는 기존 명령을 깨지 않게 남겨둔 **호환 래퍼**입니다. 새 실험은 가능하면 `belief_distribution_benchmark.py --preset reviewer10` 기준으로 실행하는 것을 권장합니다.

### 9. 캐시·해석

-   `nav_graph_source: ai2thor_controller`이면 `assets/cache/ai2thor_nav_graphs/<scene>.json`을 우선 사용해 THOR 기동 비용을 줄입니다.
-   Offline은 **planner-level** 비교용입니다. `simulation makespan`은 실제 THOR 실행에 따라 달라질 수 있고, EDF/CPM도 동일합니다.
