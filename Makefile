SHELL := /bin/bash
PROJECT_ROOT ?= $(CURDIR)
ARENA_WS ?= $(HOME)/arena5_ws
CONDA_ENV_NAME ?= ramp-offline
SEED ?= 0
HEADLESS ?= 1
CONFIG ?=
LOG_DIR ?= $(PROJECT_ROOT)/outputs/logs

.DEFAULT_GOAL := help

.PHONY: help preflight conda arena build test smoke baseline scenarios mine-failures label-expert train-bc train-dagger train-ppo-smoke train-ppo train-detector pilot evaluate-flatland evaluate-gazebo statistics figures tables paper reproduce-small reproduce-paper student-branch

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
	@conda run -n "$(CONDA_ENV_NAME)" ruff check . 2>&1 | tee "$(LOG_DIR)/ruff.log"
	@conda run -n "$(CONDA_ENV_NAME)" pytest -q 2>&1 | tee "$(LOG_DIR)/pytest.log"

smoke: | $(LOG_DIR) ## Run the Arena headless smoke test.
	@SEED="$(SEED)" HEADLESS="$(HEADLESS)" scripts/arena/smoke_arena.sh 2>&1 | tee "$(LOG_DIR)/arena_smoke.log"

baseline: ## Run baseline episodes (implemented after Gate 0).
	@scripts/evaluate/run_baseline.sh --seed "$(SEED)" $(if $(CONFIG),--config "$(CONFIG)")
scenarios: ## Compile deterministic scenarios.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/data/compile_scenarios.py --seed "$(SEED)"
mine-failures: ## Mine reproducible planner failures.
	@scripts/evaluate/mine_failures.sh --seed "$(SEED)"
label-expert: ## Label recovery states using the privileged expert.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/data/label_expert.py --seed "$(SEED)"
train-bc: ## Train behavior cloning policies.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/train/train_bc.py --seed "$(SEED)"
train-dagger: ## Run two DAgger aggregation rounds.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/train/train_dagger.py --seed "$(SEED)"
train-ppo-smoke: ## Run a small action-masked PPO smoke job.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/train/train_ppo.py --profile smoke --seed "$(SEED)"
train-ppo: ## Run configured PPO training.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/train/train_ppo.py --profile main --seed "$(SEED)"
train-detector: ## Train the optional learned failure detector.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/train/train_detector.py --seed "$(SEED)"
pilot: ## Run validation-only pilot evaluation.
	@scripts/evaluate/run_experiment.sh --tier pilot --seed "$(SEED)"
evaluate-flatland: ## Run the locked Flatland final manifest.
	@scripts/evaluate/run_experiment.sh --tier final --simulator flatland
evaluate-gazebo: ## Run the optional Gazebo transfer validation.
	@scripts/evaluate/run_experiment.sh --tier gazebo --simulator gazebo
statistics: ## Compute paired statistics from final artifacts.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/evaluate/statistics.py
figures: ## Generate figures from recorded results.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/paper/make_figures.py
tables: ## Generate LaTeX tables from recorded results.
	@conda run -n "$(CONDA_ENV_NAME)" python scripts/paper/make_tables.py
paper: ## Compile the manuscript after validating generated artifacts.
	@scripts/paper/build_paper.sh
reproduce-small: ## Exercise the full small-data pipeline.
	@scripts/reproduce_small.sh --seed "$(SEED)"
reproduce-paper: ## Recreate final evaluation, statistics, figures, tables, and PDF.
	@scripts/reproduce_paper.sh
student-branch: ## Safely create the student/reproduce teaching branch.
	@scripts/teaching/make_student_branch.sh
