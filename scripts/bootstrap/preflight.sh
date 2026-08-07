#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARENA_WS="${ARENA_WS:-${HOME}/arena5_ws}"
REPORT="${PROJECT_ROOT}/docs/environment_report.txt"
mkdir -p "$(dirname "${REPORT}")"

capture() {
    printf 'RAMP environment preflight\n'
    printf 'captured_at=%s\n' "$(date --utc +%Y-%m-%dT%H:%M:%SZ)"
    printf 'project_root=${PROJECT_ROOT}\n'
    printf 'arena_ws=${ARENA_WS}\n'
    printf '\n[uname]\n'
    printf 'kernel=%s\n' "$(uname -s)"
    printf 'kernel_release=%s\n' "$(uname -r)"
    printf 'architecture=%s\n' "$(uname -m)"
    printf '\n[os-release]\n'
    sed -n '1,30p' /etc/os-release
    printf '\n[cpu]\n'
    lscpu
    printf '\n[memory]\n'
    free -h
    printf '\n[disk]\n'
    df -h --output=size,avail,pcent "${PROJECT_ROOT}"
    printf '\n[python]\n'
    command -v python3 >/dev/null 2>&1 && printf 'available=yes\n' || printf 'available=no\n'
    python3 --version || true
    printf '\n[conda]\n'
    command -v conda >/dev/null 2>&1 && printf 'available=yes\n' || printf 'available=no\n'
    conda --version 2>/dev/null || true
    printf '\n[mamba]\n'
    command -v mamba >/dev/null 2>&1 && printf 'available=yes\n' || printf 'available=no\n'
    printf '\n[git]\n'
    git --version || true
    printf '\n[ros2 inherited]\n'
    command -v ros2 >/dev/null 2>&1 && printf 'available=yes\n' || printf 'available=no\n'
    printf 'ROS_DISTRO=%s\n' "${ROS_DISTRO:-}"
    printf '\n[ros2 humble]\n'
    if [[ -r /opt/ros/humble/setup.bash ]]; then
        env -i HOME="${HOME}" USER="${USER:-}" PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash --noprofile --norc -c \
            'source /opt/ros/humble/setup.bash; printf "available=yes\nROS_DISTRO=%s\n" "$ROS_DISTRO"; ros2 pkg list | wc -l'
    else
        printf 'not installed\n'
    fi
    printf '\n[gpu]\n'
    if command -v nvidia-smi >/dev/null 2>&1; then
        printf 'available=yes\n'
        nvidia-smi --query-gpu=name,driver_version,memory.total \
            --format=csv,noheader 2>/dev/null || true
    else
        printf 'available=no\n'
    fi
    printf '\n[docker]\n'
    command -v docker >/dev/null 2>&1 && printf 'available=yes\n' || printf 'available=no\n'
    docker --version 2>/dev/null || true
    printf '\n[active environments]\n'
    [[ -n "${CONDA_PREFIX:-}" ]] && printf 'conda_active=yes\n' || printf 'conda_active=no\n'
    [[ -n "${VIRTUAL_ENV:-}" ]] && printf 'virtualenv_active=yes\n' || printf 'virtualenv_active=no\n'
    printf '\n[arena discovery]\n'
    if [[ -d "${ARENA_WS}" ]]; then
        printf 'workspace=present\n'
        find "${ARENA_WS}" -maxdepth 3 -type f \
            \( -name arena -o -name arena.bash -o -name setup.bash \) \
            -printf '${ARENA_WS}/%P\n'
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
printf 'Preflight resource checks passed. Report: ${PROJECT_ROOT}/docs/environment_report.txt\n'
