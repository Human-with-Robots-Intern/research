# AI2-THOR Task Scheduling Research Framework

This repository provides a task scheduling and execution framework for household tasks in the AI2-THOR simulation environment. It includes a dynamic scheduler that updates task-duration estimates during execution, several comparison baselines, and monitoring backends based on Gaussian Bayesian approximation and particle filtering.

## Project Structure

The main source code is organized under `src/`.

-   `dag_bayesian.py`: Entry point for the proposed DAG-Bayesian scheduling algorithm. It combines dynamic planning, execution monitoring, Bayesian duration estimation, and posterior updates.
-   **`core/`**: Core logic for the main scheduler.
    -   `scheduler.py`: Search-based scheduler that selects the next action.
    -   `agent.py`: Agent model that maintains duration beliefs and updates posteriors after monitoring observations.
    -   `monitoring.py`: Bayesian and particle-filter belief updates, ground-truth sampling, observation models, and monitoring trigger policies.
-   **`scheduler/`**: Supporting modules for scheduling.
    -   `action_handler.py`: Executes primitive actions in the simulator and predicts action durations.
    -   `constraint_handler.py`: Manages temporal constraints and dependencies between tasks.
    -   `heuristic_manager.py`: Computes heuristic costs used to guide scheduler search.
-   **`baselines/`**: Baseline scheduling and planning methods used for comparison.
    -   `cpm.py`: Critical Path Method (CPM) scheduler.
    -   `edf/`: Earliest Deadline First (EDF) scheduler.
    -   `cap/`: Code as Policies baseline that converts natural-language instructions into executable Python code.
    -   `progprompt/`: ProgPrompt baseline that generates Python-like plans from natural-language instructions.
-   **`models/`**: Shared data structures for tasks, states, and results.
    -   `task.py`: Defines classes such as `Task` and `Subtask`.
    -   `dataclass.py`: Defines state containers such as `SchedulerState` and `SimulationNode`.
-   **`simulation/`**: Interfaces with the AI2-THOR simulator.
    -   `runner_ai2thor.py`: Initializes simulator controllers and runs tasks.
-   **`experiments/`**: Offline experiment and analysis runners.
    -   `offline_harness.py`: In-process offline experiment harness for DAG-Bayesian, EDF, and CPM with a shared result schema.
    -   `exact_oracle.py`: Exhaustive oracle baseline for small deterministic settings.
-   **`utils/`**: General utilities for I/O, logging, NLP, visualization, and related tasks.
-   `tune.py`: Hyperparameter tuning script using `Optuna`.

## Running Experiments

Each algorithm can be run directly as a Python script. Full experiment batches can also be launched through YAML-driven runners, including the full AI2-THOR batch runner and the offline suite scripts.

-   **Recommended environment**: The examples below assume that the project Python environment is active, for example:

    ```bash
    conda activate research
    ```

### 1. Running Individual Algorithms

#### DAG-Bayesian, CPM, and EDF

-   **Description**: `dag_bayesian.py`, `baselines/cpm.py`, and `baselines/edf/dag_edf.py` display the available tasks under `assets/tasks` and prompt the user to select a task at runtime.
-   **Command**:

    ```bash
    # Example: run the CPM baseline
    python src/baselines/cpm.py --scene FloorPlan1
    ```

-   **Arguments**:
    -   `--scene`: Simulation scene name, such as `FloorPlan1` or `FloorPlan422`.

#### CAP and ProgPrompt

-   **Description**: The Code as Policies and ProgPrompt baselines take the target task directly as a natural-language instruction.
-   **Command**:

    ```bash
    # Example: run the CAP baseline
    python src/baselines/cap/cap_ai2thor.py --instruction "make a coffee and toast a bread"
    ```

-   **Arguments**:
    -   `--instruction`: Natural-language instruction to be converted into a plan.
-   **Note**: These LLM-based baselines require the `OPENAI_API_KEY` environment variable.

