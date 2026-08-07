#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
default_scenario="scenarios/generated/moderate_v5/arena/map_empty/doorway_bottleneck_medium_validation_moderate_v5_r00_s75110.json"
scenario_value="${SCENARIO:-${1:-${default_scenario}}}"
if [[ "${scenario_value}" == /* ]]; then
    scenario="${scenario_value}"
else
    scenario="${PROJECT_ROOT}/${scenario_value}"
fi
[[ -f "${scenario}" ]] || {
    echo "ERROR: capture scenario does not exist: ${scenario_value}" >&2
    exit 2
}
scenario_relative="${scenario#"${PROJECT_ROOT}/"}"
[[ "${scenario_relative}" != "${scenario}" ]] || {
    echo "ERROR: capture scenario must be inside PROJECT_ROOT" >&2
    exit 2
}
scenario_split="$(python3 - "${scenario}" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload.get("ramp_metadata", {}).get("split", ""))
PY
)"
[[ "${scenario_split}" == "validation" ]] || {
    echo "ERROR: paper runtime capture requires a validation scenario, got: ${scenario_split:-missing}" >&2
    exit 2
}

capture_id="${RAMP_CAPTURE_ID:-gazebo_doorway_bottleneck_medium}"
[[ "${capture_id}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
    echo "ERROR: RAMP_CAPTURE_ID must contain only lowercase letters, digits, _ or -" >&2
    exit 2
}
ros_domain_id="${ROS_DOMAIN_ID:-226}"
[[ "${ros_domain_id}" =~ ^[0-9]+$ ]] && ((ros_domain_id <= 232)) || {
    echo "ERROR: ROS_DOMAIN_ID must be an integer in [0, 232]" >&2
    exit 2
}
display_number="${RAMP_CAPTURE_DISPLAY_NUMBER:-196}"
[[ "${display_number}" =~ ^[0-9]+$ ]] && \
    ((display_number >= 90 && display_number <= 199)) || {
    echo "ERROR: RAMP_CAPTURE_DISPLAY_NUMBER must be an integer in [90, 199]" >&2
    exit 2
}

gazebo_partition="${GZ_PARTITION:-pgrr_runtime_capture_${capture_id}}"
[[ "${gazebo_partition}" =~ ^[A-Za-z0-9_.-]+$ ]] || {
    echo "ERROR: GZ_PARTITION contains unsupported characters" >&2
    exit 2
}
captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
timestamp_token="$(date -u +%Y%m%dT%H%M%SZ)"
episode_id="runtime_capture_${capture_id}_${timestamp_token}_$$"
output_directory="${PROJECT_ROOT}/outputs/figures/runtime"
log_directory="${PROJECT_ROOT}/outputs/logs/runtime_capture"
screenshot="${output_directory}/${capture_id}.png"
window_info="${output_directory}/${capture_id}.window.json"
metadata="${output_directory}/${capture_id}.metadata.json"
paper_copy="${PROJECT_ROOT}/paper/figures/runtime_${capture_id}.png"
runtime_log="${log_directory}/${episode_id}_runtime.log"
capture_log="${log_directory}/${episode_id}_capture.log"
xvfb_log="${log_directory}/${episode_id}_xvfb.log"
driver_log="${log_directory}/${episode_id}_driver.log"

for target in "${screenshot}" "${window_info}" "${metadata}" "${paper_copy}"; do
    if [[ -e "${target}" ]]; then
        echo "ERROR: refusing to overwrite existing capture artifact: ${target#"${PROJECT_ROOT}/"}" >&2
        exit 2
    fi
done
mkdir -p "${output_directory}" "${log_directory}" "$(dirname "${paper_copy}")"

arena_image="${ARENA_IMAGE:-ramp-arena:humble}"
arena_image_id="$(docker image inspect "${arena_image}" --format '{{.Id}}')"
project_commit="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)"
export RAMP_ENABLE_CMD_MUX=1
export RAMP_DISABLE_AUTO_RESET=1

set +e
"${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    env \
    RAMP_SCENARIO="/workspace/${scenario_relative}" \
    RAMP_EPISODE_ID="${episode_id}" \
    RAMP_EPISODE_TIMEOUT_S="${RAMP_EPISODE_TIMEOUT_S:-120}" \
    RAMP_REPLICATE="" \
    RAMP_ACTOR_UPDATE_HZ="${RAMP_ACTOR_UPDATE_HZ:-5.0}" \
    RAMP_TTC_THRESHOLD_S="1.5" \
    RAMP_SOURCE_POLICY="base" \
    RAMP_PROJECT_COMMIT="${project_commit}" \
    RAMP_HOST_UID="$(id -u)" \
    RAMP_HOST_GID="$(id -g)" \
    ROS_DOMAIN_ID="${ros_domain_id}" \
    GZ_PARTITION="${gazebo_partition}" \
    IGN_PARTITION="${gazebo_partition}" \
    RAMP_CAPTURE_DISPLAY_NUMBER="${display_number}" \
    RAMP_CAPTURE_ARENA_HEADLESS="0" \
    RAMP_CAPTURE_MINIMUM_SAMPLES="${RAMP_CAPTURE_MINIMUM_SAMPLES:-60}" \
    RAMP_CAPTURE_OUTPUT="/workspace/${screenshot#"${PROJECT_ROOT}/"}" \
    RAMP_CAPTURE_WINDOW_INFO="/workspace/${window_info#"${PROJECT_ROOT}/"}" \
    RAMP_CAPTURE_LOG="/workspace/${capture_log#"${PROJECT_ROOT}/"}" \
    RAMP_CAPTURE_XVFB_LOG="/workspace/${xvfb_log#"${PROJECT_ROOT}/"}" \
    RAMP_BASELINE_RUNTIME_LOG="/workspace/${runtime_log#"${PROJECT_ROOT}/"}" \
    bash /workspace/scripts/arena/capture_gazebo_snapshot_inner.sh \
    2>&1 | tee "${driver_log}"
capture_status=${PIPESTATUS[0]}
set -e
if ((capture_status != 0)); then
    echo "ERROR: runtime screenshot capture failed; see ${driver_log#"${PROJECT_ROOT}/"}" >&2
    exit "${capture_status}"
fi

outcome="${PROJECT_ROOT}/data/raw/${episode_id}.outcome.json"
python3 "${PROJECT_ROOT}/scripts/arena/record_runtime_capture.py" \
    --root "${PROJECT_ROOT}" \
    --screenshot "${screenshot}" \
    --paper-copy "${paper_copy}" \
    --metadata-output "${metadata}" \
    --window-info "${window_info}" \
    --scenario "${scenario}" \
    --outcome "${outcome}" \
    --runtime-log "${runtime_log}" \
    --capture-log "${capture_log}" \
    --git-commit "${project_commit}" \
    --arena-image-id "${arena_image_id}" \
    --ros-domain-id "${ros_domain_id}" \
    --gazebo-partition "${gazebo_partition}" \
    --episode-id "${episode_id}" \
    --captured-at "${captured_at}"

echo "Gazebo screenshot: ${screenshot#"${PROJECT_ROOT}/"}"
echo "Paper copy:       ${paper_copy#"${PROJECT_ROOT}/"}"
echo "Provenance:       ${metadata#"${PROJECT_ROOT}/"}"
