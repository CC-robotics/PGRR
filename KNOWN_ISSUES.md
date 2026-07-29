# Known issues

## KI-001: Default interactive shell selects ROS Iron

The machine contains Humble and Iron, and the initial shell reported `ROS_DISTRO=iron`. Arena runtime scripts explicitly unset inherited ROS setup variables where practical and source `/opt/ros/humble/setup.bash`. Do not run Arena from Conda base.

## KI-002: Inherited ROS pytest plugin contaminated Conda tests

The initial `make test` inherited `/opt/ros/iron` through `PYTHONPATH`, loading an incompatible `launch_testing` pytest plugin. Offline commands now clear ROS discovery variables, the activation helper does the same, and a regression test checks that no `/opt/ros` path is visible. The Makefile also enables `pipefail` so `tee` cannot hide test failures.

## KI-003: Full Conda SAT solve was unnecessarily slow

Putting the scientific and PyTorch stack across Conda channels spent nine minutes in dependency solving without creating an environment. The Conda layer now contains Python 3.10 and pip; all declared wheels remain in `environment.yml` and exact resolved versions are locked in `requirements-offline.lock.txt`.

## KI-004: Docker default runtime points to a missing NVIDIA runtime

The host Docker daemon selects `nvidia-container-runtime` by default, but that executable is not installed. Arena bootstrap and runtime commands therefore pass `--runtime runc` explicitly. GPU access is not required for the simulator smoke test; offline Torch GPU access was validated separately on the host.

## KI-005: Humble installer hard-codes the wrong vcstool executable

The reviewed upstream installer installs the vcstool fork into Arena's Poetry environment but aliases `vcs` to a nonexistent pyenv shim. The original installer and its SHA256 remain archived unchanged. `third_party/arena_humble_compat.patch` captures the Poetry-environment executable before importing repositories; installation then resumes from the preserved builder container.

## KI-006: Legacy installer is not safely resumable

The upstream script repeats full repository imports and moves an existing Arena checkout before cloning it again. Interrupted vendor builds can also leave child processes alive in the builder container. The compatibility patch uses shallow concurrent imports with completion markers, reuses a valid checkout, and the wrapper validates markers before publishing an image. A builder image is never treated as complete merely because the installer process returned.

## KI-007: Network routes have complementary failure modes

Direct Ubuntu and ROS apt downloads are substantially faster than the inherited proxy, while some direct GitHub clones stop making progress. Bootstrap runs apt without proxy variables and passes the inherited proxy only to the official installer repository operations. Imports are shallow and resumable; repository counts and valid Git `HEAD` objects are checked before a completion marker is accepted.

## KI-008: Binary Nav2 and legacy source bond ABI mismatch

The first complete launch crashed `map_server` while creating its lifecycle bond because the Arena overlay shadowed the binary package with an older `bondcpp`. The source package is now ignored and runtime paths are scrubbed. `ldd` confirms that `map_server` resolves the Humble apt library. Keep this assertion when changing the image or ROS apt snapshot.

## KI-009: Gazebo GPU LiDAR requires a display context in headless mode

`headless:=2` alone produced an OGRE GLX initialization failure. Xvfb with Mesa software rendering fixes startup and is part of the smoke command. This validates software headless operation; it does not validate accelerated rendering.

## KI-010: Upstream rosdep metadata has unresolved optional keys

The legacy source tree reports unresolved keys for `${PROJECT_NAME}_msgs` and `hunav_rviz2_panel`; the Humble rosdep database also lacks a rule for the standard `ament_python` build type. The required packages for the selected Gazebo/Jackal/DWB profile build and run. The project overlay explicitly skips only the installed `ament_python` build tool; future packages must not copy the malformed upstream placeholder key.

## KI-011: Smoke goal acceptance is not navigation success

The Gate 0 smoke target only proves action discovery and acceptance. Its readiness goal can abort and is not counted as `GOAL_REACHED`. Gate 1 must validate an appropriate static start/goal pair and record the terminal outcome through the episode logger.

## KI-012: Arena Humble omits the Gazebo HuNav plugin dependency chain

The task generator references `libHuNavSystemPluginIGN.so`, but the accepted image contains no such library. The upstream Arena-Rosnav plugin repository was located and pinned during diagnosis, but it depends on `arena_people_msgs`, which is not present in Arena, ROS Humble apt, or the plugin repository. Running `human:=hunav` therefore starts the manager while Gazebo rejects the motion plugin; this is not a valid dynamic simulation. Gate 1 uses the D-010 kinematic proxy and fails on any pre-cleanup entity-update error. Do not describe proxy runs as HuNav or social-force runs.

## KI-013: Logger node clock stayed at zero after legacy task reset

Although `/clock` and odometry stamps advanced, the logger node clock remained zero in the combined launch, so a simulated timeout could never fire. Sampling now uses a steady timer and elapsed simulation time from odometry headers. Regression runs verified timestamps from 0.0 to 2.997 seconds and a correctly classified timeout.

## KI-014: ROS node attribute shadowing broke clean destruction

The first logger implementation named its subscription handle list `_subscriptions`, shadowing an internal `rclpy.node.Node` collection and causing `destroy_node()` to remove entries twice. The handle list is now `_subscription_handles`; the terminal loop exits without calling shutdown from inside a callback.

## KI-015: Legacy Arena emits traceback text during controlled teardown

The upstream world generator calls `rclpy.shutdown()` after an external shutdown and some bridge processes report signal exit codes during cleanup. Runtime acceptance checks inspect crashes only before the explicit `[RAMP_*] cleanup_started` marker, require terminal episode artifacts first, and still preserve the full teardown log. Unexpected tracebacks before that marker remain fatal.