### 2. Full AI2-THOR Batch Runner

-   **Description**: Batch runner for executing multiple algorithm, scene, and task combinations in AI2-THOR. Experiment targets and scene lists are configured through YAML; the CLI mainly selects the config path and dry-run behavior.
-   **Config file**: `scripts/run_all_config.yaml` by default. Edit fields such as `scene_type`, `scene_lists`, `approaches`, `llm_scripts`, `task_folder_name`, `ablation_configs`, and `init_prior_configs` in this file.
-   **Main behavior**:
    -   Reads scenes from `scene_lists` according to `scene_type`.
    -   Executes scheduler script paths listed in `approaches` as subprocesses.
    -   Applies retry logic to baselines listed in `llm_scripts`.
-   **Commands** from the repository root. Replace `<batch_runner>` with the anonymized batch-runner script name used in the released artifact:

    ```bash
    python scripts/<batch_runner>.py
    python scripts/<batch_runner>.py --config run_all_config.yaml --dry-run
    ```

-   **CLI arguments**:
    -   `--config`: YAML config path. Relative paths are resolved from the `scripts/` directory.
    -   `--dry-run`: Print the experiment list without launching the runs.
    -   `--skip-completed`: Skip tasks whose result JSON already exists. This flag matches the default skip-completed behavior.

### 3. Offline Single Run (`scripts/offline/offline_experiment.py`)

-   **Description**: Offline runner for quickly comparing planner-level schedules and temporal-constraint behavior without launching a full AI2-THOR simulation each time.
-   **Supported approaches**:
    -   `bayesian`: Offline rollout of the proposed method.
    -   `edf`: EDF baseline adapter.
    -   `cpm`: CPM baseline adapter.
-   **Main features**:
    -   Saves all approaches with the same single-run result schema.
    -   Switches between `bayesian` and `particle_filter` through `belief_update_method`.
    -   Supports runtime ground-truth duration distributions through `gt_distribution`: `constant`, `gaussian`, `lognormal`, `gamma`, or `mixture`.
    -   Uses the current `gt_distribution` as the default `particle_distribution` for particle-filter runs if no particle distribution is specified.
    -   Adds oracle comparison fields to result JSON files when `oracle_reference_dir` is provided.
    -   Uses cache-first behavior for `nav_graph_source: ai2thor_controller`; the AI2-THOR controller is launched only when the cache is missing.
    -   Supports `max_monitoring_per_critical_interval` to cap the number of monitoring actions per critical interval. If omitted, monitoring is uncapped.

#### Single-Run Example

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

#### Particle-Filter Single-Run Example

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

#### Compare Two Result Files

```bash
python scripts/offline/offline_experiment.py compare \
  --before assets/results/before.json \
  --after assets/results/after.json \
  --output-path assets/results/offline_compare.json
```

#### Main Arguments

-   `--approach`: One of `bayesian`, `edf`, or `cpm`.
-   `--ablation-config`: Mainly used for `bayesian` in the current offline batch setup.
-   `--init-prior-config`: Common values include `UNDER_ESTIMATE`, `CORRECT_ESTIMATE`, and `OVER_ESTIMATE`.
-   `--beam-bound`: Beam width and depth pair, such as `10,10`.
-   `--belief-update-method`: Either `bayesian` or `particle_filter`.
-   `--gt-distribution`: Runtime ground-truth duration distribution used by monitoring.
-   `--particle-distribution`: Particle initialization distribution for particle-filter runs. If omitted, particle-filter runs use `gt_distribution`, while non-particle-filter runs use `gaussian`.
-   `--eta`: Risk tolerance for the monitoring trigger.
-   `--max-monitoring-per-critical-interval`: Maximum number of monitoring actions per critical interval. If omitted, monitoring is uncapped.
-   `--gt-seed`: Seed used for ground-truth sampling, the observation model, and particle-filter initialization/resampling.
-   `--case`, `--cases`: Select one case or multiple cases.
-   `--instruction`, `--instructions`: Select one or more instruction files.
-   `--nav-graph-source`: Either `synthetic_grid` or `ai2thor_controller`.
-   `--oracle-reference-dir`: Root directory containing precomputed oracle-reference JSON files.
-   `--output-path`: Output path for the JSON report.

