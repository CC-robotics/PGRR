#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'Source this file: source scripts/bootstrap/activate_offline.sh\n' >&2
    exit 2
fi
if ! command -v conda >/dev/null 2>&1; then
    printf 'conda is not available in PATH\n' >&2
    return 1
fi
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV_NAME:-ramp-offline}"
printf 'Activated offline environment. ROS has not been sourced.\n'
