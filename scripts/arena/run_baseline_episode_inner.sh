#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${RAMP_SCENARIO:?RAMP_SCENARIO is required}"
TIMEOUT_S="${RAMP_EPISODE_TIMEOUT_S:-180}"
SCENARIO_TARGET="/opt/arena_ws/install/arena_simulation_setup/share/arena_simulation_setup/worlds/map_empty/scenarios/default.json"

readarray -t scenario_values < <(python3 - "${SCENARIO}" <<'PY'
import json
import sys

scenario = json.load(open(sys.argv[1], encoding="utf-8"))
metadata = scenario.get("ramp_metadata", {})
robot = scenario["robots"][0]
print(metadata.get("scenario_id", ""))
print(metadata.get("seed", ""))
print(metadata.get("split", ""))
print(metadata.get("map_id", ""))
print(robot["goal"][0])
print(robot["goal"][1])
print(robot["goal"][2] if len(robot["goal"]) > 2 else 0.0)
print(robot["start"][0])
print(robot["start"][1])
print(robot["start"][2] if len(robot["start"]) > 2 else 0.0)
PY
)
scenario_id="${scenario_values[0]}"
seed="${scenario_values[1]}"
split="${scenario_values[2]}"
map_id="${scenario_values[3]}"
goal_x="${scenario_values[4]}"
goal_y="${scenario_values[5]}"
goal_yaw="${scenario_values[6]}"
start_x="${scenario_values[7]}"
start_y="${scenario_values[8]}"
start_yaw="${scenario_values[9]}"
if [[ -z "${scenario_id}" || -z "${seed}" || -z "${split}" || -z "${map_id}" ]]; then
    echo "ERROR: scenario is missing required ramp_metadata" >&2
    exit 2
fi
episode_id="${RAMP_EPISODE_ID:-${scenario_id}_base_dwb}"
output_directory="/workspace/data/raw"
RUNTIME_LOG="${RAMP_BASELINE_RUNTIME_LOG:-/workspace/outputs/logs/baseline/${episode_id}_runtime.log}"
STATUS_LOG="${RAMP_BASELINE_STATUS_LOG:-/workspace/outputs/logs/baseline/${episode_id}_status.log}"
outcome_file="${output_directory}/${episode_id}.outcome.json"
stream_file="${output_directory}/${episode_id}.jsonl"
if [[ -e "${outcome_file}" || -e "${stream_file}" ]]; then
    echo "ERROR: refusing to overwrite existing episode: ${episode_id}" >&2
    exit 2
fi
mkdir -p "${output_directory}" "$(dirname "${RUNTIME_LOG}")"
: >"${RUNTIME_LOG}"
: >"${STATUS_LOG}"
cp "${SCENARIO}" "${SCENARIO_TARGET}"

export LIBGL_ALWAYS_SOFTWARE=1
setsid xvfb-run -a -s '-screen 0 1280x720x24' \
    ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo human:=dummy headless:=2 robot:=jackal local_planner:=dwb world:=map_empty \
    tm_robots:=scenario tm_obstacles:=scenario use_sim_time:=true \
    >>"${RUNTIME_LOG}" 2>&1 &
launch_pid=$!
logger_pid=""
actor_pid=""
monitor_pid=""
cleanup_started=0

stop_logger() {
    if [[ -n "${logger_pid}" ]] && kill -0 "${logger_pid}" 2>/dev/null; then
        kill -INT "${logger_pid}" 2>/dev/null || true
        for _ in $(seq 1 15); do
            kill -0 "${logger_pid}" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "${logger_pid}" 2>/dev/null; then
            kill -TERM "${logger_pid}" 2>/dev/null || true
        fi
        wait "${logger_pid}" 2>/dev/null || true
    fi
}

stop_actor_controller() {
    if [[ -n "${actor_pid}" ]] && kill -0 "${actor_pid}" 2>/dev/null; then
        kill -INT "${actor_pid}" 2>/dev/null || true
        wait "${actor_pid}" 2>/dev/null || true
    fi
}

