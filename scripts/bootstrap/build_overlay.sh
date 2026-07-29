#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
if [[ -n "${CONDA_PREFIX:-}" || -n "${VIRTUAL_ENV:-}" ]]; then
    printf 'ERROR: deactivate Conda and virtualenv before building the ROS overlay\n' >&2
    exit 1
fi
profile="$(awk '/^profile:/ {print $2}' "${PROJECT_ROOT}/configs/platform/arena_profile.yaml" 2>/dev/null || true)"
if [[ "${profile}" == "arena_humble_docker" ]]; then
    exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
        bash -lc 'cd /workspace/ros_ws && rosdep install --from-paths src --ignore-src -r -y --rosdistro humble && colcon build --symlink-install'
fi
source "${PROJECT_ROOT}/scripts/bootstrap/source_runtime.sh"
cd "${PROJECT_ROOT}/ros_ws"
rosdep install --from-paths src --ignore-src -r -y --rosdistro humble
colcon build --symlink-install
