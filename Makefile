SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
PROJECT_ROOT ?= $(CURDIR)
ARENA_WS ?= $(HOME)/arena5_ws
CONDA_ENV_NAME ?= ramp-offline
SEED ?= 0
BOOTSTRAP_SEED ?= 20260804
HEADLESS ?= 1
CONFIG ?=
EXPERT_RAW ?= data/raw/temporary_blockage_high_train_s01720_finite2_heuristic_dwb.jsonl
EXPERT_DATASET ?= data/interim/temporary_blockage_finite2_expert_smoke.h5
BC_CONFIG ?= configs/imitation/bc_smoke.yaml
BC_OUTPUT ?= checkpoints/bc/smoke
DAGGER_ITERATION ?= 1
DAGGER_BASE_DATASETS ?= data/interim/temporary_blockage_finite2_expert_smoke.h5 data/interim/temporary_blockage_medium_train_expert.h5 data/interim/temporary_blockage_low_train_expert.h5 data/interim/doorway_high_train_expert.h5 data/interim/blind_corner_high_train_expert.h5 data/interim/group_blocking_high_train_expert.h5
DAGGER_SHARDS ?= data/interim/dagger_iter1_temporary_blockage_high_train.h5 data/interim/dagger_iter1_crossing_flow_high_train.h5 data/interim/dagger_iter1_crossing_flow_s01260_train.h5 data/interim/dagger_iter1_crossing_flow_s01291_train.h5 data/interim/dagger_iter1_crossing_flow_s01318_train.h5
DAGGER_VALIDATION ?= data/interim/temporary_blockage_validation_expert.h5
DAGGER_CONFIG ?= configs/imitation/bc_uniform_scenario.yaml
LOG_DIR ?= $(PROJECT_ROOT)/outputs/logs
MODERATE_ANALYSIS_DIR ?= outputs/moderate/final
MODERATE_RESULTS ?= $(MODERATE_ANALYSIS_DIR)/results.parquet
MODERATE_SUMMARY ?= $(MODERATE_ANALYSIS_DIR)/summary.csv
MODERATE_STATISTICS ?= $(MODERATE_ANALYSIS_DIR)/pairwise_statistics.json
MODERATE_EXPECTED_CONDITIONS ?= 120
MODERATE_BENCHMARK_CONFIG ?= configs/experiments/scenario_catalog_moderate_v5.yaml
MODERATE_SPLIT_MANIFEST ?= scenarios/splits/moderate_v5_test.yaml
MODERATE_CALIBRATION_REPORT ?= outputs/moderate/v5_validation/calibration_report.json
MODERATE_METHODS ?= base standard heuristic bc_uniform pgrr
MODERATE_MAIN_METHOD ?= pgrr
MODERATE_REFERENCE_METHOD ?= base
EVALUATION_JOBS ?= 6
EVALUATION_TIMEOUT_S ?= 240
OFFLINE_RUN := env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH -u CMAKE_PREFIX_PATH -u ROS_DISTRO -u ROS_VERSION -u ROS_PYTHON_VERSION conda run -n "$(CONDA_ENV_NAME)"

.DEFAULT_GOAL := help

.PHONY: help preflight conda arena build test smoke baseline scenarios mine-failures label-expert train-bc train-dagger train-ppo-smoke train-ppo train-detector pilot evaluate-flatland evaluate-gazebo statistics method-figures figures tables moderate-figures moderate-tables paper reproduce-small reproduce-paper privacy-check student-branch

help: ## Show available targets.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "%-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(LOG_DIR):
	@mkdir -p "$@"

preflight: | $(LOG_DIR) ## Capture a non-mutating host environment report.
	@PROJECT_ROOT="$(PROJECT_ROOT)" ARENA_WS="$(ARENA_WS)" scripts/bootstrap/preflight.sh 2>&1 | tee "$(LOG_DIR)/preflight.log"

conda: | $(LOG_DIR) ## Create/update the isolated offline environment and lock it.
	@PROJECT_ROOT="$(PROJECT_ROOT)" CONDA_ENV_NAME="$(CONDA_ENV_NAME)" scripts/bootstrap/create_offline.sh 2>&1 | tee "$(LOG_DIR)/conda.log"

arena: | $(LOG_DIR) ## Discover or install the pinned Arena runtime without Conda.
	@PROJECT_ROOT="$(PROJECT_ROOT)" ARENA_WS="$(ARENA_WS)" scripts/bootstrap/install_arena.sh 2>&1 | tee "$(LOG_DIR)/arena_install.log"

