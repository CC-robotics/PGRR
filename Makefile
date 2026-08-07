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
MODERATE_OFFLINE_ABLATION ?= $(MODERATE_ANALYSIS_DIR)/offline_policy_ablation.csv
MODERATE_EXPECTED_CONDITIONS ?= 120
MODERATE_BENCHMARK_CONFIG ?= configs/experiments/scenario_catalog_moderate_v6.yaml
MODERATE_SPLIT_MANIFEST ?= scenarios/splits/moderate_v6_test.yaml
MODERATE_CALIBRATION_SPLIT ?= scenarios/splits/moderate_v6_validation.yaml
MODERATE_CALIBRATION_DIR ?= outputs/moderate/v6_validation_base_d5fa66b
MODERATE_CALIBRATION_RESULTS ?= $(MODERATE_CALIBRATION_DIR)/results.parquet
MODERATE_CALIBRATION_REPORT ?= $(MODERATE_CALIBRATION_DIR)/calibration_report.json
MODERATE_METHODS ?= base standard heuristic bc_uniform pgrr
MODERATE_MAIN_METHOD ?= pgrr
MODERATE_REFERENCE_METHOD ?= base
EVALUATION_JOBS ?= 6
EVALUATION_TIMEOUT_S ?= 240
REPORT_STAGE ?= pending
REPORT_RESULTS ?= outputs/moderate/final/results.parquet
REPORT_STATISTICS ?= outputs/moderate/final/pairwise_statistics.json
REPORT_MATCHED_EVIDENCE ?= outputs/moderate/final/matched_base_pgrr_evidence.json
REPORT_EXPECTED_CONDITIONS ?=
REPORT_GENERATED_DIR ?= report/generated
PRESENTATION_OUTPUT ?= presentation/PGRR_report_zh.pptx
PRESENTATION_NOTES ?= presentation/speaker_notes_zh.md
PRESENTATION_PDF ?= presentation/PGRR_report_zh.pdf
OFFLINE_RUN := env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH -u CMAKE_PREFIX_PATH -u ROS_DISTRO -u ROS_VERSION -u ROS_PYTHON_VERSION conda run -n "$(CONDA_ENV_NAME)"

.DEFAULT_GOAL := help

.PHONY: help preflight conda arena build test smoke baseline scenarios mine-failures label-expert train-bc train-dagger train-ppo-smoke train-ppo train-detector pilot evaluate-calibration calibration-report verify-calibration evaluate-final evaluate-flatland evaluate-gazebo statistics method-figures figures tables moderate-figures moderate-tables paper report-assets technical-report presentation-check presentation reproduce-small reproduce-paper privacy-check student-branch

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
evaluate-calibration: ## Run and score the complete Base-only moderate-v6 validation calibration.
	@$(OFFLINE_RUN) python scripts/evaluate/run_experiment.py \
		--split validation --split-manifest "$(MODERATE_CALIBRATION_SPLIT)" \
		--methods base --jobs "$(EVALUATION_JOBS)" \
		--timeout "$(EVALUATION_TIMEOUT_S)" \
		--output-dir "$(MODERATE_CALIBRATION_DIR)"
	@$(OFFLINE_RUN) python scripts/evaluate/collect_results.py \
		--manifest "$(MODERATE_CALIBRATION_DIR)/episode_manifest.parquet" \
		--run-manifest "$(MODERATE_CALIBRATION_DIR)/run_manifest.json" \
		--raw-dir data/raw \
		--results "$(MODERATE_CALIBRATION_RESULTS)" \
		--summary "$(MODERATE_CALIBRATION_DIR)/collector_summary.csv" \
		--statistics "$(MODERATE_CALIBRATION_DIR)/collector_statistics.json" \
		--reference-policy base --treatment-policy calibration_unused \
		--bootstrap-samples 10000 --bootstrap-seed "$(BOOTSTRAP_SEED)"
	@$(OFFLINE_RUN) python scripts/evaluate/calibrate_moderate.py \
		--results "$(MODERATE_CALIBRATION_RESULTS)" \
		--split-manifest "$(MODERATE_CALIBRATION_SPLIT)" \
		--output "$(MODERATE_CALIBRATION_REPORT)" \
		--expected-conditions 72

calibration-report: ## Rebuild the Base-only v6 calibration report from collected validation results.
	@$(OFFLINE_RUN) python scripts/evaluate/calibrate_moderate.py \
		--results "$(MODERATE_CALIBRATION_RESULTS)" \
		--split-manifest "$(MODERATE_CALIBRATION_SPLIT)" \
		--output "$(MODERATE_CALIBRATION_REPORT)" \
		--expected-conditions 72

verify-calibration: ## Verify the accepted calibration report against the frozen v6 config and SHA256.
	@$(OFFLINE_RUN) python scripts/evaluate/calibrate_moderate.py \
		--verify-report "$(MODERATE_CALIBRATION_REPORT)" \
		--evaluation-config configs/final/ei_gazebo.yaml

