#!/usr/bin/env bash
set -euo pipefail

if [[ "${RAMP_DISABLE_AUTO_RESET:-0}" != "1" ]]; then
    echo "ERROR: baseline episodes require RAMP_DISABLE_AUTO_RESET=1" >&2
    exit 2
fi

SCENARIO="${RAMP_SCENARIO:?RAMP_SCENARIO is required}"
TIMEOUT_S="${RAMP_EPISODE_TIMEOUT_S:-180}"
SOURCE_POLICY="${RAMP_SOURCE_POLICY:-base}"
TTC_THRESHOLD_S="${RAMP_TTC_THRESHOLD_S:-1.5}"
case "${SOURCE_POLICY}" in
    base)
        INTER_PLANNER="navigate_w_replanning_time"
        TERMINATE_ON_PLANNER_ABORT="true"
        ;;
    standard)
        INTER_PLANNER="navigate_to_pose_w_replanning_and_recovery"
        TERMINATE_ON_PLANNER_ABORT="true"
        ;;
    heuristic|bc|oracle)
        INTER_PLANNER="navigate_w_replanning_time"
        TERMINATE_ON_PLANNER_ABORT="false"
        ;;
    *)
        echo "ERROR: RAMP_SOURCE_POLICY must be base, standard, heuristic, bc, or oracle" >&2
        exit 2
        ;;
esac
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
static_obstacles = scenario.get("obstacles", {}).get("static", [])
print(len(static_obstacles))
print(json.dumps(static_obstacles, separators=(",", ":")))
print(str(all(obstacle.get("model") == "shelf" for obstacle in static_obstacles)).lower())
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
static_obstacle_count="${scenario_values[10]}"
static_obstacles_json="${scenario_values[11]}"
static_geometry_supported="${scenario_values[12]}"
lidar_static_collision_enabled=true
physical_static_collision_enabled=false
minimum_valid_lidar_range_m=0.0
collision_omnidirectional_absolute_distance_m=0.0
if [[ "${static_obstacle_count}" -eq 0 ]]; then
    lidar_static_collision_enabled=false
    # The Jackal body can appear below 0.34 m in the Gazebo GPU scan. Open-map
    # scenarios contain no static contact at that range, while a human proxy
    # reaches the physical collision boundary at approximately 0.36 m.
    minimum_valid_lidar_range_m=0.34
    collision_omnidirectional_absolute_distance_m=0.70
elif [[ "${static_geometry_supported}" == "true" ]]; then
    lidar_static_collision_enabled=false
    physical_static_collision_enabled=true
fi
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
    inter_planner:="${INTER_PLANNER}" \
    tm_robots:=scenario tm_obstacles:=scenario use_sim_time:=true \
    >>"${RUNTIME_LOG}" 2>&1 &
launch_pid=$!
logger_pid=""
actor_pid=""
pose_bridge_pid=""
mux_pid=""
detector_pid=""
recovery_pid=""
monitor_pid=""
cleanup_started=0

