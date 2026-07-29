# Runtime dependency manifest

## Environment boundary

- Offline data and learning: `ramp-offline`, declared in `environment.yml` and frozen in `environment.lock.yml` plus `requirements-offline.lock.txt`.
- ROS simulation: `ramp-arena:humble`, Docker `runc`, Ubuntu 22.04, ROS2 Humble, Python 3.10.20, Gazebo 8.14.0.
- The two environments share only files under the repository; ROS Python paths are removed from offline commands and Conda is rejected by runtime bootstrap scripts.

## Arena profile

The selected fallback is official Arena-Rosnav commit `c2ff4a87e8686013b53f1e9cd8b01b3ab04fbce4`, built as 48 source packages over binary Humble. The runtime discovers 416 ROS packages. It uses Jackal, DWB, the empty-map smoke world, Xvfb, and Mesa software rendering.

The simulation-setup checkout is a sparse view of exact commit `3f142b25d88ce962c803b57cf20f38985d376dea`. Included assets are `map_empty`, Jackal, `gazebo_actor`, shelf, and Construction Cone. HuNav's panel package is also built because Arena's runtime uses its pedestrian meshes even in headless mode. This profile is sufficient for the accepted smoke test; later scenarios must declare any added assets.

## Compatibility boundaries

- Nav2 and Slam Toolbox come from ROS apt. The archived ROS2 source tree is ignored.
- Source `bond_core` is ignored because it is ABI-incompatible with binary Nav2; `map_server` links to `/opt/ros/humble/lib/libbondcpp.so`.
- The installed map-server launch is patched to provide the packaged empty-map YAML required by current binary Nav2.
- Modern Arena-Training and RosNav-RL are not claimed installed at Gate 0. Their integration is deferred to the relevant learning gate and may use the documented standalone Gymnasium path.

Exact repositories, package versions, image identity, installer identity, and patch hashes are in `arena_commits.lock`.
