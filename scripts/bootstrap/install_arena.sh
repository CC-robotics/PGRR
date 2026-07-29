#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARENA_WS="${ARENA_WS:-${HOME}/arena5_ws}"
PROFILE_FILE="${PROJECT_ROOT}/configs/platform/arena_profile.yaml"
INSTALLER_URL="https://raw.githubusercontent.com/Arena-Rosnav/arena-rosnav/humble/installers/install.sh"

if [[ -n "${CONDA_PREFIX:-}" || -n "${VIRTUAL_ENV:-}" ]]; then
    printf 'ERROR: deactivate Conda and virtualenv before Arena installation\n' >&2
    exit 1
fi

if [[ -e "${ARENA_WS}" && ! -d "${ARENA_WS}" ]]; then
    printf 'ERROR: ARENA_WS exists but is not a directory: %s\n' "${ARENA_WS}" >&2
    exit 1
fi

if [[ -d "${ARENA_WS}" ]]; then
    if [[ -r "${ARENA_WS}/arena" ]] || [[ -r "${ARENA_WS}/arena.bash" ]] || [[ -r "${ARENA_WS}/install/setup.bash" ]]; then
        printf 'Using existing Arena workspace: %s\n' "${ARENA_WS}"
        exit 0
    fi
    if find "${ARENA_WS}" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
        printf 'ERROR: refusing to overwrite non-Arena, non-empty directory: %s\n' "${ARENA_WS}" >&2
        exit 1
    fi
fi

tmp_installer="$(mktemp /tmp/ramp_arena_install.XXXXXX.sh)"
curl -fsSL "${INSTALLER_URL}" -o "${tmp_installer}"
installer_sha="$(sha256sum "${tmp_installer}" | awk '{print $1}')"
cp "${tmp_installer}" "${PROJECT_ROOT}/third_party/arena_humble_installer.sh"
printf '%s  %s\n' "${installer_sha}" "${INSTALLER_URL}" > \
    "${PROJECT_ROOT}/third_party/arena_humble_installer.sha256"

if grep -Eq 'rm -rf[[:space:]]+(["'\''$]{0,2})(HOME|~|/)(["'\''/[:space:]]|$)' "${tmp_installer}"; then
    printf 'ERROR: installer safety review found a broad destructive command\n' >&2
    exit 1
fi

cat > "${PROFILE_FILE}" <<'YAML'
profile: arena_humble_fallback
ros_distro: humble
workspace_tooling: legacy_arena_bash
preferred_simulator: gazebo
flatland_available: false
installer_review_required: true
YAML

if ! sudo -n true 2>/dev/null; then
    printf 'ERROR: official Arena fallback installer requires sudo and no cached credential is available.\n' >&2
    printf 'Reviewed installer saved at %s (SHA256 %s).\n' \
        "${PROJECT_ROOT}/third_party/arena_humble_installer.sh" "${installer_sha}" >&2
    exit 77
fi

printf '%s\n' "${ARENA_WS}" | \
    ARENA_WS_DIR="${ARENA_WS}" RCFILE="${PROJECT_ROOT}/.arena_install_rc" \
    ARENA_BRANCH=humble ARENA_ROS_DISTRO=humble bash "${tmp_installer}"
