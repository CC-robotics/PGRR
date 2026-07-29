#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${RAMP_SMOKE_LOG:-/workspace/outputs/logs/arena_runtime.log}"
TIMEOUT_S="${RAMP_SMOKE_TIMEOUT_S:-240}"
SIMULATOR="${RAMP_SIMULATOR:-gazebo}"
ROBOT="${RAMP_ROBOT:-jackal}"
LOCAL_PLANNER="${RAMP_LOCAL_PLANNER:-dwb}"
WORLD="${RAMP_WORLD:-map_empty}"
mkdir -p "$(dirname "${LOG_FILE}")"
: >"${LOG_FILE}"

if ! ros2 pkg prefix arena_bringup >/dev/null 2>&1; then
    printf 'ERROR: arena_bringup is not discoverable\n' >&2
    exit 1
fi
map_server_executable="$(ros2 pkg prefix nav2_map_server)/lib/nav2_map_server/map_server"
if ldd "${map_server_executable}" | grep -Eq '/opt/arena_ws/install/(bond|bondcpp|bondpy|test_bond)(/|$)'; then
    printf 'ERROR: binary Nav2 is shadowed by the incompatible Arena bond overlay\n' >&2
    exit 1
fi

export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
setsid xvfb-run -a -s '-screen 0 1280x720x24' \
    ros2 launch arena_bringup arena.launch.py \
    sim:="${SIMULATOR}" headless:=2 robot:="${ROBOT}" \
    local_planner:="${LOCAL_PLANNER}" world:="${WORLD}" \
    use_sim_time:=true >>"${LOG_FILE}" 2>&1 &
launch_pid=$!
cleanup_started=0

cleanup() {
    if (( cleanup_started )); then
        return
    fi
    cleanup_started=1
    printf '[RAMP_SMOKE] cleanup_started\n' >>"${LOG_FILE}"
    if kill -0 "${launch_pid}" 2>/dev/null; then
        kill -INT -- "-${launch_pid}" 2>/dev/null || true
        for _ in $(seq 1 30); do
            kill -0 "${launch_pid}" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "${launch_pid}" 2>/dev/null; then
            kill -TERM -- "-${launch_pid}" 2>/dev/null || true
        fi
        wait "${launch_pid}" 2>/dev/null || true
    fi
    printf '[RAMP_SMOKE] cleanup_complete\n' >>"${LOG_FILE}"
}
trap cleanup EXIT INT TERM

deadline=$((SECONDS + TIMEOUT_S))
topic_by_type() {
    local message_type="$1"
    ros2 topic list -t 2>/dev/null | \
        awk -v expected="[${message_type}]" '$2 == expected {print $1; exit}'
}

action_by_type() {
    local action_type="$1"
    ros2 action list -t 2>/dev/null | \
        awk -v expected="[${action_type}]" '$2 == expected {print $1; exit}'
}

wait_for_discovery() {
    local kind="$1"
    local type="$2"
    local value=""
    while (( SECONDS < deadline )); do
        if ! kill -0 "${launch_pid}" 2>/dev/null; then
            printf 'ERROR: Arena launch exited before %s discovery\n' "${kind}" >&2
            tail -100 "${LOG_FILE}" >&2
            return 1
        fi
        if [[ "${kind}" == "action" ]]; then
            value="$(action_by_type "${type}")"
        else
            value="$(topic_by_type "${type}")"
        fi
        if [[ -n "${value}" ]]; then
            printf '%s\n' "${value}"
            return 0
        fi
        sleep 2
    done
    printf 'ERROR: timed out discovering %s type %s\n' "${kind}" "${type}" >&2
    tail -100 "${LOG_FILE}" >&2
    return 1
}

clock_topic="$(wait_for_discovery topic rosgraph_msgs/msg/Clock)"
tf_topic="$(wait_for_discovery topic tf2_msgs/msg/TFMessage)"
lidar_topic="$(wait_for_discovery topic sensor_msgs/msg/LaserScan)"
odom_topic="$(wait_for_discovery topic nav_msgs/msg/Odometry)"
nav_action="$(wait_for_discovery action nav2_msgs/action/NavigateToPose)"

timeout 20 ros2 topic echo --once "${clock_topic}" >/dev/null
timeout 20 ros2 topic echo --once "${tf_topic}" >/dev/null
timeout 20 ros2 topic echo --once "${lidar_topic}" >/dev/null
timeout 20 ros2 topic echo --once "${odom_topic}" >/dev/null

goal_log="${LOG_FILE%.log}_goal.log"
set +e
timeout 25 ros2 action send_goal "${nav_action}" \
    nav2_msgs/action/NavigateToPose \
    '{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}' \
    >"${goal_log}" 2>&1
goal_status=$?
set -e
if [[ "${goal_status}" -ne 0 && "${goal_status}" -ne 124 ]]; then
    printf 'ERROR: navigation goal command failed with status %s\n' "${goal_status}" >&2
    cat "${goal_log}" >&2
    exit 1
fi
if ! grep -q 'Goal accepted' "${goal_log}"; then
    printf 'ERROR: navigation goal was not accepted\n' >&2
    cat "${goal_log}" >&2
    exit 1
fi

crash_count="$(grep -Eic 'process has died|segmentation fault|core dumped' "${LOG_FILE}" || true)"
if (( crash_count > 0 )); then
    printf 'ERROR: detected %s simulator/node crashes\n' "${crash_count}" >&2
    grep -Ei 'process has died|segmentation fault|core dumped' "${LOG_FILE}" >&2 || true
    exit 1
fi

printf 'Arena smoke PASS: clock=%s tf=%s lidar=%s odom=%s action=%s\n' \
    "${clock_topic}" "${tf_topic}" "${lidar_topic}" "${odom_topic}" "${nav_action}"
