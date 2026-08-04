#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
EPISODE_MANIFEST="outputs/final/episode_manifest.parquet"
RUN_MANIFEST="outputs/final/run_manifest.json"

if (($#)); then
    echo "Usage: scripts/reproduce_paper.sh" >&2
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
for required in "${EPISODE_MANIFEST}" "${RUN_MANIFEST}"; do
    if [[ ! -s "${required}" ]]; then
        echo "ERROR: missing completed final-run input: ${required}" >&2
        echo "This command only rebuilds artifacts; it never starts or resumes simulation." >&2
        exit 1
    fi
done

echo "[reproduce-paper] collecting the locked run; no simulation will be launched"
offline python scripts/evaluate/collect_results.py \
    --manifest "${EPISODE_MANIFEST}" \
    --run-manifest "${RUN_MANIFEST}" \
    --raw-dir data/raw \
    --results outputs/final/results.parquet \
    --summary outputs/final/summary.csv \
    --statistics outputs/final/statistics.json \
    --bootstrap-seed 20260804
offline python scripts/evaluate/failure_analysis.py \
    --results outputs/final/results.parquet \
    --output outputs/final/failure_analysis.md
offline python scripts/paper/render_episode_media.py \
    --results outputs/final/results.parquet \
    --raw-dir data/raw
offline python scripts/paper/make_figures.py
offline python scripts/paper/make_figures.py --output-dir outputs/figures
offline python scripts/paper/make_tables.py
offline python scripts/paper/make_tables.py --output-dir outputs/tables
clean_env \
    PROJECT_ROOT="${PROJECT_ROOT}" \
    CONDA_ENV_NAME="${CONDA_ENV_NAME}" \
    bash "${PROJECT_ROOT}/scripts/paper/build_paper.sh"
offline python scripts/paper/build_artifact_manifest.py \
    --command scripts/reproduce_paper.sh

echo "[reproduce-paper] PASS: paper/main.pdf and outputs/final/artifact_manifest.json"
