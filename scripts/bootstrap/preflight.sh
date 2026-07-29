#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARENA_WS="${ARENA_WS:-${HOME}/arena5_ws}"
REPORT="${PROJECT_ROOT}/docs/environment_report.txt"
mkdir -p "$(dirname "${REPORT}")"

capture() {
    printf 'RAMP environment preflight\n'
    printf 'captured_at=%s\n' "$(date --iso-8601=seconds)"
    printf 'project_root=%s\n' "${PROJECT_ROOT}"
    printf 'arena_ws=%s\n' "${ARENA_WS}"
    printf '\n[uname]\n'
    uname -a
    printf '\n[os-release]\n'
    sed -n '1,30p' /etc/os-release
    printf '\n[cpu]\n'
    lscpu
    printf '\n[memory]\n'
    free -h
    printf '\n[disk]\n'
    df -h "${PROJECT_ROOT}"
    printf '\n[python]\n'
    command -v python3 || true
    python3 --version || true
    printf '\n[conda]\n'
    command -v conda || true
    conda --version 2>/dev/null || true
    printf '\n[mamba]\n'
    command -v mamba || true
    printf '\n[git]\n'
    git --version || true
    printf '\n[ros2 inherited]\n'
    command -v ros2 || true
    printf 'ROS_DISTRO=%s\n' "${ROS_DISTRO:-}"
    printf '\n[ros2 humble]\n'
    if [[ -r /opt/ros/humble/setup.bash ]]; then
        env -i HOME="${HOME}" USER="${USER:-}" PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash --noprofile --norc -c \
            'source /opt/ros/humble/setup.bash; command -v ros2; printf "ROS_DISTRO=%s\n" "$ROS_DISTRO"; ros2 pkg list | wc -l'
    else
        printf 'not installed\n'
    fi
    printf '\n[gpu]\n'
    command -v nvidia-smi || true
    nvidia-smi 2>/dev/null || true
    printf '\n[docker]\n'
    command -v docker || true
    docker --version 2>/dev/null || true
    printf '\n[active environments]\n'
    printf 'CONDA_PREFIX=%s\n' "${CONDA_PREFIX:-}"
    printf 'CONDA_DEFAULT_ENV=%s\n' "${CONDA_DEFAULT_ENV:-}"
    printf 'VIRTUAL_ENV=%s\n' "${VIRTUAL_ENV:-}"
    printf '\n[arena discovery]\n'
    if [[ -d "${ARENA_WS}" ]]; then
        find "${ARENA_WS}" -maxdepth 3 -type f \( -name arena -o -name arena.bash -o -name setup.bash \) -print
    else
        printf 'workspace absent\n'
    fi
}

capture | tee "${REPORT}"

available_kib="$(df -Pk "${PROJECT_ROOT}" | awk 'NR==2 {print $4}')"
memory_kib="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if (( available_kib < 40 * 1024 * 1024 )); then
    printf 'ERROR: less than 40 GiB free disk space\n' >&2
    exit 1
fi
if (( memory_kib < 16 * 1024 * 1024 )); then
    printf 'WARNING: less than the recommended 16 GiB RAM\n' >&2
fi
printf 'Preflight resource checks passed. Report: %s\n' "${REPORT}"
