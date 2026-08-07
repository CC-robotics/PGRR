#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${RAMP_STATIC_LOG:-/workspace/outputs/logs/static_navigation_runtime.log}"
GOAL_LOG="${RAMP_STATIC_GOAL_LOG:-/workspace/outputs/logs/static_navigation_goal.log}"
TIMEOUT_S="${RAMP_STATIC_TIMEOUT_S:-240}"
SCENARIO="${RAMP_STATIC_SCENARIO:-/workspace/scenarios/generated/arena/map_empty/ramp_static.json}"
SCENARIO_TARGET="/opt/arena_ws/install/arena_simulation_setup/share/arena_simulation_setup/worlds/map_empty/scenarios/default.json"
mkdir -p "$(dirname "${LOG_FILE}")"
: >"${LOG_FILE}"

python3 - "${SCENARIO}" <<'PY'
import json
import sys

scenario = json.load(open(sys.argv[1], encoding="utf-8"))
robot = scenario["robots"][0]
if scenario["obstacles"]["static"] or scenario["obstacles"]["dynamic"]:
    raise SystemExit("static acceptance scenario contains obstacles")
if len(robot["start"]) != 3 or len(robot["goal"]) != 3:
    raise SystemExit("invalid robot start/goal")
PY
cp "${SCENARIO}" "${SCENARIO_TARGET}"

export LIBGL_ALWAYS_SOFTWARE=1
setsid xvfb-run -a -s '-screen 0 1280x720x24' \
    ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo human:=dummy headless:=2 robot:=jackal local_planner:=dwb world:=map_empty \
    tm_robots:=scenario tm_obstacles:=scenario use_sim_time:=true \
    >>"${LOG_FILE}" 2>&1 &
launch_pid=$!
cleanup_started=0

cleanup() {
    if (( cleanup_started )); then
        return
    fi
    cleanup_started=1
    printf '[RAMP_STATIC] cleanup_started\n' >>"${LOG_FILE}"
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
    printf '[RAMP_STATIC] cleanup_complete\n' >>"${LOG_FILE}"
}
trap cleanup EXIT INT TERM

deadline=$((SECONDS + TIMEOUT_S))
nav_action=""
odom_topic=""
while (( SECONDS < deadline )); do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
        printf 'ERROR: Arena exited before Nav2 became ready\n' >&2
        tail -100 "${LOG_FILE}" >&2
        exit 1
    fi
    nav_action="$(ros2 action list -t 2>/dev/null | awk '$2 == "[nav2_msgs/action/NavigateToPose]" {print $1; exit}')"
    odom_topic="$(ros2 topic list -t 2>/dev/null | awk '$2 == "[nav_msgs/msg/Odometry]" {print $1; exit}')"
    if [[ -n "${nav_action}" && -n "${odom_topic}" ]]; then
        break
    fi
    sleep 2
done
if [[ -z "${nav_action}" || -z "${odom_topic}" ]]; then
    printf 'ERROR: timed out waiting for Nav2 action and odometry\n' >&2
    tail -100 "${LOG_FILE}" >&2
    exit 1
fi

timeout 20 ros2 topic echo --once "${odom_topic}" >"${GOAL_LOG%.log}_start_odom.txt"
set +e
timeout 160 python3 /workspace/scripts/arena/wait_for_nav_status.py \
    --topic "${nav_action}/_action/status" --timeout 150 \
    >"${GOAL_LOG}" 2>&1
goal_status=$?
set -e
timeout 20 ros2 topic echo --once "${odom_topic}" >"${GOAL_LOG%.log}_end_odom.txt"

if [[ "${goal_status}" -ne 0 ]]; then
    printf 'ERROR: static navigation command exited with status %s\n' "${goal_status}" >&2
    cat "${GOAL_LOG}" >&2
    exit 1
fi
if ! grep -q 'GOAL_REACHED' "${GOAL_LOG}"; then
    printf 'ERROR: task-generated static goal did not reach STATUS_SUCCEEDED\n' >&2
    cat "${GOAL_LOG}" >&2
    exit 1
fi
crash_count="$(grep -Eic 'process has died|segmentation fault|core dumped' "${LOG_FILE}" || true)"
if (( crash_count > 0 )); then
    printf 'ERROR: detected %s runtime crashes during static navigation\n' "${crash_count}" >&2
    grep -Ei 'process has died|segmentation fault|core dumped' "${LOG_FILE}" >&2
    exit 1
fi
printf 'Static navigation PASS: action=%s odom=%s goal=(22.0,12.0)\n' "${nav_action}" "${odom_topic}"
