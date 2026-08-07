#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
SEED=0
BOOTSTRAP_SEED=20260804

usage() {
    cat <<'EOF'
Usage: scripts/reproduce_small.sh [--seed INTEGER]

Run key unit tests and the deterministic offline policy ablation in the clean
ramp-offline Conda environment. The small ablation is written under
outputs/smoke and never replaces the frozen final ablation. If a complete final
run manifest is present, also verify that the recorded final evidence can
rebuild results, figures, tables, and the paper. No simulator or large training
job is started by this script.
EOF
}

while (($#)); do
    case "$1" in
        --seed)
            if (($# < 2)); then
                echo "ERROR: --seed requires an integer" >&2
                exit 2
            fi
            SEED="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! "${SEED}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --seed must be a non-negative integer" >&2
    exit 2
fi
if [[ ! -f "${PROJECT_ROOT}/pyproject.toml" ]]; then
    echo "ERROR: repository root could not be resolved from ${BASH_SOURCE[0]}" >&2
    exit 1
fi
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda is required for the ramp-offline environment" >&2
    exit 1
fi

clean_env() {
    env \
        -u AMENT_PREFIX_PATH \
        -u CMAKE_PREFIX_PATH \
        -u COLCON_PREFIX_PATH \
        -u CONDA_DEFAULT_ENV \
        -u CONDA_PREFIX \
        -u CONDA_PROMPT_MODIFIER \
        -u LD_LIBRARY_PATH \
        -u PYTHONHOME \
        -u PYTHONPATH \
        -u RMW_IMPLEMENTATION \
        -u ROS_DOMAIN_ID \
        -u ROS_DISTRO \
        -u ROS_LOCALHOST_ONLY \
        -u ROS_PYTHON_VERSION \
        -u ROS_VERSION \
        -u VIRTUAL_ENV \
        CONDA_SHLVL=0 \
        "$@"
}

offline() {
    clean_env conda run --no-capture-output -n "${CONDA_ENV_NAME}" "$@"
}

cd "${PROJECT_ROOT}"
export PYTHONHASHSEED="${SEED}"
echo "[reproduce-small] root=${PROJECT_ROOT} conda_env=${CONDA_ENV_NAME} seed=${SEED}"
offline python -c 'import sys; assert sys.version_info[:2] == (3, 10), sys.version'
offline pytest -q \
    tests/unit/test_action_mask.py \
    tests/unit/test_state_machine.py \
    tests/unit/test_planning_expert.py \
    tests/unit/test_offline_policy_ablation.py \
    tests/unit/test_collect_results.py \
    tests/unit/test_statistics_cli.py \
    tests/unit/test_paper_artifacts.py \
    tests/unit/test_artifact_manifest.py \
    tests/unit/test_reproduce_scripts.py

mkdir -p outputs/smoke
offline python scripts/evaluate/offline_policy_ablation.py \
	--output outputs/smoke/offline_policy_ablation.csv

EPISODE_MANIFEST="outputs/final/episode_manifest.parquet"
RUN_MANIFEST="outputs/final/run_manifest.json"
if [[ ! -s "${EPISODE_MANIFEST}" || ! -s "${RUN_MANIFEST}" ]]; then
    echo "[reproduce-small] SKIP final paper chain: complete episode/run manifests are not both present."
    echo "[reproduce-small] PASS: tests and offline policy ablation completed."
    exit 0
fi

offline python scripts/evaluate/collect_results.py \
    --manifest "${EPISODE_MANIFEST}" \
    --run-manifest "${RUN_MANIFEST}" \
    --raw-dir data/raw \
    --results outputs/final/results.parquet \
    --summary outputs/final/summary.csv \
    --statistics outputs/final/statistics.json \
    --bootstrap-seed "${BOOTSTRAP_SEED}"
offline python scripts/paper/make_figures.py
offline python scripts/paper/make_tables.py
clean_env \
    PROJECT_ROOT="${PROJECT_ROOT}" \
    CONDA_ENV_NAME="${CONDA_ENV_NAME}" \
    bash "${PROJECT_ROOT}/scripts/paper/build_paper.sh"

echo "[reproduce-small] PASS: final paper chain rebuilt from the completed run."
