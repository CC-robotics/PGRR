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
source_policy="${RAMP_SOURCE_POLICY:-base}"
project_root_resolved="$(readlink -f -- "${PROJECT_ROOT}")"

runtime_config_path() {
    local configured_path="${1:?configured config path is required}"
    local resolved_path=""
    if [[ "${configured_path}" != /* ]]; then
        configured_path="${PROJECT_ROOT}/${configured_path}"
    fi
    resolved_path="$(readlink -f -- "${configured_path}")"
    if [[ ! -f "${resolved_path}" ]]; then
        echo "ERROR: runtime config does not exist: ${configured_path}" >&2
        return 2
    fi
    case "${resolved_path}" in
        "${project_root_resolved}"/*) ;;
        *)
            echo "ERROR: runtime config must be inside PROJECT_ROOT: ${resolved_path}" >&2
            return 2
            ;;
    esac
    printf '/workspace/%s\n' "${resolved_path#"${project_root_resolved}"/}"
}

recovery_config="$(runtime_config_path "${RAMP_RECOVERY_CONFIG:-configs/failure/recovery_state_machine.yaml}")"
failure_rules_config="$(runtime_config_path "${RAMP_FAILURE_RULES_CONFIG:-configs/failure/rules.yaml}")"
default_model_path="/workspace/checkpoints/bc/uniform_scenario/best.onnx"
case "${source_policy}" in
    pgrr)
        default_model_path="/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx"
        ;;
    mwbc)
        default_model_path="/workspace/checkpoints/bc/mwbc_scenario/best.onnx"
        ;;
esac
optional_runtime_environment=()
if [[ -n "${RAMP_TAU_ON:-}" ]]; then
    optional_runtime_environment+=("RAMP_TAU_ON=${RAMP_TAU_ON}")
fi
exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    env \
    RAMP_SCENARIO="/workspace/${relative}" \
    RAMP_EPISODE_ID="${RAMP_EPISODE_ID:-}" \
    RAMP_EPISODE_TIMEOUT_S="${RAMP_EPISODE_TIMEOUT_S:-180}" \
    RAMP_REPLICATE="${RAMP_REPLICATE:-}" \
    RAMP_ACTOR_UPDATE_HZ="${RAMP_ACTOR_UPDATE_HZ:-2.0}" \
    RAMP_TTC_THRESHOLD_S="${RAMP_TTC_THRESHOLD_S:-1.5}" \
    RAMP_RECOVERY_CONFIG="${recovery_config}" \
    RAMP_FAILURE_RULES_CONFIG="${failure_rules_config}" \
    "${optional_runtime_environment[@]}" \
    RAMP_SOURCE_POLICY="${source_policy}" \
    RAMP_BC_MODEL_PATH="${RAMP_BC_MODEL_PATH:-${default_model_path}}" \
    RAMP_CHECKPOINT_SHA256="${RAMP_CHECKPOINT_SHA256:-}" \
    RAMP_HOST_UID="$(id -u)" \
    RAMP_HOST_GID="$(id -g)" \
    ROS_DOMAIN_ID="${ros_domain_id}" \
    GZ_PARTITION="${GZ_PARTITION:-ramp_default}" \
    IGN_PARTITION="${IGN_PARTITION:-${GZ_PARTITION:-ramp_default}}" \
    RAMP_PROJECT_COMMIT="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" \
    bash /workspace/scripts/arena/run_baseline_episode_inner.sh