stop_monitor() {
    if [[ -n "${monitor_pid}" ]] && kill -0 "${monitor_pid}" 2>/dev/null; then
        kill -TERM "${monitor_pid}" 2>/dev/null || true
        wait "${monitor_pid}" 2>/dev/null || true
    fi
}

cleanup() {
    if (( cleanup_started )); then
        return
    fi
    cleanup_started=1
    printf '[RAMP_BASELINE] cleanup_started\n' >>"${RUNTIME_LOG}"
    stop_logger
    stop_actor_controller
    stop_monitor
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
    printf '[RAMP_BASELINE] cleanup_complete\n' >>"${RUNTIME_LOG}"
    host_uid="${RAMP_HOST_UID:-}"
    host_gid="${RAMP_HOST_GID:-}"
    if [[ "${host_uid}" =~ ^[0-9]+$ && "${host_gid}" =~ ^[0-9]+$ ]]; then
        for artifact in \
            "${stream_file}" "${outcome_file}" "${output_directory}/${episode_id}.metadata.json" \
            "${RUNTIME_LOG}" "${STATUS_LOG}"; do
            [[ ! -e "${artifact}" ]] || chown "${host_uid}:${host_gid}" "${artifact}"
        done
        chown "${host_uid}:${host_gid}" "$(dirname "${RUNTIME_LOG}")" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

deadline=$((SECONDS + 120))
nav_action=""
odom_topic=""
scan_topic=""
cmd_topic=""
path_topic=""
while (( SECONDS < deadline )); do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
        echo "ERROR: Arena exited before baseline topics became ready" >&2
        tail -120 "${RUNTIME_LOG}" >&2
        exit 1
    fi
    nav_action="$(ros2 action list -t 2>/dev/null | awk '$2 == "[nav2_msgs/action/NavigateToPose]" {print $1; exit}')"
    odom_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[nav_msgs/msg/Odometry]" {print $1; exit}')"
    scan_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[sensor_msgs/msg/LaserScan]" {print $1; exit}')"
    cmd_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[geometry_msgs/msg/Twist]" && $1 ~ /cmd_vel/ {print $1; exit}')"
    path_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[nav_msgs/msg/Path]" {print $1; exit}')"
    if [[ -n "${nav_action}" && -n "${odom_topic}" && -n "${scan_topic}" && -n "${cmd_topic}" ]]; then
        break
    fi
    sleep 2
done
if [[ -z "${nav_action}" || -z "${odom_topic}" || -z "${scan_topic}" || -z "${cmd_topic}" ]]; then
    echo "ERROR: timed out waiting for required baseline topics" >&2
    ros2 topic list -t >&2 || true
    exit 1
fi
if [[ -z "${path_topic}" ]]; then
    path_topic="/__ramp_unused/path"
fi
project_commit="${RAMP_PROJECT_COMMIT:?RAMP_PROJECT_COMMIT is required}"
ramp_ros_prefix="$(ros2 pkg prefix ramp_ros)"
"${ramp_ros_prefix}/lib/ramp_ros/scenario_actor_controller" --ros-args \
    -p use_sim_time:=true \
    -p scenario_file:="${SCENARIO}" \
    -p set_pose_service:=/world/default/set_pose \
    -p spawn_service:=/world/default/create \
    -p privileged_humans_topic:=/ramp/privileged/humans \
    -p update_frequency_hz:="${RAMP_ACTOR_UPDATE_HZ:-2.0}" \
    >>"${RUNTIME_LOG}" 2>&1 &
actor_pid=$!
timeout_value="$(python3 -c 'import sys; print(float(sys.argv[1]))' "${TIMEOUT_S}")"
"${ramp_ros_prefix}/lib/ramp_ros/episode_logger" --ros-args \
    -p use_sim_time:=true \
    -p episode_id:="${episode_id}" \
    -p scenario_id:="${scenario_id}" \
    -p map_id:="${map_id}" \
    -p seed:="${seed}" \
    -p split:="${split}" \
    -p planner_id:=dwb \
    -p source_policy:=base \
    -p arena_commit:=c2ff4a87e8686013b53f1e9cd8b01b3ab04fbce4 \
    -p project_commit:="${project_commit}" \
    -p output_directory:="${output_directory}" \
    -p episode_timeout_s:="${timeout_value}" \
    -p goal_x:="${goal_x}" -p goal_y:="${goal_y}" -p goal_yaw:="${goal_yaw}" \
    -p robot_start_x:="${start_x}" -p robot_start_y:="${start_y}" \
    -p robot_start_yaw:="${start_yaw}" \
    -p odom_topic:="${odom_topic}" -p scan_topic:="${scan_topic}" \
    -p cmd_vel_topic:="${cmd_topic}" -p base_cmd_vel_topic:="${cmd_topic}" \
    -p global_path_topic:="${path_topic}" \
    -p nav_status_topic:="${nav_action}/_action/status" \
    -p collision_topic:=/__ramp_unused/collision \
    >>"${RUNTIME_LOG}" 2>&1 &
logger_pid=$!

wall_timeout="$(python3 -c 'import math,sys; print(math.ceil(float(sys.argv[1]) * 3.0 + 60.0))' "${TIMEOUT_S}")"
python3 /workspace/scripts/arena/wait_for_nav_status.py \
    --topic "${nav_action}/_action/status" --timeout "${wall_timeout}" \
    >"${STATUS_LOG}" 2>&1 &
monitor_pid=$!
wall_deadline=$((SECONDS + wall_timeout))
wall_guard_expired=0
while kill -0 "${logger_pid}" 2>/dev/null; do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
        echo "ERROR: Arena exited before the episode reached a terminal outcome" >&2
        break
    fi
    if (( SECONDS >= wall_deadline )); then
        echo "ERROR: wall-clock guard expired before simulated episode timeout" >&2
        wall_guard_expired=1
        break
    fi
    sleep 1
done
if (( wall_guard_expired )); then
    stop_logger
fi
set +e
wait "${logger_pid}" 2>/dev/null
logger_status=$?
set -e
logger_pid=""
if kill -0 "${monitor_pid}" 2>/dev/null; then
    stop_monitor
    monitor_status=143
else
    set +e
    wait "${monitor_pid}" 2>/dev/null
    monitor_status=$?
    set -e
fi
monitor_pid=""

if [[ ! -s "${stream_file}" || ! -s "${outcome_file}" ]]; then
    echo "ERROR: episode logger did not produce non-empty stream and outcome files" >&2
    tail -120 "${RUNTIME_LOG}" >&2
    exit 1
fi
outcome="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["outcome"])' "${outcome_file}")"
sample_count="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sample_count"])' "${outcome_file}")"
if [[ "${outcome}" == "SIMULATOR_FAILURE" || "${outcome}" == "INVALID_RESET" ]]; then
    echo "ERROR: invalid baseline episode outcome: ${outcome}" >&2
    cat "${outcome_file}" >&2
    exit 1
fi
crash_count="$(grep -Eic 'process has died|segmentation fault|core dumped|Traceback \(most recent call last\)' "${RUNTIME_LOG}" || true)"
if (( crash_count > 0 )); then
    echo "ERROR: detected ${crash_count} runtime crashes during baseline episode" >&2
    grep -Ei 'process has died|segmentation fault|core dumped|Traceback \(most recent call last\)' "${RUNTIME_LOG}" >&2
    exit 1
fi
printf 'Baseline episode PASS: episode=%s outcome=%s samples=%s monitor_status=%s\n' \
    "${episode_id}" "${outcome}" "${sample_count}" "${monitor_status}"
