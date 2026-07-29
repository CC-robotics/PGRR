# Decision log

## D-001: Strict offline/runtime environment separation

The host has both ROS2 Humble and Iron, while the initial shell selected Iron inside Conda base. Arena commands will run in a clean non-Conda shell that explicitly sources Humble. Offline ML commands will run only through `conda run -n ramp-offline` or the offline activation helper.

## D-002: Isolated Arena Humble/Gazebo fallback

No installed Arena workspace or public Arena 5 workspace bootstrap entry point was available. The official Humble installer requires sudo, mutates the user pyenv installation, and the host Humble installation is incomplete. Gate 0 therefore runs the reviewed official installer inside an Ubuntu 22.04 `runc` container and selects Gazebo, which is the supported simulator in that branch. This preserves the host ROS and Conda installations and records a reproducible runtime image profile.

## D-003: Binary ROS2 Humble base with an Arena source overlay

The legacy Humble installer normally rebuilds 104 ROS2 repositories from source. Its vendor packages repeatedly stalled while downloading OGRE and other upstream archives, and a partial build also skipped an incomplete Iceoryx dependency on resume. The isolated container already has the official `/opt/ros/humble` binary distribution from the ROS apt repository. The bootstrap therefore marks the archived ROS source tree with `COLCON_IGNORE`, preserves the partial build as `*.source_ros_cache`, and builds the official Arena Humble repositories as an overlay on the binary Humble base. This avoids a mixed ROS distribution and does not modify the host installation.

## D-004: Pinned minimal headless simulation assets

The upstream simulation resource repository repeatedly failed while transferring unrelated large hospital assets. Gate 0 uses the exact upstream commit with a sparse, declared asset profile containing the empty world, Jackal, actor, shelf, and construction-cone assets needed by the automated smoke path. HuNav's panel subtree is included because Arena loads pedestrian meshes from it even in headless mode. This is not presented as a full Arena resource installation. Scenario assets required by later gates must be added explicitly and pinned before use.

## D-005: System bond library is authoritative

The archived Arena overlay built an older source `bondcpp` that is ABI-incompatible with the current binary Nav2 packages and caused `map_server` heap corruption during lifecycle activation. The source `bond_core` tree is ignored, stale overlay bond paths are removed from runtime discovery variables, and Nav2 resolves `/opt/ros/humble/lib/libbondcpp.so`. A direct lifecycle activation test and the complete smoke launch both pass with this boundary.

## D-006: Xvfb software display for deterministic headless startup

Arena's Gazebo LiDAR sensor still initializes an OGRE rendering context when `headless:=2`. The smoke test therefore runs inside Xvfb with `LIBGL_ALWAYS_SOFTWARE=1`. This supplies GLX without a desktop session or GPU-container dependency and leaves the host display untouched.

## D-007: Defer modern training-framework integration

The pinned Humble fallback predates the Arena 5 `arena feature training install` workflow and exposes its legacy optional training feature instead. Recovery learning will first use the repository's pure Python offline pipeline. If online PPO is retained at Gate 6, it will use the user-approved standalone Gymnasium/ROS2 service path unless a compatible Arena-Training integration is verified; no modern Arena-Training installation is claimed at Gate 0.

## D-008: Nav2/DWB is the primary planner adapter

Runtime introspection found Nav2 `NavigateToPose` and DWB in the accepted Arena profile. Recovery logic depends only on the backend-neutral planner protocol; `Nav2Adapter` owns the action-specific mapping and original-goal restoration. MBF is retained only as a capability probe because its messages are not installed in this profile.

## D-009: Repository source paths bridge pure Python into ROS

`ramp_core` and `ramp_ml` remain normal Python packages rather than ROS packages. The runtime wrappers add their configurable repository source directories to `PYTHONPATH` after sourcing the project overlay, while Conda remains inactive. This lets ROS nodes reuse the tested core without installing apt ROS libraries into Conda or duplicating algorithms.

## D-010: Deterministic Gazebo actor proxy for the Humble dynamic fallback

The pinned Arena task generator injects `libHuNavSystemPluginIGN.so`, but the accepted installer does not install that plugin. The upstream plugin repository additionally depends on `arena_people_msgs`, which is neither published nor present in the Arena workspace. For Gate 1, Arena still owns Gazebo, Jackal, Nav2, LiDAR, maps, and scenario resets; a project ROS node spawns named cylindrical pedestrian proxies through the official `SpawnEntity` service and advances fixed scenario trajectories through `SetEntityPose`. It publishes true positions only on a privileged topic. This is an explicit deterministic kinematic fallback, not a HuNav social-force result. Replacing it with a pinned complete HuNav dependency chain remains preferred when that chain is reproducibly available.

## D-011: Sensor timestamps are authoritative episode simulation time

In the mixed legacy Humble launch, the logger's ROS clock remained at zero even while `/clock` and stamped sensor streams advanced. Episode timing therefore uses odometry header stamps, which are generated by the simulator bridge, while every node still declares and receives `use_sim_time`. Sampling uses a steady wall timer so reset-time clock jumps cannot stall logging.
