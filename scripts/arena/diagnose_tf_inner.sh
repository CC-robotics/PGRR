#!/usr/bin/env bash
set -euo pipefail

if [[ "${RAMP_DISABLE_AUTO_RESET:-0}" != "1" ]]; then
    echo "ERROR: TF diagnostics require RAMP_DISABLE_AUTO_RESET=1" >&2
    exit 2
fi

scenario="${RAMP_SCENARIO:?RAMP_SCENARIO is required}"
scenario_target="/opt/arena_ws/install/arena_simulation_setup/share/arena_simulation_setup/worlds/map_empty/scenarios/default.json"
runtime_log="${RAMP_TF_DIAGNOSTIC_LOG:-/workspace/outputs/logs/baseline/tf_diagnostic_runtime.log}"
mkdir -p "$(dirname "${runtime_log}")"
cp "${scenario}" "${scenario_target}"
: >"${runtime_log}"

export LIBGL_ALWAYS_SOFTWARE=1
setsid xvfb-run -a -s '-screen 0 1280x720x24' \
    ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo human:=dummy headless:=2 robot:=jackal local_planner:=dwb world:=map_empty \
    inter_planner:=navigate_w_replanning_time \
    tm_robots:=scenario tm_obstacles:=scenario use_sim_time:=true \
    >>"${runtime_log}" 2>&1 &
launch_pid=$!
odom_tf_pid=""
cleanup_started=0

stop_pid_bounded() {
    local pid="${1:-}"
    local signal="${2:-INT}"
    local attempts="${3:-10}"
    [[ -n "${pid}" ]] || return 0
    kill -0 "${pid}" 2>/dev/null || {
        wait "${pid}" 2>/dev/null || true
        return 0
    }
    kill -"${signal}" "${pid}" 2>/dev/null || true
    for _ in $(seq 1 "${attempts}"); do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "${pid}" 2>/dev/null; then
        kill -TERM "${pid}" 2>/dev/null || true
        for _ in $(seq 1 5); do
            kill -0 "${pid}" 2>/dev/null || break
            sleep 1
        done
    fi
    if kill -0 "${pid}" 2>/dev/null; then
        kill -KILL "${pid}" 2>/dev/null || true
    fi
    wait "${pid}" 2>/dev/null || true
}

cleanup() {
    if (( cleanup_started )); then
        return
    fi
    cleanup_started=1
    stop_pid_bounded "${odom_tf_pid}" INT 10
    if kill -0 "${launch_pid}" 2>/dev/null; then
        kill -INT -- "-${launch_pid}" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "${launch_pid}" 2>/dev/null || break
            sleep 1
        done
        kill -TERM -- "-${launch_pid}" 2>/dev/null || true
        wait "${launch_pid}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
        echo "ERROR: Arena exited before odometry became available" >&2
        tail -120 "${runtime_log}" >&2
        exit 1
    fi
    if ros2 topic list 2>/dev/null | grep -qx '/task_generator_node/jackal/odom'; then
        break
    fi
    sleep 2
done
if ! ros2 topic list 2>/dev/null | grep -qx '/task_generator_node/jackal/odom'; then
    echo "ERROR: odometry topic did not become available" >&2
    exit 1
fi

ramp_ros_prefix="$(ros2 pkg prefix ramp_ros)"
"${ramp_ros_prefix}/lib/ramp_ros/odom_tf_broadcaster" --ros-args \
    -p use_sim_time:=true \
    -p odom_topic:=/task_generator_node/jackal/odom \
    >>"${runtime_log}" 2>&1 &
odom_tf_pid=$!

tf_deadline=$((SECONDS + 30))
while (( SECONDS < tf_deadline )); do
    if grep -Fq 'broadcast first odometry transform' "${runtime_log}"; then
        break
    fi
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
        echo "ERROR: Arena exited before the odometry TF broadcaster became ready" >&2
        tail -120 "${runtime_log}" >&2
        exit 1
    fi
    if ! kill -0 "${odom_tf_pid}" 2>/dev/null; then
        echo "ERROR: odometry TF broadcaster exited before publishing a transform" >&2
        tail -120 "${runtime_log}" >&2
        exit 1
    fi
    sleep 1
done
if ! grep -Fq 'broadcast first odometry transform' "${runtime_log}"; then
    echo "ERROR: odometry TF broadcaster did not publish within 30 seconds" >&2
    tail -120 "${runtime_log}" >&2
    exit 1
fi

printf 'ROS_ODOM_SAMPLE\n'
timeout 15 ros2 topic echo --once /task_generator_node/jackal/odom || true
printf 'TF_TOPIC_INFO\n'
ros2 topic info -v /tf || true
printf 'TF_ODOM_BASE\n'
timeout 12 ros2 run tf2_ros tf2_echo jackal/odom jackal/base_link || true
printf 'TF_MAP_BASE\n'
timeout 12 ros2 run tf2_ros tf2_echo map jackal/base_link || true
printf 'GZ_GROUND_TRUTH_TOPICS\n'
gz topic -l | grep -E 'ground_truth|wheel_(odometry|tf)' || true
printf 'GZ_GROUND_TRUTH_POSE\n'
timeout 8 gz topic -e -t /model/jackal/ground_truth_pose || true
printf 'DIAGNOSTIC_LOG_KEYS\n'
grep -E 'Task Reset|Off Grid|transform|ground_truth|ERROR' "${runtime_log}" | tail -80 || true
