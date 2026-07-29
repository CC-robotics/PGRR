#!/usr/bin/env bash
set -euo pipefail

ARENA_WS_DIR="${ARENA_WS_DIR:-/opt/arena_ws}"
MANIFEST="${ARENA_WS_DIR}/src/arena/arena-rosnav/.repos/arena.repos"
FILTERED_MANIFEST="/tmp/ramp_arena_filtered.repos"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
cd "${ARENA_WS_DIR}"

python3 - "${MANIFEST}" "${FILTERED_MANIFEST}" <<'PY'
import os
import subprocess
import sys

import yaml

source, destination = sys.argv[1:]
repositories = yaml.safe_load(open(source, encoding="utf-8"))["repositories"]
special = {
    "arena/simulation-setup",
    "arena/tools",
    "deps/hunav/hunav_sim",
    "deps/nav2/navigation2",
    "deps/slam_toolbox",
}
missing = {}
for relative, spec in repositories.items():
    if relative in special:
        continue
    path = os.path.join("/opt/arena_ws/src", relative)
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        missing[relative] = spec
with open(destination, "w", encoding="utf-8") as stream:
    yaml.safe_dump({"repositories": missing}, stream, sort_keys=True)
for relative in missing:
    print(relative)
PY

while IFS= read -r relative; do
    [[ -n "${relative}" ]] || continue
    target="${ARENA_WS_DIR}/src/${relative}"
    if [[ -e "${target}" ]]; then
        mv "${target}" "${target}.ramp_incomplete_${STAMP}_$$"
    fi
done < <(python3 - "${FILTERED_MANIFEST}" <<'PY'
import sys
import yaml

for path in yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["repositories"]:
    print(path)
PY
)

missing_count="$(python3 - "${FILTERED_MANIFEST}" <<'PY'
import sys
import yaml

print(len(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["repositories"]))
PY
)"
if (( missing_count > 0 )); then
    timeout 1800 vcs import --shallow -w 4 src < "${FILTERED_MANIFEST}"
fi

partial_clone() {
    local relative="$1"
    local url="$2"
    local expected_commit="$3"
    shift 3
    local sentinel="$1"
    local target="${ARENA_WS_DIR}/src/${relative}"
    local actual=""
    local sparse_lock=""
    if [[ -d "${target}/.git" ]]; then
        actual="$(git -C "${target}" rev-parse HEAD 2>/dev/null || true)"
        git -C "${target}" config http.version HTTP/1.1
        for sparse_lock in \
            "${target}/.git/info/sparse-checkout.lock" \
            "${target}/.git/index.lock"; do
            if [[ -f "${sparse_lock}" ]]; then
                if ps -C git -o args= 2>/dev/null | grep -F -- "${target}" >/dev/null; then
                    printf 'ERROR: active Git process holds %s\n' "${sparse_lock}" >&2
                    return 1
                fi
                unlink "${sparse_lock}"
            fi
        done
    fi
    if [[ "${actual}" == "${expected_commit}" ]]; then
        env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
            timeout 1800 git -C "${target}" sparse-checkout set "$@"
        env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
            timeout 1200 git -C "${target}" checkout --force "${expected_commit}"
        local missing=0
        local sparse_path
        for sparse_path in "$@"; do
            [[ -e "${target}/${sparse_path}" ]] || missing=1
        done
        if (( missing == 0 )); then
            return 0
        fi
    fi
    if [[ -e "${target}" ]]; then
        mv "${target}" "${target}.ramp_incomplete_${STAMP}_$$"
    fi
    mkdir -p "$(dirname "${target}")"
    env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
        timeout 1200 git clone --filter=blob:none --no-checkout "${url}" "${target}"
    env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
        git -C "${target}" sparse-checkout init --cone
    env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
        timeout 1200 git -C "${target}" sparse-checkout set "$@"
    env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
        timeout 1200 git -C "${target}" fetch --depth 1 origin "${expected_commit}"
    env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
        timeout 1200 git -C "${target}" checkout --force "${expected_commit}"
    test "$(git -C "${target}" rev-parse HEAD)" = "${expected_commit}"
}

partial_clone \
    arena/tools https://github.com/voshch/arena-tools.git \
    cbf1d05abd436cdb820da9fd0c35847b06a39ae0 \
    arena_tools resource
partial_clone \
    deps/hunav/hunav_sim https://github.com/voshch/hunav_sim.git \
    a69cf96d98b0d40e247f819d7aebab661ac68b3b \
    hunav_agent_manager hunav_evaluator hunav_msgs hunav_rviz2_panel hunav_sim
partial_clone \
    arena/simulation-setup https://github.com/voshch/arena-simulation-setup.git \
    3f142b25d88ce962c803b57cf20f38985d376dea \
    arena_simulation_setup configs \
    "gazebo_models/Construction Cone" \
    entities/robots/jackal \
    entities/obstacles/static/shelf \
    entities/obstacles/dynamic/gazebo_actor \
    launch resource scripts worlds/map_empty

set +u
source /opt/ros/humble/setup.bash
set -u
ros2 pkg prefix nav2_bringup >/dev/null
ros2 pkg prefix slam_toolbox >/dev/null

ignored_packages=(
    src/deps/nav2/bond_core
    src/deps/robots/irobot_create/irobot_create_common/irobot_create_common_bringup
    src/deps/robots/irobot_create/irobot_create_common/irobot_create_nodes
    src/deps/robots/irobot_create/irobot_create_gazebo/irobot_create_gazebo_bringup
    src/deps/robots/irobot_create/irobot_create_gazebo/irobot_create_gazebo_plugins
    src/deps/robots/irobot_create/irobot_create_gazebo/irobot_create_gazebo_sim
    src/deps/robots/irobot_create/irobot_create_ignition/irobot_create_ignition_bringup
    src/deps/robots/irobot_create/irobot_create_ignition/irobot_create_ignition_sim
    src/deps/robots/irobot_create/irobot_create_ignition/irobot_create_ignition_toolbox
    src/gazebo/turtlebot4_simulator/turtlebot4_ignition_bringup
    src/gazebo/turtlebot4_simulator/turtlebot4_ignition_gui_plugins
    src/gazebo/turtlebot4_simulator/turtlebot4_ignition_toolbox
    src/gazebo/turtlebot4_simulator/turtlebot4_simulator
)
for package_path in "${ignored_packages[@]}"; do
    if [[ -d "${ARENA_WS_DIR}/${package_path}" ]]; then
        touch "${ARENA_WS_DIR}/${package_path}/COLCON_IGNORE"
    fi
done

python3 - "${MANIFEST}" <<'PY'
import os
import subprocess
import sys

import yaml

repositories = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["repositories"]
binary = {"deps/nav2/navigation2", "deps/slam_toolbox"}
invalid = []
for relative in repositories:
    if relative in binary:
        continue
    path = os.path.join("/opt/arena_ws/src", relative)
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        invalid.append(relative)
if invalid:
    raise SystemExit("repositories without valid HEAD: " + ", ".join(invalid))
PY

touch "${ARENA_WS_DIR}/src/arena/.ramp_import_complete"
