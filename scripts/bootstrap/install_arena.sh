#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARENA_WS="${ARENA_WS:-${HOME}/arena5_ws}"
PROFILE_FILE="${PROJECT_ROOT}/configs/platform/arena_profile.yaml"
INSTALLER_URL="https://raw.githubusercontent.com/Arena-Rosnav/arena-rosnav/humble/installers/install.sh"
ARENA_IMAGE="${ARENA_IMAGE:-ramp-arena:humble}"
BUILDER_NAME="${ARENA_BUILDER_NAME:-ramp-arena-builder}"

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
if ! curl --retry 3 --retry-delay 2 --retry-all-errors -fsSL \
    "${INSTALLER_URL}" -o "${tmp_installer}"; then
    archived_installer="${PROJECT_ROOT}/third_party/arena_humble_installer.sh"
    if [[ ! -s "${archived_installer}" ]]; then
        printf 'ERROR: official Arena installer download failed and no archive exists\n' >&2
        exit 1
    fi
    cp "${archived_installer}" "${tmp_installer}"
    printf 'Using the previously archived official Arena installer after network failure.\n'
fi
installer_sha="$(sha256sum "${tmp_installer}" | awk '{print $1}')"
cp "${tmp_installer}" "${PROJECT_ROOT}/third_party/arena_humble_installer.sh"
printf '%s  %s\n' "${installer_sha}" "${INSTALLER_URL}" > \
    "${PROJECT_ROOT}/third_party/arena_humble_installer.sha256"