build: | $(LOG_DIR) ## Build Python and ROS2 packages.
	@scripts/bootstrap/build_overlay.sh 2>&1 | tee "$(LOG_DIR)/build.log"

test: | $(LOG_DIR) ## Run offline lint, type, and unit tests.
	@$(OFFLINE_RUN) ruff check . 2>&1 | tee "$(LOG_DIR)/ruff.log"
	@$(OFFLINE_RUN) ruff format --check . 2>&1 | tee "$(LOG_DIR)/ruff-format.log"
	@$(OFFLINE_RUN) mypy packages/ramp_core packages/ramp_ml 2>&1 | tee "$(LOG_DIR)/mypy.log"
	@$(OFFLINE_RUN) pytest -q 2>&1 | tee "$(LOG_DIR)/pytest.log"

smoke: | $(LOG_DIR) ## Run the Arena headless smoke test.
	@SEED="$(SEED)" HEADLESS="$(HEADLESS)" scripts/arena/smoke_arena.sh 2>&1 | tee "$(LOG_DIR)/arena_smoke.log"

baseline: ## Run baseline episodes (implemented after Gate 0).
	@scripts/evaluate/run_baseline.sh --seed "$(SEED)" $(if $(CONFIG),--config "$(CONFIG)")
scenarios: | $(LOG_DIR) ## Compile deterministic scenarios and validate them with Arena's parser.
	@$(OFFLINE_RUN) python scripts/data/compile_scenarios.py --seed "$(SEED)" 2>&1 | tee "$(LOG_DIR)/scenarios.log"
	@env -u CONDA_PREFIX -u VIRTUAL_ENV PROJECT_ROOT="$(PROJECT_ROOT)" scripts/arena/validate_scenarios.sh 2>&1 | tee "$(LOG_DIR)/scenario_validation.log"
mine-failures: ## Mine reproducible planner failures.
	@SEED_START="$(SEED)" CONDA_ENV_NAME="$(CONDA_ENV_NAME)" scripts/evaluate/mine_failures.sh
label-expert: ## Label recovery states using the privileged expert.
	@$(OFFLINE_RUN) python scripts/data/label_expert.py "$(EXPERT_RAW)" \
		--output "$(EXPERT_DATASET)" \
		--summary data/manifests/temporary_blockage_finite2_expert_smoke_summary.json
train-bc: ## Train behavior cloning policies.
	@$(OFFLINE_RUN) python scripts/train/train_bc.py "$(EXPERT_DATASET)" \
		--config "$(BC_CONFIG)" --output "$(BC_OUTPUT)"
train-dagger: ## Aggregate and train one configured DAgger round.
	@$(OFFLINE_RUN) python scripts/train/train_dagger.py \
		--iteration "$(DAGGER_ITERATION)" --base-datasets $(DAGGER_BASE_DATASETS) \
		--dagger-shards $(DAGGER_SHARDS) --validation-dataset "$(DAGGER_VALIDATION)" \
		--config "$(DAGGER_CONFIG)"
train-ppo-smoke: ## Run a small action-masked PPO smoke job.
	@$(OFFLINE_RUN) python scripts/train/train_ppo.py --profile smoke --seed "$(SEED)"
train-ppo: ## Run configured PPO training.
	@$(OFFLINE_RUN) python scripts/train/train_ppo.py --profile main --seed "$(SEED)"
train-detector: ## Train the optional learned failure detector.
	@$(OFFLINE_RUN) python scripts/train/train_detector.py --seed "$(SEED)"
pilot: ## Run validation-only pilot evaluation.
	@scripts/evaluate/run_experiment.sh --tier pilot --seed "$(SEED)"
evaluate-flatland: ## Run the locked five-method moderate-v5 test manifest (legacy target name).
	@$(OFFLINE_RUN) python scripts/evaluate/run_experiment.py \
		--split test --split-manifest "$(MODERATE_SPLIT_MANIFEST)" \
		--methods $(MODERATE_METHODS) --jobs "$(EVALUATION_JOBS)" \
		--timeout "$(EVALUATION_TIMEOUT_S)" \
		--output-dir "$(MODERATE_ANALYSIS_DIR)"
evaluate-gazebo: ## Run the optional Gazebo transfer validation.
	@scripts/evaluate/run_experiment.sh --tier gazebo --simulator gazebo