### 4. Offline Suite Runner (`scripts/offline/run_experiment_suite.py`)

-   **Description**: Thin one-command orchestrator for offline experiments. It runs oracle-reference preflight, offline batch execution, and result analysis in sequence.
-   **Supported suites**:
    -   `scalability`: Compares beam/lookahead settings and monitoring on/off behavior.
    -   `eta_sensitivity`: Compares different `eta` values for Bayesian monitoring.
    -   `monitoring_budget`: Compares monitoring caps per critical interval (`1`, `2`, `3`, and `uncap`).
    -   `pf_vs_bayesian`: Compares Bayesian and particle-filter updates under non-Gaussian ground-truth distributions.
    -   `all`: Runs `scalability -> eta_sensitivity -> monitoring_budget -> pf_vs_bayesian`.
-   **Default behavior**:
    -   Runs oracle-reference preflight before each suite.
    -   Uses skip-completed semantics for oracle preflight.
    -   Runs `offline_comparison.py` automatically after each suite.
    -   Keeps lower-level scripts such as `run_oracle_reference_batch.py`, `run_batch.py`, and `offline_comparison.py` unchanged.

#### Recommended Commands

```bash
python scripts/offline/run_experiment_suite.py --suite scalability
python scripts/offline/run_experiment_suite.py --suite eta_sensitivity
python scripts/offline/run_experiment_suite.py --suite monitoring_budget
python scripts/offline/run_experiment_suite.py --suite pf_vs_bayesian
python scripts/offline/run_experiment_suite.py --suite all
```

#### Dry-Run Example

```bash
python scripts/offline/run_experiment_suite.py --suite monitoring_budget --dry-run
```

#### Suite Config Files

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

#### Current Suite Design

-   `scalability`
    -   approaches: `bayesian`, `edf`, `cpm`
    -   ablation: `DEFAULT`, `NONE_MONITORING`
    -   ground truth: `constant`
    -   prior: `CORRECT_ESTIMATE`
    -   beam: `[1,1]`, `[5,5]`, `[10,10]`, `[20,20]`
-   `eta_sensitivity`
    -   approach: `bayesian`
    -   ablation: `DEFAULT`
    -   ground truth: `constant`
    -   prior: `CORRECT_ESTIMATE`
    -   beam: `[1,1]`, `[5,5]`, `[10,10]`, `[20,20]`
    -   eta: `0.01`, `0.1`, `0.5`, `0.9`
-   `monitoring_budget`
    -   approach: `bayesian`
    -   ablation: `DEFAULT`
    -   ground truth: `gaussian`
    -   prior: `CORRECT_ESTIMATE`
    -   beam: `[10,10]`
    -   eta: `0.1`
    -   monitoring budget: `1`, `2`, `3`, `uncap`
-   `pf_vs_bayesian`
    -   approach: `bayesian`
    -   ablation: `DEFAULT`
    -   ground truth: `constant`, `gaussian`, `lognormal`, `mixture`
    -   belief update: `bayesian` vs. `particle_filter`
    -   prior: `UNDER_ESTIMATE`, `CORRECT_ESTIMATE`, `OVER_ESTIMATE`

### 5. Offline Oracle Reference Generation (`scripts/offline/run_oracle_reference_batch.py`)

-   **Description**: Generates deterministic oracle references in a separate precomputation step instead of storing the oracle as another batch baseline. Later baseline results are compared against these references.
-   **Config file**: `scripts/offline/oracle_reference_config.yaml`
-   **Commands**:

    ```bash
    cd scripts/offline && python run_oracle_reference_batch.py --config oracle_reference_config.yaml
    python scripts/offline/run_oracle_reference_batch.py --config scripts/offline/oracle_reference_config.yaml
    ```

