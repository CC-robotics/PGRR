#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    env \
    RAMP_STATIC_TIMEOUT_S="${RAMP_STATIC_TIMEOUT_S:-240}" \
    bash /workspace/scripts/arena/static_navigation_inner.sh
