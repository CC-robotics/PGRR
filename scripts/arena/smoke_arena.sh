#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "${PROJECT_ROOT}/scripts/bootstrap/source_runtime.sh"
if ! ros2 pkg prefix arena_bringup >/dev/null 2>&1; then
    printf 'ERROR: arena_bringup is not available; Arena Gate 0 is incomplete\n' >&2
    exit 1
fi
printf 'Arena package discovered. Full topic/action smoke assertions are added after profile introspection.\n'
exit 1