-   **Output paths**:
    -   Single-run oracle reference:
        `assets/results/offline_oracle_reference/<task_folder>/<scene>/<case>/<instruction>.json`
    -   Batch summary:
        `assets/results/offline_oracle_reference/_batch_summary/offline_oracle_reference_<timestamp>.json`

### 6. Offline Batch Runner (`scripts/offline/run_batch.py`)

-   **Description**: Reads a YAML config and runs offline experiments in batch mode. This script can be used directly when only a specific config needs to be executed without `run_experiment_suite.py`.
-   **Commands**:

    ```bash
    # From scripts/offline, pass only the file name
    cd scripts/offline && python run_batch.py --config batch_config.yaml

    # From the repository root, pass a repo-relative path
    python scripts/offline/run_batch.py --config scripts/offline/scalability_config.yaml
    ```

-   **Common config files**:
    -   `scripts/offline/scalability_config.yaml`
    -   `scripts/offline/eta_sensitivity_config.yaml`
    -   `scripts/offline/monitoring_budget_config.yaml`
    -   `scripts/offline/pf_vs_bayesian_*_config.yaml`
-   **Current batch rules**:
    -   Only `bayesian` is swept over `beam_bound` and `ablation_configs`.
    -   `edf` and `cpm` run only once with `DEFAULT`.
    -   As a result, `edf` and `cpm` do not produce `NONE_MONITORING` result files.
    -   `max_monitoring_per_critical_intervals` is meaningful only for the `bayesian + DEFAULT` variant.
-   **Additional batch config keys**:
    -   `belief_update_method`: `bayesian` or `particle_filter`.
    -   `gt_distribution`: `constant`, `gaussian`, `lognormal`, `gamma`, or `mixture`.
    -   `particle_distribution`: Particle initialization distribution for particle-filter runs.
    -   `factor_alpha`: Override for the synthetic Gaussian observation variance factor.
    -   `max_monitoring_per_critical_intervals`: List of monitoring caps per critical interval.

#### Result Directory Layout

-   Result JSON:
    `assets/results/offline_exp_result/<suite_dir>/<task_folder>/<init_prior>/<scene>/<case>/<instruction_stem>/<baseline>/<file>.json`
-   Worker log:
    `logs/<run_timestamp>/<suite_name>/<task_folder>/<init_prior>/<scene>/<case>/<instruction_stem>/<baseline>/<file>.log`
-   Batch summary:
    `assets/results/offline_exp_result/<suite_dir>/_batch_summary/<suite_name>_<timestamp>.json`

`init_prior` is kept as a common top-level folder across all suites. Therefore, `scalability`, `eta_sensitivity`, and `monitoring_budget` also explicitly contain a `CORRECT_ESTIMATE/` folder.

#### File-Naming Rules

-   `bayesian`: `DEFAULT__w10_d10[__eta0.1][__gtgaussian][__mb2].json`
-   `particle_filter`: `DEFAULT__w10_d10[__eta0.1]__gtlognormal[__pdistlognormal][__mb2].json`
-   `edf`: `edf.json`
-   `cpm`: `cpm.json`

The baseline name is represented by the parent baseline directory, not by the file name alone.

#### PF-vs-Bayesian Batch Examples

```bash
python scripts/offline/run_batch.py \
  --config scripts/offline/pf_vs_bayesian_lognormal_particle_filter_config.yaml

python scripts/offline/run_batch.py \
  --config scripts/offline/pf_vs_bayesian_lognormal_bayesian_config.yaml
```

### 7. Result Comparison and Analysis (`assets/result_analysis/offline_comparison.py`)

