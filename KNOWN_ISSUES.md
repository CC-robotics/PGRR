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

## KI-016: Cleared `CONDA_PREFIX` can coexist with stale Conda shell state

The first failure-mining invocation inherited `CONDA_SHLVL=1` and `CONDA_DEFAULT_ENV=base` after `CONDA_PREFIX` had already been unset. `conda run` then failed while trying to deactivate a null prefix. The launcher now clears all activation metadata and sets `CONDA_SHLVL=0` only for the offline materialization subprocess; Arena still launches afterward outside Conda. No simulator episode was started by the failed invocation.

## KI-017: Arena's static shelf asset is physically dynamic

The installed `static/shelf` SDF contains `<static>false>`. A corridor with 58 adjacent shelves caused the DART world clock to stop near 5.2 simulated seconds even with pedestrian control disabled. A locked runtime-only asset override changes the tag to true. The corrected 15-second probe completed with 158 samples and robot motion from x=5.00 m to x=6.16 m; the final metadata-locked canonical seed produced a real `COLLISION` at 112.9203 simulated seconds.

## KI-018: Headless Jackal LiDAR is unnecessarily three-dimensional

The pinned Jackal uses a 640 x 16 GPU LiDAR. With Xvfb/Mesa this rendered 10,240 rays per frame despite the experiment requiring a planar scan. The versioned runtime override uses 360 x 1 rays at the same 10 Hz and disables visualization. The public observation pipeline continues to downsample to the declared 180 beams. This is a platform-performance adaptation, not an algorithm result.

## KI-019: Wall-clock guard originally waited on a live logger

When simulation time stopped, the baseline loop detected its wall deadline but then waited for the logger before signaling it, so cleanup could hang. The guard now stops the logger first, emits `SIMULATOR_FAILURE`, and proceeds through bounded cleanup. Diagnostic outcomes from the interrupted probes are retained under `data/raw/interrupted/` and are excluded from algorithm metrics.

## KI-020: Nav2 lifecycle activation has intermittent invalid resets

Six Gate 1 attempts exposed missing `NavigateToPose` readiness or lifecycle service timeouts even though some ROS topics existed. These are classified as `INVALID_RESET`, archived with logs, and excluded from algorithm outcomes. Failure mining now assigns a fresh ROS domain and Gazebo partition per seed and retry, permits two bounded retries, and never overwrites valid episode data. All 30 fixed seeds eventually produced valid outcomes.

## KI-021: Arena visual actors were invisible to LiDAR

The first 30-episode Gate 1 run moved task-generated actors and detected collision from privileged center distance, but scans did not change as actors approached. The controller had reused each actor name, so its cylinder spawn addressed the existing visual entity instead of creating geometry. Proxies now use `ramp_lidar_proxy_*` names and validate spawn success. Earlier results and labels are superseded and cannot support observable-policy claims.

## KI-022: Upstream task generator ignored `auto_reset`

The Humble task generator reads `auto_reset` but reset every completed task unconditionally. `third_party/task_generator_auto_reset.patch` gates reset on the parameter; runtime mounts an explicit `auto_reset: false` profile and applies the patch ephemerally. Initial task setup still emits one expected reset.

## KI-023: Host and container symlink builds need distinct paths

Colcon symlink artifacts embed absolute paths. A host build under `/home/diy/RAMP` is not reusable at `/workspace` in the Arena container. Container artifacts remain in `ros_ws/{build,install,log}` and optional host artifacts use `*-host`; all generated variants are ignored.

## KI-024: Arena can pause at its task timeout before the logger's terminal sample

One corrected heuristic episode reached a final odometry stamp just below 120 s and then stopped producing sensor data at Arena's task boundary, so the independent 120 s logger could not observe `elapsed >= timeout`. The runtime-only task-generator profile now sets its integer timeout to 125 s while the algorithm episode timeout remains 120 s. Arena's legacy parameter declaration rejects a YAML float override even though its Python wrapper is annotated as `float`; a regression test locks the integer representation. This preserves the declared evaluation horizon and gives the logger a five-second simulator-time guard band; a stopped simulator still reaches the existing wall-clock guard and is classified separately.

## KI-025: Wall-clock sampling duplicated slow-simulator odometry stamps

The logger samples from a steady wall timer so a paused simulator can still reach its wall guard, but Gazebo can run slower than real time. The original logger therefore wrote the latest odometry more than once; observed unique-stamp ratios ranged from 0.80 to 0.95. Terminal outcomes and endpoint metrics are unaffected, but duplicated frames would bias learning. The logger now writes only strictly newer simulator stamps and treats backwards time as `INVALID_RESET`. HDF5 rejects non-strict timestamps, while legacy raw conversion removes only equal adjacent stamps and reports the removal count.

## KI-026: Terminal Nav2 aborts were previously allowed to drift into timeout

The original logger classified only startup aborts with less than 0.05 m displacement as `PLANNER_FAILURE`. In corrected head-on seed 0, Nav2 later reached a terminal abort but the robot continued receiving stale control behavior and drifted outside the corridor until `TIMEOUT`. B0/B1 now require an abort with no accepted, executing, or canceling replacement goal for 5 s of simulation time before terminating as `PLANNER_FAILURE`; stale aborted goal records are ignored while a replacement is active. B2 keeps this automatic termination disabled so its recovery manager may intervene, and a manager `FAILED` state is logged as `PLANNER_FAILURE`. The interrupted strict1 artifacts are retained under `data/quarantine/planner_outcome_bug_20260730/` and excluded.
