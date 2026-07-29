#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARENA_IMAGE="${ARENA_IMAGE:-ramp-arena:humble}"
if ! docker image inspect "${ARENA_IMAGE}" >/dev/null 2>&1; then
    printf 'ERROR: Arena image is missing. Run make arena first.\n' >&2
    exit 1
fi
if ! docker run --rm --runtime runc "${ARENA_IMAGE}" \
    test -f /opt/arena_ws/.ramp_install_complete; then
    printf 'ERROR: Arena image exists but has not passed installation validation.\n' >&2
    exit 1
fi
docker run --rm --runtime runc --network host --ipc host \
    -e WANDB_MODE=offline \
    -e RAMP_ROOT=/workspace \
    -v "${PROJECT_ROOT}:/workspace" \
    -v "${PROJECT_ROOT}/configs/platform/jackal_planar_lidar.gazebo:/opt/arena_ws/src/arena/simulation-setup/entities/robots/jackal/urdf/jackal.gazebo:ro" \
    -v "${PROJECT_ROOT}/configs/platform/shelf_static.sdf:/opt/arena_ws/src/arena/simulation-setup/entities/obstacles/static/shelf/sdf/shelf.sdf:ro" \
    "${ARENA_IMAGE}" \
    bash --noprofile --norc -c \
    'export PATH=/root/.local/bin:$PATH
     source /opt/ros/humble/setup.bash
     cd /opt/arena_ws
     source arena.bash
     if [[ -n "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" && ! -f "${FASTRTPS_DEFAULT_PROFILES_FILE}" ]]; then
         unset FASTRTPS_DEFAULT_PROFILES_FILE
     fi
     cd /workspace
     if [[ -r /workspace/ros_ws/install/setup.bash ]]; then source /workspace/ros_ws/install/setup.bash; fi
     for runtime_var in AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH; do
         runtime_value="${!runtime_var:-}"
         runtime_value="$(printf "%s" "${runtime_value}" | awk -v RS=: -v ORS=: '\''!/^\/opt\/arena_ws\/install\/(bond|bondcpp|bondpy|test_bond)(\/|$)/'\'' | sed '\''s/:$//'\'')"
         export "${runtime_var}=${runtime_value}"
     done
     export PYTHONPATH="/workspace/packages/ramp_core:/workspace/packages/ramp_ml${PYTHONPATH:+:${PYTHONPATH}}"
     exec "$@"' \
    bash "$@"
