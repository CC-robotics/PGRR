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
mux_mount=()
if [[ "${RAMP_ENABLE_CMD_MUX:-0}" == "1" ]]; then
    mux_mount=(
        -v "${PROJECT_ROOT}/configs/platform/jackal_mappings_mux.yaml:/opt/arena_ws/src/arena/simulation-setup/entities/robots/jackal/mappings.yaml:ro"
    )
fi
task_generator_mount=()
if [[ "${RAMP_DISABLE_AUTO_RESET:-0}" == "1" ]]; then
    task_generator_mount=(
        -v "${PROJECT_ROOT}/configs/platform/arena_task_generator_no_auto_reset.yaml:/opt/arena_ws/install/arena_bringup/share/arena_bringup/configs/task_generator.yaml:ro"
    )
fi
docker run --rm --runtime runc --network host --ipc host \
    -e WANDB_MODE=offline \
    -e RAMP_ROOT=/workspace \
    -e RAMP_DISABLE_AUTO_RESET="${RAMP_DISABLE_AUTO_RESET:-0}" \
    -v "${PROJECT_ROOT}:/workspace" \
    -v "${PROJECT_ROOT}/configs/platform/jackal_planar_lidar.gazebo:/opt/arena_ws/src/arena/simulation-setup/entities/robots/jackal/urdf/jackal.gazebo:ro" \
    -v "${PROJECT_ROOT}/configs/platform/shelf_static.sdf:/opt/arena_ws/src/arena/simulation-setup/entities/obstacles/static/shelf/sdf/shelf.sdf:ro" \
    "${mux_mount[@]}" \
    "${task_generator_mount[@]}" \
    "${ARENA_IMAGE}" \
    bash --noprofile --norc -c \
    'export PATH=/root/.local/bin:$PATH
     source /opt/ros/humble/setup.bash
     if [[ "${RAMP_DISABLE_AUTO_RESET:-0}" == "1" ]]; then
         task_node=/opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/node.py
         patch --forward --silent --reject-file=- "$task_node" /workspace/third_party/task_generator_auto_reset.patch 2>/dev/null ||
             grep -q "self._task.is_done and self._auto_reset" "$task_node"
         robot_manager=/opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/manager/robot_manager/robot_manager.py
         patch --forward --silent --reject-file=- "$robot_manager" /workspace/third_party/task_generator_known_pose.patch 2>/dev/null ||
             grep -q "'\''amcl'\'': '\''false'\''" "$robot_manager"
         patch --forward --silent --reject-file=- "$robot_manager" /workspace/third_party/task_generator_known_pose_gazebo_tf.patch 2>/dev/null ||
             grep -q "Known-pose Gazebo publishes the dynamic odom-to-base transform" "$robot_manager" || {
                 printf "ERROR: Arena known-pose Gazebo TF patch is not applied\n" >&2
                 exit 1
             }
         gazebo_simulator=/opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/simulators/sim/gazebo_simulator/gazebo_simulator.py
         patch --forward --silent --reject-file=- "$gazebo_simulator" /workspace/third_party/task_generator_ground_truth_odom.patch 2>/dev/null ||
             grep -q "Ground-truth odometry already uses map coordinates" "$gazebo_simulator"
     fi
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
