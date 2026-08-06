#!/usr/bin/env bash
set -euo pipefail

snapshot_file="${RAMP_CAPTURE_OUTPUT:?RAMP_CAPTURE_OUTPUT is required}"
window_info_file="${RAMP_CAPTURE_WINDOW_INFO:?RAMP_CAPTURE_WINDOW_INFO is required}"
capture_log="${RAMP_CAPTURE_LOG:?RAMP_CAPTURE_LOG is required}"
xvfb_log="${RAMP_CAPTURE_XVFB_LOG:?RAMP_CAPTURE_XVFB_LOG is required}"
episode_id="${RAMP_EPISODE_ID:?RAMP_EPISODE_ID is required}"
display_number="${RAMP_CAPTURE_DISPLAY_NUMBER:-96}"
minimum_samples="${RAMP_CAPTURE_MINIMUM_SAMPLES:-60}"
arena_headless="${RAMP_CAPTURE_ARENA_HEADLESS:-0}"

[[ "${snapshot_file}" == /workspace/* && "${window_info_file}" == /workspace/* ]] || {
    echo "ERROR: capture artifacts must remain under /workspace" >&2
    exit 2
}
[[ "${display_number}" =~ ^[0-9]+$ ]] && ((display_number >= 90 && display_number <= 199)) || {
    echo "ERROR: RAMP_CAPTURE_DISPLAY_NUMBER must be an integer in [90, 199]" >&2
    exit 2
}
[[ "${minimum_samples}" =~ ^[0-9]+$ ]] && ((minimum_samples >= 1)) || {
    echo "ERROR: RAMP_CAPTURE_MINIMUM_SAMPLES must be a positive integer" >&2
    exit 2
}
[[ "${arena_headless}" == "0" ]] || {
    echo "ERROR: a Gazebo GUI capture requires RAMP_CAPTURE_ARENA_HEADLESS=0" >&2
    exit 2
}

mkdir -p "$(dirname "${snapshot_file}")" "$(dirname "${capture_log}")"
if [[ -e "${snapshot_file}" || -e "${window_info_file}" ]]; then
    echo "ERROR: refusing to overwrite an existing runtime capture" >&2
    exit 2
fi
: >"${capture_log}"
: >"${xvfb_log}"

# Arena's optional RViz task panel queries this reserved workspace as soon as
# headless mode is disabled.  The pinned minimal image omits the empty folder,
# which makes that read-only GUI query crash task_generator before Nav2 can
# activate.  Recreate only the expected empty directory in the disposable
# container layer; evaluation scenarios and planner parameters are unchanged.
mkdir -p \
    /opt/arena_ws/install/arena_simulation_setup/share/arena_simulation_setup/worlds/.generated/scenarios

display=":${display_number}"
export DISPLAY="${display}"
export LIBGL_ALWAYS_SOFTWARE=1
Xvfb "${display}" -screen 0 1600x1000x24 +extension GLX +render -noreset \
    >>"${xvfb_log}" 2>&1 &
xvfb_pid=$!
capture_pid=""
cleanup_started=0

cleanup() {
    if ((cleanup_started)); then
        return
    fi
    cleanup_started=1
    if [[ -n "${capture_pid}" ]] && kill -0 "${capture_pid}" 2>/dev/null; then
        kill -TERM "${capture_pid}" 2>/dev/null || true
        wait "${capture_pid}" 2>/dev/null || true
    fi
    if kill -0 "${xvfb_pid}" 2>/dev/null; then
        kill -TERM "${xvfb_pid}" 2>/dev/null || true
        wait "${xvfb_pid}" 2>/dev/null || true
    fi
    host_uid="${RAMP_HOST_UID:-}"
    host_gid="${RAMP_HOST_GID:-}"
    if [[ "${host_uid}" =~ ^[0-9]+$ && "${host_gid}" =~ ^[0-9]+$ ]]; then
        for artifact in \
            "${snapshot_file}" "${window_info_file}" "${capture_log}" "${xvfb_log}"; do
            [[ ! -e "${artifact}" ]] || chown "${host_uid}:${host_gid}" "${artifact}"
        done
    fi
}
trap cleanup EXIT INT TERM

display_deadline=$((SECONDS + 20))
until DISPLAY="${display}" python3 -c \
    'from PyQt5.QtWidgets import QApplication; app=QApplication([]); assert app.primaryScreen()' \
    >>"${xvfb_log}" 2>&1; do
    if ! kill -0 "${xvfb_pid}" 2>/dev/null || ((SECONDS >= display_deadline)); then
        echo "ERROR: capture Xvfb did not become ready" >&2
        tail -80 "${xvfb_log}" >&2
        exit 1
    fi
    sleep 1
done

stream_file="/workspace/data/raw/${episode_id}.jsonl"
readarray -t camera_values < <(python3 - "${RAMP_SCENARIO}" <<'PY'
import json
import math
import sys

scenario = json.load(open(sys.argv[1], encoding="utf-8"))
robot = scenario["robots"][0]
start_x, start_y = map(float, robot["start"][:2])
goal_x, goal_y = map(float, robot["goal"][:2])
dx = goal_x - start_x
dy = goal_y - start_y
span = math.hypot(dx, dy)
if span < 1.0e-6:
    raise SystemExit("capture camera requires distinct robot start and goal")
unit_x, unit_y = dx / span, dy / span
left_x, left_y = -unit_y, unit_x
focus_x, focus_y = (start_x + goal_x) / 2.0, (start_y + goal_y) / 2.0
back = max(5.0, min(8.0, span * 0.45))
side = max(3.0, min(5.0, span * 0.30))
height = max(8.0, min(11.0, span * 0.60))
camera_x = focus_x - back * unit_x - side * left_x
camera_y = focus_y - back * unit_y - side * left_y
look_x, look_y = focus_x - camera_x, focus_y - camera_y
yaw = math.atan2(look_y, look_x)
pitch = math.atan2(height, math.hypot(look_x, look_y))
half_yaw, half_pitch = yaw / 2.0, pitch / 2.0
qx = -math.sin(half_pitch) * math.sin(half_yaw)
qy = math.sin(half_pitch) * math.cos(half_yaw)
qz = math.cos(half_pitch) * math.sin(half_yaw)
qw = math.cos(half_pitch) * math.cos(half_yaw)
values = (camera_x, camera_y, height, qx, qy, qz, qw)
for value in values:
    print(f"{value:.9f}")
print(
    json.dumps(
        {
            "framing": "scenario_midpoint_oblique",
            "focus_xyz": [focus_x, focus_y, 0.0],
            "pose_xyz_xyzw": [*values],
            "transport_service": "/gui/move_to/pose",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
)
PY
)
camera_context="${camera_values[7]}"
(
    sample_deadline=$((SECONDS + 180))
    sample_count=0
    while ((SECONDS < sample_deadline)); do
        if [[ -s "${stream_file}" ]]; then
            sample_count="$(wc -l <"${stream_file}")"
            if ((sample_count >= minimum_samples)); then
                break
            fi
        fi
        sleep 0.25
    done
    if ((sample_count < minimum_samples)); then
        echo "ERROR: episode did not produce ${minimum_samples} samples before capture deadline" >&2
        exit 1
    fi
    echo "Framing a live Gazebo GUI after ${sample_count} logged simulator samples."
    camera_response="$(
        ign service -s /gui/move_to/pose \
            --reqtype ignition.msgs.GUICamera \
            --reptype ignition.msgs.Boolean \
            --timeout 5000 \
            --req "pose { position { x: ${camera_values[0]} y: ${camera_values[1]} z: ${camera_values[2]} } orientation { x: ${camera_values[3]} y: ${camera_values[4]} z: ${camera_values[5]} w: ${camera_values[6]} } }"
    )"
    echo "${camera_response}"
    grep -Fq 'data: true' <<<"${camera_response}" || {
        echo "ERROR: Gazebo rejected the reproducible GUI camera pose" >&2
        exit 1
    }
    sleep 3
    echo "Capturing the populated Gazebo Scene3D viewport."
    DISPLAY="${display}" python3 /workspace/scripts/arena/capture_x11_window.py \
        --output "${snapshot_file}" \
        --info-output "${window_info_file}" \
        --title-pattern 'Gazebo|gz sim' \
        --capture-context "${camera_context}" \
        --timeout 90
) >>"${capture_log}" 2>&1 &
capture_pid=$!

set +e
PATH="/workspace/scripts/arena/capture_shims:${PATH}" \
    bash /workspace/scripts/arena/run_baseline_episode_inner.sh
baseline_status=$?
if ((baseline_status != 0)) && kill -0 "${capture_pid}" 2>/dev/null; then
    kill -TERM "${capture_pid}" 2>/dev/null || true
fi
wait "${capture_pid}"
capture_status=$?
set -e
capture_pid=""

if ((baseline_status != 0)); then
    echo "ERROR: live navigation episode failed during screenshot capture" >&2
    exit "${baseline_status}"
fi
if ((capture_status != 0)) || [[ ! -s "${snapshot_file}" || ! -s "${window_info_file}" ]]; then
    echo "ERROR: Gazebo window capture failed" >&2
    tail -120 "${capture_log}" >&2
    exit 1
fi

echo "Live Gazebo GUI capture PASS: ${snapshot_file}"