record_startup_failure() {
    local detail="${1:?startup failure detail is required}"
    [[ -e "${outcome_file}" ]] && return 0
    python3 - "${outcome_file}" "${episode_id}" "${detail}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(
    json.dumps(
        {
            "detail": sys.argv[3],
            "episode_id": sys.argv[2],
            "outcome": "SIMULATOR_FAILURE",
            "outcome_id": 4,
            "sample_count": 0,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
}

stop_pid_bounded() {
    local pid="${1:-}"
    local signal="${2:-INT}"
    local attempts="${3:-10}"
    [[ -n "${pid}" ]] || return 0
    kill -0 "${pid}" 2>/dev/null || return 0
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

stop_logger() {
    stop_pid_bounded "${logger_pid}" INT 15
}

stop_actor_controller() {
    stop_pid_bounded "${actor_pid}" INT 10
    stop_pid_bounded "${pose_bridge_pid}" INT 10
}

stop_recovery_nodes() {
    for recovery_node_pid in "${recovery_pid}" "${detector_pid}" "${mux_pid}"; do
        stop_pid_bounded "${recovery_node_pid}" INT 10
    done
}

stop_monitor() {
    stop_pid_bounded "${monitor_pid}" TERM 5
}

cleanup() {
    if (( cleanup_started )); then
        return
    fi
    cleanup_started=1
    printf '[RAMP_BASELINE] cleanup_started\n' >>"${RUNTIME_LOG}"
    stop_logger
    stop_recovery_nodes
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
map_topic=""
while (( SECONDS < deadline )); do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
        echo "ERROR: Arena exited before baseline topics became ready" >&2
        record_startup_failure "Arena exited before baseline topics became ready"
        tail -120 "${RUNTIME_LOG}" >&2
        exit 1
    fi
    nav_action="$(ros2 action list -t 2>/dev/null | awk '$2 == "[nav2_msgs/action/NavigateToPose]" {print $1; exit}')"
    odom_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[nav_msgs/msg/Odometry]" {print $1; exit}')"
    scan_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[sensor_msgs/msg/LaserScan]" {print $1; exit}')"
    cmd_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[geometry_msgs/msg/Twist]" && $1 ~ /\/cmd_vel$/ {print $1; exit}')"
    path_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[nav_msgs/msg/Path]" && $1 ~ /\/plan$/ {print $1; exit}')"
    map_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[nav_msgs/msg/OccupancyGrid]" && $1 ~ /\/map$/ {print $1; exit}')"
    if [[ -n "${nav_action}" && -n "${odom_topic}" && -n "${scan_topic}" && -n "${cmd_topic}" ]]; then
        break
    fi
    sleep 2
done
if [[ -z "${nav_action}" || -z "${odom_topic}" || -z "${scan_topic}" || -z "${cmd_topic}" ]]; then
    echo "ERROR: timed out waiting for required baseline topics" >&2
    record_startup_failure "timed out waiting for required baseline topics"
    ros2 topic list -t >&2 || true
    exit 1
fi
base_cmd_topic="${cmd_topic}"
mux_cmd_topic="${cmd_topic%cmd_vel}mux_cmd_vel"
if [[ -z "${path_topic}" ]]; then
    path_topic="/__ramp_unused/path"
fi
if [[ -z "${map_topic}" ]]; then
    map_topic="/__ramp_unused/map"
fi
project_commit="${RAMP_PROJECT_COMMIT:?RAMP_PROJECT_COMMIT is required}"
ramp_ros_prefix="$(ros2 pkg prefix ramp_ros)"
ros2 run ros_gz_bridge parameter_bridge \
    '/world/default/dynamic_pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V' \
    >>"${RUNTIME_LOG}" 2>&1 &
pose_bridge_pid=$!
"${ramp_ros_prefix}/lib/ramp_ros/goal_mux" --ros-args \
    -p use_sim_time:=true \
    -p base_cmd_vel_topic:="${base_cmd_topic}" \
    -p recovery_cmd_vel_topic:=/ramp/recovery_cmd_vel \
    -p cmd_vel_topic:="${mux_cmd_topic}" \
    -p recovery_decision_topic:=/ramp/recovery_decision \
    -p episode_start_topic:=/ramp/episode_started \
    -p wait_for_episode_start:=true \
    >>"${RUNTIME_LOG}" 2>&1 &
mux_pid=$!
"${ramp_ros_prefix}/lib/ramp_ros/scenario_actor_controller" --ros-args \
    -p use_sim_time:=true \
    -p scenario_file:="${SCENARIO}" \
    -p set_pose_service:=/world/default/set_pose \
    -p spawn_service:=/world/default/create \
    -p privileged_humans_topic:=/ramp/privileged/humans \
    -p privileged_robot_pose_topic:=/ramp/privileged/robot_pose \
    -p actual_pose_topic:=/world/default/dynamic_pose/info \
    -p actual_pose_timeout_s:=1.0 \
    -p health_topic:=/ramp/actors_healthy \
    -p episode_start_topic:=/ramp/episode_started \
    -p logger_ready_topic:=/ramp/logger_ready \
    -p odom_topic:="${odom_topic}" \
    -p nav_status_topic:="${nav_action}/_action/status" \
    -p wait_for_navigation_active:=true \
    -p robot_start_x:="${start_x}" -p robot_start_y:="${start_y}" \
    -p robot_start_yaw:="${start_yaw}" \
    -p update_frequency_hz:="${RAMP_ACTOR_UPDATE_HZ:-2.0}" \
    >>"${RUNTIME_LOG}" 2>&1 &
actor_pid=$!
if [[ "${SOURCE_POLICY}" == "heuristic" || "${SOURCE_POLICY}" == "bc" || "${SOURCE_POLICY}" == "oracle" ]]; then
    recovery_policy_type="heuristic"
    if [[ "${SOURCE_POLICY}" == "oracle" ]]; then
        recovery_policy_type="expert"
    elif [[ "${SOURCE_POLICY}" == "bc" ]]; then
        recovery_policy_type="bc"
    fi
    "${ramp_ros_prefix}/lib/ramp_ros/failure_detector" --ros-args \
        -p use_sim_time:=true \
        -p goal_x:="${goal_x}" -p goal_y:="${goal_y}" \
        -p robot_start_x:="${start_x}" -p robot_start_y:="${start_y}" \
        -p robot_start_yaw:="${start_yaw}" \
        -p odometry_is_world_frame:=true \
        -p odom_topic:="${odom_topic}" -p scan_topic:="${scan_topic}" \
        -p base_cmd_vel_topic:="${base_cmd_topic}" \
        -p ttc_threshold_s:="${TTC_THRESHOLD_S}" \
        -p minimum_valid_lidar_range_m:="${minimum_valid_lidar_range_m}" \
        -p collision_omnidirectional_absolute_distance_m:="${collision_omnidirectional_absolute_distance_m}" \
        -p nav_status_topic:="${nav_action}/_action/status" \
        -p failure_status_topic:=/ramp/failure_status \
        -p recovery_decision_topic:=/ramp/recovery_decision \
        >>"${RUNTIME_LOG}" 2>&1 &
    detector_pid=$!
    recovery_command=("${ramp_ros_prefix}/lib/ramp_ros/recovery_manager")
    if [[ "${SOURCE_POLICY}" == "bc" ]]; then
        inference_python="/workspace/.venv-inference/bin/python"
        model_path="${RAMP_BC_MODEL_PATH:-/workspace/checkpoints/bc/uniform_scenario/best.onnx}"
        if [[ ! -x "${inference_python}" || ! -f "${model_path}" ]]; then
            echo "ERROR: BC inference runtime or model is missing" >&2
            exit 2
        fi
        recovery_command=("${inference_python}" -m ramp_ros.nodes.recovery_manager_node)
    fi
    "${recovery_command[@]}" --ros-args \
        -p use_sim_time:=true \
        -p goal_x:="${goal_x}" -p goal_y:="${goal_y}" -p goal_yaw:="${goal_yaw}" \
        -p robot_start_x:="${start_x}" -p robot_start_y:="${start_y}" \
        -p robot_start_yaw:="${start_yaw}" \
        -p odometry_is_world_frame:=true \
        -p odom_topic:="${odom_topic}" -p scan_topic:="${scan_topic}" \
        -p base_cmd_vel_topic:="${base_cmd_topic}" \
        -p cmd_vel_topic:=/ramp/recovery_cmd_vel \
        -p global_path_topic:="${path_topic}" -p map_topic:="${map_topic}" \
        -p nav_status_topic:="${nav_action}/_action/status" \
        -p navigate_to_pose_action:="${nav_action}" \
        -p failure_status_topic:=/ramp/failure_status \
        -p recovery_decision_topic:=/ramp/recovery_decision \
        -p policy_type:="${recovery_policy_type}" \
        -p minimum_valid_lidar_range_m:="${minimum_valid_lidar_range_m}" \
        -p model_path:="${RAMP_BC_MODEL_PATH:-}" \
        -p privileged_humans_topic:=/ramp/privileged/humans \
        >>"${RUNTIME_LOG}" 2>&1 &
    recovery_pid=$!
fi
timeout_value="$(python3 -c 'import sys; print(float(sys.argv[1]))' "${TIMEOUT_S}")"
"${ramp_ros_prefix}/lib/ramp_ros/episode_logger" --ros-args \
    -p use_sim_time:=true \
    -p episode_id:="${episode_id}" \
    -p scenario_id:="${scenario_id}" \
    -p map_id:="${map_id}" \
    -p seed:="${seed}" \
    -p split:="${split}" \
    -p planner_id:=dwb \
    -p source_policy:="${SOURCE_POLICY}" \
    -p arena_commit:=c2ff4a87e8686013b53f1e9cd8b01b3ab04fbce4 \
    -p project_commit:="${project_commit}" \
    -p output_directory:="${output_directory}" \
    -p episode_timeout_s:="${timeout_value}" \
    -p wait_for_navigation_active:=true \
    -p navigation_activation_timeout_s:=20.0 \
    -p navigation_activation_wall_timeout_s:=90.0 \
    -p terminate_on_planner_abort:="${TERMINATE_ON_PLANNER_ABORT}" \
    -p planner_abort_grace_s:=5.0 \
    -p goal_x:="${goal_x}" -p goal_y:="${goal_y}" -p goal_yaw:="${goal_yaw}" \
    -p robot_start_x:="${start_x}" -p robot_start_y:="${start_y}" \
    -p robot_start_yaw:="${start_yaw}" \
    -p odometry_is_world_frame:=true \
    -p odom_topic:="${odom_topic}" -p scan_topic:="${scan_topic}" \
    -p cmd_vel_topic:="${mux_cmd_topic}" -p base_cmd_vel_topic:="${base_cmd_topic}" \
    -p global_path_topic:="${path_topic}" \
    -p nav_status_topic:="${nav_action}/_action/status" \
    -p collision_topic:=/__ramp_unused/collision \
    -p actor_health_topic:=/ramp/actors_healthy \
    -p privileged_robot_pose_topic:=/ramp/privileged/robot_pose \
    -p episode_start_topic:=/ramp/episode_started \
    -p logger_ready_topic:=/ramp/logger_ready \
    -p lidar_collision_distance_m:=0.12 \
    -p lidar_collision_confirmation_frames:="${RAMP_LIDAR_COLLISION_CONFIRMATION_FRAMES:-3}" \
    -p lidar_static_collision_enabled:="${lidar_static_collision_enabled}" \
    -p physical_static_collision_enabled:="${physical_static_collision_enabled}" \
    -p static_obstacles_json:="'${static_obstacles_json}'" \
    -p failure_status_topic:=/ramp/failure_status \
    -p recovery_decision_topic:=/ramp/recovery_decision \
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

if [[ ! -e "${stream_file}" || ! -s "${outcome_file}" ]]; then
    echo "ERROR: episode logger did not produce stream and outcome files" >&2
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
if [[ ! -s "${stream_file}" ]]; then
    echo "ERROR: valid episode logger outcome has an empty stream" >&2
    exit 1
fi
crash_pattern='process has died|segmentation fault|core dumped|Traceback \(most recent call last\)'
crash_count="$(
    awk '/\[RAMP_BASELINE\] cleanup_started/ {exit} {print}' "${RUNTIME_LOG}" \
        | grep -Eic "${crash_pattern}" || true
)"
if (( crash_count > 0 )); then
    echo "ERROR: detected ${crash_count} runtime crashes during baseline episode" >&2
    awk '/\[RAMP_BASELINE\] cleanup_started/ {exit} {print}' "${RUNTIME_LOG}" \
        | grep -Ei "${crash_pattern}" >&2
    exit 1
fi
printf 'Episode PASS: episode=%s policy=%s outcome=%s samples=%s monitor_status=%s\n' \
    "${episode_id}" "${SOURCE_POLICY}" "${outcome}" "${sample_count}" "${monitor_status}"
