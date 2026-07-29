#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

exec "${PROJECT_ROOT}/scripts/bootstrap/arena_container.sh" \
    python3 /workspace/tests/integration/failure_detector_ros_smoke.py
