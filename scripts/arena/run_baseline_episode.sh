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

exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    env \
    RAMP_SCENARIO="/workspace/${relative}" \
    RAMP_EPISODE_ID="${RAMP_EPISODE_ID:-}" \
    RAMP_EPISODE_TIMEOUT_S="${RAMP_EPISODE_TIMEOUT_S:-180}" \
    RAMP_PROJECT_COMMIT="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" \
    bash /workspace/scripts/arena/run_baseline_episode_inner.sh
