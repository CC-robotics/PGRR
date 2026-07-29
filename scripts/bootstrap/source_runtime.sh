#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'Source this file: source scripts/bootstrap/source_runtime.sh\n' >&2
    exit 2
fi
if [[ -n "${CONDA_PREFIX:-}" || -n "${VIRTUAL_ENV:-}" ]]; then
    printf 'Refusing to mix Arena with Conda/virtualenv. Deactivate it first.\n' >&2
    return 1
fi

RAMP_ROOT="${RAMP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARENA_WS="${ARENA_WS:-${HOME}/arena5_ws}"
export RAMP_ROOT ARENA_WS

for variable in AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH; do
    value="${!variable:-}"
    if [[ -n "${value}" ]]; then
        cleaned="$(printf '%s' "${value}" | awk -v RS=: -v ORS=: '!/\/opt\/ros\/(iron|jazzy|rolling)/' | sed 's/:$//')"
        export "${variable}=${cleaned}"
    fi
done
unset ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION

if [[ ! -r /opt/ros/humble/setup.bash ]]; then
    printf 'ROS2 Humble setup is missing\n' >&2
    return 1
fi
source /opt/ros/humble/setup.bash

if [[ -r "${ARENA_WS}/arena" ]]; then
    source "${ARENA_WS}/arena"
elif [[ -r "${ARENA_WS}/arena.bash" ]]; then
    source "${ARENA_WS}/arena.bash"
elif [[ -r "${ARENA_WS}/install/setup.bash" ]]; then
    source "${ARENA_WS}/install/setup.bash"
fi
if [[ -r "${RAMP_ROOT}/ros_ws/install/setup.bash" ]]; then
    source "${RAMP_ROOT}/ros_ws/install/setup.bash"
fi
export WANDB_MODE=offline
printf 'RAMP runtime sourced: ROS_DISTRO=%s ARENA_WS=%s\n' "${ROS_DISTRO}" "${ARENA_WS}"
