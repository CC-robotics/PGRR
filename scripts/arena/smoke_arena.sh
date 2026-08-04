#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
profile="$(awk '/^profile:/ {print $2}' "${PROJECT_ROOT}/configs/platform/arena_profile.yaml" 2>/dev/null || true)"
if [[ "${profile}" != "arena_humble_docker" ]]; then
    printf 'ERROR: unsupported or incomplete Arena profile: %s\n' "${profile:-unset}" >&2
    exit 1
fi
# The upstream Jackal mapping still points at the removed `/odometry` Gazebo
# topic. Use the pinned project mapping so the smoke test observes the same
# ground-truth odometry and planar LiDAR interfaces as evaluated episodes.
export RAMP_ENABLE_CMD_MUX=1
exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    bash /workspace/scripts/arena/smoke_runtime_inner.sh
