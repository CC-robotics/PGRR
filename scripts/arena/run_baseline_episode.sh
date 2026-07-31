#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SCENARIO="${SCENARIO:-${1:-}}"
if [[ -z "${SCENARIO}" ]]; then
    echo "Usage: SCENARIO=/absolute/path/to/scenario.json $0" >&2
    exit 2
fi
if [[ "${SCENARIO}" != /* ]]; then
    SCENARIO="${PROJECT_ROOT}/${SCENARIO}"
fi
if [[ ! -f "${SCENARIO}" ]]; then
    echo "ERROR: scenario does not exist: ${SCENARIO}" >&2
    exit 2
fi
relative="${SCENARIO#"${PROJECT_ROOT}/"}"
if [[ "${relative}" == "${SCENARIO}" ]]; then
    echo "ERROR: scenario must be inside PROJECT_ROOT for the container runtime" >&2
    exit 2
fi

ros_domain_id="${ROS_DOMAIN_ID:-1}"
if [[ ! "${ros_domain_id}" =~ ^[0-9]+$ ]] || ((ros_domain_id > 232)); then
    echo "ERROR: ROS_DOMAIN_ID must be an integer in [0, 232]: ${ros_domain_id}" >&2
    exit 2
fi

export RAMP_ENABLE_CMD_MUX=1
export RAMP_DISABLE_AUTO_RESET=1
exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    env \
    RAMP_SCENARIO="/workspace/${relative}" \
    RAMP_EPISODE_ID="${RAMP_EPISODE_ID:-}" \
    RAMP_EPISODE_TIMEOUT_S="${RAMP_EPISODE_TIMEOUT_S:-180}" \
    RAMP_ACTOR_UPDATE_HZ="${RAMP_ACTOR_UPDATE_HZ:-2.0}" \
    RAMP_TTC_THRESHOLD_S="${RAMP_TTC_THRESHOLD_S:-1.5}" \
    RAMP_SOURCE_POLICY="${RAMP_SOURCE_POLICY:-base}" \
    RAMP_BC_MODEL_PATH="${RAMP_BC_MODEL_PATH:-/workspace/checkpoints/bc/uniform_scenario/best.onnx}" \
    RAMP_HOST_UID="$(id -u)" \
    RAMP_HOST_GID="$(id -g)" \
    ROS_DOMAIN_ID="${ros_domain_id}" \
    GZ_PARTITION="${GZ_PARTITION:-ramp_default}" \
    IGN_PARTITION="${IGN_PARTITION:-${GZ_PARTITION:-ramp_default}}" \
    RAMP_PROJECT_COMMIT="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" \
    bash /workspace/scripts/arena/run_baseline_episode_inner.sh