statistics: ## Collect and summarize the complete five-method moderate benchmark.
	@$(OFFLINE_RUN) python scripts/evaluate/collect_results.py \
		--manifest "$(MODERATE_ANALYSIS_DIR)/episode_manifest.parquet" \
		--run-manifest "$(MODERATE_ANALYSIS_DIR)/run_manifest.json" \
		--raw-dir data/raw \
		--results "$(MODERATE_RESULTS)" \
		--summary "$(MODERATE_ANALYSIS_DIR)/collector_summary.csv" \
		--statistics "$(MODERATE_ANALYSIS_DIR)/collector_statistics.json" \
		--reference-policy "$(MODERATE_REFERENCE_METHOD)" \
		--treatment-policy "$(MODERATE_MAIN_METHOD)" \
		--bootstrap-samples 10000 --bootstrap-seed "$(BOOTSTRAP_SEED)"
	@$(OFFLINE_RUN) python scripts/evaluate/summarize_moderate.py \
		--results "$(MODERATE_RESULTS)" --output-dir "$(MODERATE_ANALYSIS_DIR)" \
		--methods $(MODERATE_METHODS) \
		--main-method "$(MODERATE_MAIN_METHOD)" \
		--reference-method "$(MODERATE_REFERENCE_METHOD)" \
		--bootstrap-samples 10000 --bootstrap-seed "$(BOOTSTRAP_SEED)"
moderate-figures: statistics ## Generate five-method moderate benchmark vector figures.
	@$(OFFLINE_RUN) python scripts/paper/make_moderate_figures.py \
		--results "$(MODERATE_RESULTS)" --summary "$(MODERATE_SUMMARY)" \
		--statistics "$(MODERATE_STATISTICS)" \
		--expected-condition-count "$(MODERATE_EXPECTED_CONDITIONS)" \
		--output-dir paper/figures
	@$(OFFLINE_RUN) python scripts/paper/make_moderate_figures.py \
		--results "$(MODERATE_RESULTS)" --summary "$(MODERATE_SUMMARY)" \
		--statistics "$(MODERATE_STATISTICS)" \
		--expected-condition-count "$(MODERATE_EXPECTED_CONDITIONS)" \
		--output-dir outputs/figures
method-figures: ## Generate result-independent closed-loop and expert figures.
	@$(OFFLINE_RUN) python scripts/paper/make_method_figures.py --output-dir paper/figures
	@$(OFFLINE_RUN) python scripts/paper/make_method_figures.py --output-dir outputs/figures
moderate-tables: statistics ## Generate five-method moderate benchmark LaTeX tables.
	@$(OFFLINE_RUN) python scripts/paper/make_moderate_tables.py \
		--results "$(MODERATE_RESULTS)" --summary "$(MODERATE_SUMMARY)" \
		--statistics "$(MODERATE_STATISTICS)" \
		--expected-condition-count "$(MODERATE_EXPECTED_CONDITIONS)" \
		--output-dir paper/generated
	@$(OFFLINE_RUN) python scripts/paper/make_moderate_tables.py \
		--results "$(MODERATE_RESULTS)" --summary "$(MODERATE_SUMMARY)" \
		--statistics "$(MODERATE_STATISTICS)" \
		--expected-condition-count "$(MODERATE_EXPECTED_CONDITIONS)" \
		--output-dir outputs/tables
figures: moderate-figures method-figures ## Generate publication figures from the moderate benchmark.
tables: moderate-tables ## Generate publication tables from the moderate benchmark.
paper: figures tables ## Compile the manuscript after validating generated artifacts.
	@scripts/paper/build_paper.sh
reproduce-small: ## Exercise the full small-data pipeline.
	@scripts/reproduce_small.sh --seed "$(SEED)"
reproduce-paper: ## Rebuild paper artifacts from a completed locked evaluation.
	@scripts/reproduce_paper.sh
privacy-check: | $(LOG_DIR) ## Reject private paths, host IDs, secrets, and unsafe metadata.
	@$(OFFLINE_RUN) python scripts/bootstrap/sanitize_hdf5_metadata.py 2>&1 | tee "$(LOG_DIR)/hdf5-privacy.log"
	@$(OFFLINE_RUN) python scripts/bootstrap/privacy_audit.py 2>&1 | tee "$(LOG_DIR)/privacy-audit.log"
student-branch: ## Safely create the student/reproduce teaching branch.
	@scripts/teaching/make_student_branch.sh