evaluate-final: verify-calibration ## Run the locked five-method moderate-v6 Gazebo test manifest.
	@$(OFFLINE_RUN) python scripts/evaluate/run_experiment.py \
		--split test --split-manifest "$(MODERATE_SPLIT_MANIFEST)" \
		--methods $(MODERATE_METHODS) --jobs "$(EVALUATION_JOBS)" \
		--timeout "$(EVALUATION_TIMEOUT_S)" \
		--output-dir "$(MODERATE_ANALYSIS_DIR)"

evaluate-flatland: evaluate-final ## Compatibility alias for the locked Gazebo final evaluation.
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
moderate-figures: ## Generate figures from published moderate result/statistic artifacts.
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
moderate-tables: ## Generate tables from published moderate result/statistic artifacts.
	@$(OFFLINE_RUN) python scripts/paper/make_moderate_tables.py \
		--results "$(MODERATE_RESULTS)" --summary "$(MODERATE_SUMMARY)" \
		--statistics "$(MODERATE_STATISTICS)" \
		--ablation "$(MODERATE_OFFLINE_ABLATION)" \
		--expected-condition-count "$(MODERATE_EXPECTED_CONDITIONS)" \
		--output-dir paper/generated
	@$(OFFLINE_RUN) python scripts/paper/make_moderate_tables.py \
		--results "$(MODERATE_RESULTS)" --summary "$(MODERATE_SUMMARY)" \
		--statistics "$(MODERATE_STATISTICS)" \
		--ablation "$(MODERATE_OFFLINE_ABLATION)" \
		--expected-condition-count "$(MODERATE_EXPECTED_CONDITIONS)" \
		--output-dir outputs/tables
figures: moderate-figures method-figures ## Generate publication figures from the moderate benchmark.
tables: moderate-tables ## Generate publication tables from the moderate benchmark.
paper: figures tables ## Compile the manuscript after validating generated artifacts.
	@scripts/paper/build_paper.sh

report-assets: ## Generate fail-closed pending/validation/test report inputs.
	@args=(--stage "$(REPORT_STAGE)" --output-dir "$(REPORT_GENERATED_DIR)" --require-runtime-capture); \
	if [[ "$(REPORT_STAGE)" != "pending" ]]; then \
		args+=(--results "$(REPORT_RESULTS)" --statistics "$(REPORT_STATISTICS)" \
			--matched-evidence "$(REPORT_MATCHED_EVIDENCE)"); \
	fi; \
	if [[ -n "$(REPORT_EXPECTED_CONDITIONS)" ]]; then args+=(--expected-conditions "$(REPORT_EXPECTED_CONDITIONS)"); fi; \
	$(OFFLINE_RUN) python scripts/report/build_report_assets.py "$${args[@]}"

technical-report: ## Build and validate the 25--35 page Chinese technical report.
	@REPORT_STAGE="$(REPORT_STAGE)" REPORT_RESULTS="$(if $(filter pending,$(REPORT_STAGE)),,$(REPORT_RESULTS))" \
	REPORT_STATISTICS="$(if $(filter pending,$(REPORT_STAGE)),,$(REPORT_STATISTICS))" \
	REPORT_MATCHED_EVIDENCE="$(if $(filter pending,$(REPORT_STAGE)),,$(REPORT_MATCHED_EVIDENCE))" \
	REPORT_EXPECTED_CONDITIONS="$(REPORT_EXPECTED_CONDITIONS)" CONDA_ENV_NAME="$(CONDA_ENV_NAME)" \
	scripts/report/build_report.sh

presentation-check: report-assets ## Validate the 30-slide Chinese deck specification without python-pptx.
	@$(OFFLINE_RUN) python scripts/presentation/build_deck.py \
		--stage "$(REPORT_STAGE)" --report-data "$(REPORT_GENERATED_DIR)/report_data.json" \
		--check-only

presentation: report-assets ## Build the 30-slide PPTX, speaker notes, and exported PDF.
	@$(OFFLINE_RUN) python scripts/presentation/build_deck.py \
		--stage "$(REPORT_STAGE)" --report-data "$(REPORT_GENERATED_DIR)/report_data.json" \
		--output "$(PRESENTATION_OUTPUT)" --notes "$(PRESENTATION_NOTES)"
	@PRESENTATION_PPTX="$(abspath $(PRESENTATION_OUTPUT))" \
	PRESENTATION_PDF="$(abspath $(PRESENTATION_PDF))" \
	PRESENTATION_NOTES="$(abspath $(PRESENTATION_NOTES))" \
	CONDA_ENV_NAME="$(CONDA_ENV_NAME)" scripts/presentation/render_pdf.sh
reproduce-small: ## Exercise the full small-data pipeline.
	@scripts/reproduce_small.sh --seed "$(SEED)"
reproduce-paper: ## Rebuild paper artifacts from a completed locked evaluation.
	@scripts/reproduce_paper.sh
privacy-check: | $(LOG_DIR) ## Reject private paths, host IDs, secrets, and unsafe metadata.
	@$(OFFLINE_RUN) python scripts/bootstrap/sanitize_hdf5_metadata.py 2>&1 | tee "$(LOG_DIR)/hdf5-privacy.log"
	@$(OFFLINE_RUN) python scripts/bootstrap/privacy_audit.py 2>&1 | tee "$(LOG_DIR)/privacy-audit.log"
student-branch: ## Safely create the student/reproduce teaching branch.
	@scripts/teaching/make_student_branch.sh
