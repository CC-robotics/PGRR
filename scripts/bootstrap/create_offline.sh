#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
cd "${PROJECT_ROOT}"

clean_env() {
    env \
        -u AMENT_PREFIX_PATH \
        -u CMAKE_PREFIX_PATH \
        -u COLCON_PREFIX_PATH \
        -u PYTHONHOME \
        -u PYTHONPATH \
        -u ROS_DISTRO \
        -u ROS_PYTHON_VERSION \
        -u ROS_VERSION \
        "$@"
}

if ! command -v conda >/dev/null 2>&1; then
    printf 'ERROR: conda is not installed\n' >&2
    exit 1
fi

if conda env list | awk '{print $1}' | grep -Fxq "${CONDA_ENV_NAME}"; then
    conda env update -n "${CONDA_ENV_NAME}" -f environment.yml --prune
elif command -v mamba >/dev/null 2>&1; then
    mamba env create -f environment.yml
else
    conda env create -f environment.yml
fi

clean_env conda run -n "${CONDA_ENV_NAME}" python -m pip install \
    -e packages/ramp_core -e packages/ramp_ml
conda env export -n "${CONDA_ENV_NAME}" --no-builds \
    | sed -E '/^prefix:[[:space:]]/d' > environment.lock.yml
clean_env conda run -n "${CONDA_ENV_NAME}" python -m pip list \
    --format=freeze --exclude-editable > requirements-offline.lock.txt
printf '%s\n' '-e packages/ramp_core' '-e packages/ramp_ml' \
    >> requirements-offline.lock.txt
clean_env conda run -n "${CONDA_ENV_NAME}" python -c \
    'import sys; assert sys.version_info[:2] == (3, 10), sys.version; import ramp_core, ramp_ml'
printf 'Offline environment %s is ready.\n' "${CONDA_ENV_NAME}"
