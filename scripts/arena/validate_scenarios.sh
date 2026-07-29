#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SCENARIO_ROOT="${SCENARIO_ROOT:-${PROJECT_ROOT}/scenarios/generated/arena/map_empty}"

if [[ -n "${CONDA_PREFIX:-}" ]]; then
    echo "ERROR: Arena validation must run outside Conda." >&2
    exit 2
fi
if [[ ! -d "${SCENARIO_ROOT}" ]]; then
    echo "ERROR: missing scenario directory: ${SCENARIO_ROOT}" >&2
    exit 2
fi

container_root="/workspace/${SCENARIO_ROOT#"${PROJECT_ROOT}/"}"
exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    python3 /workspace/scripts/arena/validate_scenarios_inner.py "${container_root}"