if grep -Eq 'rm -rf[[:space:]]+(["'\''$]{0,2})(HOME|~|/)(["'\''/[:space:]]|$)' "${tmp_installer}" || \
    ! sudo -n true 2>/dev/null; then
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        printf 'ERROR: native installer is unsafe without isolation or needs sudo; Docker is unavailable.\n' >&2
        printf 'Reviewed installer: %s (SHA256 %s).\n' \
            "${PROJECT_ROOT}/third_party/arena_humble_installer.sh" "${installer_sha}" >&2
        exit 77
    fi
    printf 'Native install is not safe/non-interactive; using an isolated Docker profile.\n'
    arena_base_image='ubuntu:22.04'
    image_complete=0
    if docker image inspect "${ARENA_IMAGE}" >/dev/null 2>&1; then
        if docker run --rm --runtime runc "${ARENA_IMAGE}" bash -c \
            'test -f /opt/arena_ws/.ramp_install_complete &&
             test -f "/opt/arena_ws/src/arena/simulation-setup/gazebo_models/Construction Cone/model.sdf" &&
             test -d /opt/arena_ws/install/arena_simulation_setup/share/arena_simulation_setup/gazebo_models &&
             grep -q default_map_path /opt/arena_ws/src/arena/arena-rosnav/arena_bringup/launch/utils/map_server.launch.py &&
             test -f /opt/arena_ws/src/deps/nav2/bond_core/COLCON_IGNORE &&
             command -v Xvfb >/dev/null &&
             source /opt/ros/humble/setup.bash &&
             source /opt/arena_ws/install/setup.bash &&
             ros2 pkg prefix hunav_rviz2_panel >/dev/null &&
             ros2 pkg prefix ros_gz_bridge >/dev/null'; then
            image_complete=1
        else
            printf 'Found an incomplete Arena image; resuming from its preserved layers.\n'
            arena_base_image="${ARENA_IMAGE}"
        fi
    fi
    if [[ "${image_complete}" -eq 0 ]]; then
        if ! docker container inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
            docker create --name "${BUILDER_NAME}" --runtime runc --network host \
                -e DEBIAN_FRONTEND=noninteractive \
                -e PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
                -e RTI_NC_LICENSE_ACCEPTED=yes -e TZ=Etc/UTC \
                -e ARENA_WS_DIR=/opt/arena_ws -e ARENA_BRANCH=humble \
                -e ARENA_ROS_DISTRO=humble -e RCFILE=/root/.bashrc \
                "${arena_base_image}" sleep infinity >/dev/null
        fi
        docker start "${BUILDER_NAME}" >/dev/null
        docker exec "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
            -u http_proxy -u https_proxy bash -c \
            'apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates cmake curl git gnupg2 libompl-dev lsb-release python3 python3-dev python3-pip software-properties-common sudo tzdata wget xvfb'
        if ! docker exec "${BUILDER_NAME}" bash -c \
            'test -s /usr/share/keyrings/ros-archive-keyring.gpg && \
             gpg --show-keys /usr/share/keyrings/ros-archive-keyring.gpg >/dev/null 2>&1'; then
            docker exec "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
                -u http_proxy -u https_proxy curl -fsSL \
                https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
                -o /usr/share/keyrings/ros-archive-keyring.gpg
        fi
        if docker exec "${BUILDER_NAME}" \
            test -s /etc/apt/sources.list.d/ros2-latest.list; then
            docker exec "${BUILDER_NAME}" bash -c \
                'if test -f /etc/apt/sources.list.d/ros2.list &&
                    grep -q "packages.ros.org/ros2/ubuntu" /etc/apt/sources.list.d/ros2.list; then
                    unlink /etc/apt/sources.list.d/ros2.list
                 fi'
        else
            docker cp "${PROJECT_ROOT}/third_party/ros2-jammy.list" \
                "${BUILDER_NAME}:/etc/apt/sources.list.d/ros2.list"
        fi
        docker exec "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
            -u http_proxy -u https_proxy apt-get update
        docker exec "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
            -u http_proxy -u https_proxy apt-get install -y \
            ros-humble-ros-gz-bridge ros-humble-ros-gz-interfaces
        if ! docker exec "${BUILDER_NAME}" bash -c \
            'source /opt/ros/humble/setup.bash 2>/dev/null && \
             command -v ros2 >/dev/null && ros2 pkg prefix rclcpp >/dev/null && \
             ros2 pkg prefix nav2_bringup >/dev/null && \
             ros2 pkg prefix slam_toolbox >/dev/null'; then
            docker exec "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
                -u http_proxy -u https_proxy apt-get install -y \
                ros-humble-desktop ros-humble-navigation2 \
                ros-humble-nav2-bringup ros-humble-slam-toolbox ros-dev-tools
        fi
        docker exec "${BUILDER_NAME}" bash -c \
            'source /opt/ros/humble/setup.bash && \
             command -v ros2 >/dev/null && ros2 pkg prefix rclcpp >/dev/null'
        docker exec "${BUILDER_NAME}" bash -c \
            'source /opt/ros/humble/setup.bash && \
             ros2 pkg prefix nav2_bringup >/dev/null && \
             ros2 pkg prefix slam_toolbox >/dev/null'
        docker exec "${BUILDER_NAME}" bash -c '
            set -eu
            mkdir -p /opt/arena_ws
            cd /opt/arena_ws
            if [ ! -f .ramp_ros_binary_fallback ]; then
                for tree in build install log; do
                    if [ -e "$tree" ]; then
                        mv "$tree" "${tree}.source_ros_cache"
                    fi
                done
                source /opt/ros/humble/setup.bash
                command -v ros2 >/dev/null
                ros2 pkg prefix rclcpp >/dev/null
                mkdir -p src/ros2
                touch src/ros2/COLCON_IGNORE
                touch src/ros2/compiled
                touch .ramp_ros_binary_fallback
            fi'
        docker cp "${PROJECT_ROOT}/third_party/arena_humble_installer.sh" \
            "${BUILDER_NAME}:/tmp/arena_install.sh"
        docker cp "${PROJECT_ROOT}/third_party/arena_humble_compat.patch" \
            "${BUILDER_NAME}:/tmp/arena_humble_compat.patch"
        docker cp "${PROJECT_ROOT}/third_party/arena_gazebo_headless.patch" \
            "${BUILDER_NAME}:/tmp/arena_gazebo_headless.patch"
        docker cp "${PROJECT_ROOT}/third_party/arena_pull_pinned.patch" \
            "${BUILDER_NAME}:/tmp/arena_pull_pinned.patch"
        docker cp "${PROJECT_ROOT}/third_party/arena_map_server_default.patch" \
            "${BUILDER_NAME}:/tmp/arena_map_server_default.patch"
        docker cp "${PROJECT_ROOT}/third_party/task_generator_auto_reset.patch" \
            "${BUILDER_NAME}:/tmp/task_generator_auto_reset.patch"
        docker cp "${PROJECT_ROOT}/third_party/task_generator_known_pose.patch" \
            "${BUILDER_NAME}:/tmp/task_generator_known_pose.patch"
        docker cp "${PROJECT_ROOT}/scripts/bootstrap/import_arena_dependencies.sh" \
            "${BUILDER_NAME}:/tmp/import_arena_dependencies.sh"
        docker exec "${BUILDER_NAME}" bash -c \
            'cd /tmp && patch --forward --silent arena_install.sh arena_humble_compat.patch || grep -q "VCS_EXECUTABLE" arena_install.sh'
        if docker exec "${BUILDER_NAME}" bash -c \
            'test -f /opt/arena_ws/src/arena/arena-rosnav/.installed &&
             grep -qx gazebo.sh /opt/arena_ws/src/arena/arena-rosnav/.installed &&
             grep -qx planners.sh /opt/arena_ws/src/arena/arena-rosnav/.installed &&
             test -f /opt/arena_ws/install/setup.bash'; then
            docker exec "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
                -u http_proxy -u https_proxy bash -lc \
                'set -eo pipefail
                 export PATH=/root/.local/bin:$PATH
                 source /opt/ros/humble/setup.bash
                 cd /opt/arena_ws
                 bash /tmp/import_arena_dependencies.sh
                 colcon build --symlink-install --event-handlers console_direct+ \
                    --packages-select hunav_rviz2_panel arena_simulation_setup arena_bringup task_generator'
        else
            printf '%s\n' '/opt/arena_ws' | \
                docker exec -i -e DEBIAN_FRONTEND=noninteractive -e TZ=Etc/UTC \
                    -e RAMP_ARENA_INSTALLERS=gazebo.sh,planners.sh \
                    -e PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
                    "${BUILDER_NAME}" env -u HTTP_PROXY -u HTTPS_PROXY \
                        -u http_proxy -u https_proxy bash -i /tmp/arena_install.sh
        fi
        docker exec "${BUILDER_NAME}" bash -lc \
            'set -eo pipefail
             map_launch=/opt/arena_ws/src/arena/arena-rosnav/arena_bringup/launch/utils/map_server.launch.py
             patch --forward --silent --reject-file=- "$map_launch" \
                /tmp/arena_map_server_default.patch 2>/dev/null || \
                grep -q default_map_path "$map_launch"
             task_node=/opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/node.py
             patch --forward --silent --reject-file=- "$task_node" \
                /tmp/task_generator_auto_reset.patch 2>/dev/null || \
                grep -q "self._task.is_done and self._auto_reset" "$task_node"
             robot_manager=/opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/manager/robot_manager/robot_manager.py
             patch --forward --silent --reject-file=- "$robot_manager" \
                /tmp/task_generator_known_pose.patch 2>/dev/null || \
                grep -q "'"'"'amcl'"'"': '"'"'false'"'"'" "$robot_manager"
             export PATH=/root/.local/bin:$PATH
             source /opt/ros/humble/setup.bash
             cd /opt/arena_ws
             colcon build --symlink-install --event-handlers console_direct+ \
                --packages-select arena_bringup task_generator'
        docker exec "${BUILDER_NAME}" bash -lc \
            'test -f /opt/arena_ws/src/ros2/compiled &&
             test -f /opt/arena_ws/src/arena/arena-rosnav/.installed &&
             grep -qx gazebo.sh /opt/arena_ws/src/arena/arena-rosnav/.installed &&
             grep -qx planners.sh /opt/arena_ws/src/arena/arena-rosnav/.installed &&
             test -f /opt/arena_ws/install/setup.bash &&
             test -f "/opt/arena_ws/src/arena/simulation-setup/gazebo_models/Construction Cone/model.sdf" &&
             test -d /opt/arena_ws/install/arena_simulation_setup/share/arena_simulation_setup/gazebo_models &&
             grep -q default_map_path /opt/arena_ws/src/arena/arena-rosnav/arena_bringup/launch/utils/map_server.launch.py &&
             grep -q "self._task.is_done and self._auto_reset" /opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/node.py &&
             grep -q "'"'"'amcl'"'"': '"'"'false'"'"'" /opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/manager/robot_manager/robot_manager.py &&
             test -f /opt/arena_ws/src/deps/nav2/bond_core/COLCON_IGNORE &&
             command -v Xvfb >/dev/null &&
             export PATH=/root/.local/bin:$PATH &&
             source /opt/ros/humble/setup.bash &&
             cd /opt/arena_ws && source arena.bash >/dev/null &&
             ros2 pkg prefix arena_bringup >/dev/null &&
             ros2 pkg prefix hunav_rviz2_panel >/dev/null &&
             ros2 pkg prefix ros_gz_bridge >/dev/null &&
             touch /opt/arena_ws/.ramp_install_complete'
        docker commit \
            --change 'ENV WANDB_MODE=offline RAMP_ROOT=/workspace ARENA_WS_DIR=/opt/arena_ws' \
            --change 'WORKDIR /workspace' \
            "${BUILDER_NAME}" "${ARENA_IMAGE}" >/dev/null
        docker stop "${BUILDER_NAME}" >/dev/null
        docker rm "${BUILDER_NAME}" >/dev/null
    fi
    image_id="$(docker image inspect "${ARENA_IMAGE}" --format '{{.Id}}')"
    printf '%s\n' \
        'profile: arena_humble_docker' \
        'ros_distro: humble' \
        'workspace_tooling: legacy_arena_bash' \
        'preferred_simulator: gazebo' \
        'flatland_available: false' \
        'container_runtime: runc' \
        'display_backend: xvfb_software_gl' \
        'robot: jackal' \
        'local_planner: dwb' \
        'asset_profile: pinned_minimal_headless' \
        "image: ${ARENA_IMAGE}" \
        "image_id: ${image_id}" \
        'arena_commit: c2ff4a87e8686013b53f1e9cd8b01b3ab04fbce4' \
        "installer_sha256: ${installer_sha}" > "${PROFILE_FILE}"
    exit 0
fi

printf '%s\n' \
    'profile: arena_humble_fallback' \
    'ros_distro: humble' \
    'workspace_tooling: legacy_arena_bash' \
    'preferred_simulator: gazebo' \
    'flatland_available: false' \
    "installer_sha256: ${installer_sha}" > "${PROFILE_FILE}"

printf '%s\n' "${ARENA_WS}" | \
    ARENA_WS_DIR="${ARENA_WS}" RCFILE="${PROJECT_ROOT}/.arena_install_rc" \
    ARENA_BRANCH=humble ARENA_ROS_DISTRO=humble bash "${tmp_installer}"