-   **Description**: Compares oracle references with batch results for each approach and produces three output files.
    1.  `offline_comparison_raw.json`: Oracle fields and approach-level makespan/computation-time gaps for each scene, case, and instruction.
    2.  `offline_analysis_summary.json`: Aggregated metrics grouped by approach and case.
    3.  `offline_analysis_tol_sweep.json`: TCSR recomputed across tolerances from stored `detail_log` entries.
-   **Command**:

    ```bash
    python -m assets.result_analysis.offline_comparison \
      --base_dir assets/results \
      --batch_dirname offline_exp_result/offline_batch_pf_vs_bayesian \
      --oracle_dirname offline_oracle_reference \
      --task_folder sampled_10_instruction_set_for_final_experiment_251203 \
      --tolerance-sweep 5.0 8.0 12.5 15.0
    ```

-   **Main arguments**:
    -   `--base_dir`: Path containing the oracle and batch result roots.
    -   `--batch_dirname`: Batch result directory name, such as `offline_exp_result/offline_batch_scalability`.
    -   `--oracle_dirname`: Oracle-reference directory name. The default is `offline_oracle_reference`.
    -   `--task_folder`: Task folder under the oracle-reference and batch result directories.
    -   `--skip_oracle_violated`: Exclude instructions whose oracle schedule violates constraints.
    -   `--tolerance-sweep`: Recompute TCSR for different tolerances from stored `detail_log` entries without rerunning the scheduler.
-   **Output path**: Results are written under `--base_dir` or `--output_dir`.

#### Reading `offline_analysis_summary.json`

The aggregation unit is **approach_key x case**. For a given `case`, the mean includes all scenes and instructions under that case.

-   **Approach-key construction**:
    -   Keys are generated from `meta_data` when possible.
    -   Keys include `init_prior_config`, `baseline_name`, `ablation_config`, `beam_width`, `beam_depth`, `eta`, `gt_distribution`, `particle_distribution`, and `monitoring_budget_per_critical`.
    -   Examples:
        -   `CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1`
        -   `UNDER_ESTIMATE__particle_filter__DEFAULT__w10_d10__eta0.1__gtlognormal`
        -   `CORRECT_ESTIMATE__bayesian__DEFAULT__w10_d10__eta0.1__gtgaussian__mb2`
-   **Second key**: Case folder name, such as `tasks_2_constraints_2`.
-   **Metric object**: The following fields are reported for each `(approach_key, case)` cell.

| Field | Meaning |
|------|---------|
| `sr` | Success rate (%) |
| `tsr` | Mean schedule TCSR (%) |
| `makespan` | Mean planner makespan in seconds |
| `makespan_sr_1` | Mean makespan over completed instructions only |
| `makespan_gap` | Mean `(scheduler_makespan - oracle optimal_schedule_time)` |
| `makespan_gap_sr_1` | Makespan gap over completed instructions only |
| `computation_time` | Mean planner computation time in seconds |
| `computation_time_gap` | Mean `(batch computation_time - oracle computation_time)` |

When `--skip_oracle_violated` is enabled, instructions whose oracle JSON violates constraints are excluded from aggregation. `--tolerance-sweep` performs post-hoc rescoring only; it does not regenerate scheduler actions or makespans.

### 8. Navigation Graph Cache

-   With `nav_graph_source: ai2thor_controller`, navigation graphs are cached under `assets/cache/ai2thor_nav_graphs/<scene>.json`.
-   If a cache file exists, offline runs use it first. The controller is initialized only when the cache is missing.
-   This substantially reduces AI2-THOR initialization overhead for repeated offline experiments on the same scene.

### 9. Notes on Interpreting Results

-   The offline harness is designed for fast planner-level comparisons.
-   Even when `offline makespan == scheduler makespan`, `simulation makespan` may differ slightly because it depends on the actual primitive-action execution results in AI2-THOR.
-   EDF and CPM baselines can also be aligned between offline runs and AI2-THOR planner-level schedules, but their actual simulation times may not be exactly identical.
