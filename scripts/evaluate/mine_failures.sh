#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
SEED_START="${SEED_START:-0}"
if [[ -n "${CONDA_PREFIX:-}" || -n "${VIRTUAL_ENV:-}" ]]; then
    echo "ERROR: failure mining launches Arena and must run outside Conda" >&2
    exit 2
fi
env -u CONDA_PREFIX -u CONDA_DEFAULT_ENV -u CONDA_PROMPT_MODIFIER \
    -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH -u CMAKE_PREFIX_PATH \
    -u ROS_DISTRO -u ROS_VERSION -u ROS_PYTHON_VERSION CONDA_SHLVL=0 \
    conda run -n "${CONDA_ENV_NAME}" \
    python "${PROJECT_ROOT}/scripts/data/materialize_failure_mining.py" \
    --seed-count 10 --seed-start "${SEED_START}"
python3 "${PROJECT_ROOT}/scripts/evaluate/mine_failures.py" "$@"
python3 "${PROJECT_ROOT}/scripts/evaluate/summarize_failure_mining.py"
