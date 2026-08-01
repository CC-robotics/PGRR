# Known issues

## KI-063: The verified learned recovery is conservative and slow

On high-density validation seeds 2201 and 2202, DWB collided after 29.50 and 30.00 s, whereas the selected DAgger hierarchy reached the physical goal after 114.92 and 118.91 s. It used 254 and 263 non-CONTINUE samples, including 140/185 WAIT samples and 35/27 BACKUP samples. The result is a real collision-to-goal conversion rather than an always-WAIT timeout, but it exposes a strong safety--time trade-off. The final evaluation must report navigation time, intervention ratio, WAIT/BACKUP use, and timeout rate together with collision and success; the validation pilot must not be described as efficiency improvement.

## KI-064: Fallback avoidance froze pedestrians that were trying to leave

On high-density validation seed 2220, Base reached the goal in 92.907 s while DAgger timed out after 179.920 s and 1,401 non-CONTINUE samples. During the final 60 s the robot remained in emergency turning while nearby cyclic pedestrians remained 1.03--1.18 m away. The fallback actor controller froze every candidate position inside its 1.3 m avoidance radius, including route motion that increased robot--human distance. This created an artificial reciprocal live-lock. The corrected rule blocks only candidates that remain inside the radius and do not increase clearance. The privileged expert deliberately retains possible stop-short motion as a conservative envelope. The original timeout and its raw hash remain unchanged; both methods require fresh replay under the corrected environment revision.

## KI-065: The JSONL stream omitted the asynchronous physical confirmation frame

The first post-KI-064 DAgger replay received a verified success callback, but its final 10 Hz JSONL row contained a 0.319 m physical goal distance. Physical Gazebo poses arrive at the 2 Hz actor-update rate; `_confirm_goal_reached` accepted the subsequent pose at or below 0.300 m and immediately stopped logging before another periodic row. The outcome file previously contained no numeric terminal snapshot, making the success criterion unauditable from the preserved artifact alone. Finalization now writes both localized and physical goal distances, and pair summaries record whether their goal distance came from the terminal outcome or the last periodic sample. Existing outcome files are immutable and are not backfilled; a fresh replay is required.

## KI-066: The current learned pilot improves outcomes but increases terminal time

Under one current environment/code commit on high-density crossing-flow seeds 2201, 2202, and 2220, Base reached two goals and collided once while DAgger reached all three. Median terminal time nevertheless increased from 91.675 to 128.405 s, and the learned policy used a median 308 non-CONTINUE samples. This is a concrete safety--efficiency trade-off, not an efficiency improvement. The pilot contains one discordant outcome and is too small for a significance or generalization claim; further tuning remains validation-only and final test parameters are not locked.

## KI-067: Off-axis radial closing ignored the configured minimum speed

On `temporary_blockage_high_validation_s02720`, Base collided at 37.995 s and DAgger collided at 41.026 s. At 34.13--35.13 s the learned run's nearest LiDAR return closed from 0.83 to 0.60 m while the robot moved at 0.23--0.26 m/s, yet collision risk remained zero because the human was outside the forward/wide sectors. The omnidirectional trend required closing speed to exceed the full robot speed plus 0.25 m/s; this incorrectly treats orthogonal robot motion as explaining a lateral range change. The configuration's explicit `collision_closing_speed_mps=0.10` was never used. Both raw outcomes and passing sensor gates are retained. The correction must be evaluated against nominal false-trigger rate before final configuration lock.

The corrected online replay still collided at 40.493 s and recorded no early collision-risk score, despite an offline reconstruction predicting earlier trend activation. This shows that a minimum-of-scan temporal trend is sensitive to callback sampling and nearest-return identity in dense multi-person flow. The branch remains as an additional cue but is not treated as a sufficient fix.

## KI-068: Emergency backup improvement was lost during deceleration

The `e923536` temporary-blockage replay correctly left the open-map absolute guard disabled because the scenario contains 20 doorway wall objects. The independent safety layer stopped at 35.498 s and executed one 0.8 s BACKUP. Nearest observed clearance increased from 0.453 m at backup entry to 0.522 m at its end, exceeding the configured 0.05 m repeat criterion. However, the controller required the robot to finish decelerating before deciding on another pulse and compared only the later instantaneous 0.481 m clearance with the original value. It therefore forgot the valid peak and rotated in place while the pedestrian continued closing, ending in collision at 39.993 s. The raw outcome, pair summary, and passing sensor gate are retained. The fix must preserve the maximum clearance observed during each bounded pulse while keeping the existing hard repeat limit and rear-clearance checks.

## KI-069: Emergency mode telemetry collapses turns and forward escape into WAIT

The successful `0205d6e` temporary-blockage recovery contains 132 samples reported as action 21 with reason `emergency_stop`. The actual command stream shows an initial turn followed by repeated bounded 0.12 m/s forward pulses before clearance release and goal rejoin. Only the BACKUP/non-BACKUP boolean currently triggers decision publication, so TURN_LEFT, TURN_RIGHT, FORWARD, and stationary STOP share the last WAIT message. Outcome and safety metrics remain valid, but per-action interpretation is ambiguous. Future evaluation runs must publish the exact emergency mode before action-distribution or interpretability claims are generated; this episode is described only at the command-trace level.

The logger now publishes every emergency-mode transition with a stable reason string while preserving the fixed action IDs. Historical rows are not rewritten. The `0205d6e` outcome remains valid performance evidence, but it is excluded from reason-based action-distribution figures; fresh runs are required for those analyses.

## KI-070: Opposite-stream recovery remains in a safe start-region live-lock

On untouched high-density validation seed 2620, Base collided after 3.497 s. The selected DAgger hierarchy kept 0.838 m minimum human-centre distance and remained collision-free for the full 180 s, but ended only 0.200 m closer to the goal after 1,633 recovery samples. It spent 1,075 samples in emergency state, repeatedly alternating bounded STOP, BACKUP, TURN, FORWARD, and learned subgoal options; progress over the final 60 s was negative. The scenario starts one same-direction pedestrian 0.838 m from the robot inside a narrow recurrent two-way stream, which is absent from the selected checkpoint's policy-visited train coverage. The outcome is a timeout, not a safety success. Validation frames must not be added to training; fresh train-split opposite-stream episodes and privileged expert labels are required before re-evaluation.

## KI-071: Policy-visited rows can temporarily have no global path

The first opposite-stream DAgger labeling attempt failed because valid recovery rows include planner intervals with an empty `global_path`. Online deployment already fell back to the preserved original goal, while the offline labeler passed the empty path to the corridor mask. A shared `navigation_path_or_goal` helper now gives deployment and labeling identical behavior and rejects non-finite fallback goals. The regenerated train-only shard contains 273 labels, zero illegal expert actions, and 266 expert-predicted successes; no validation row enters the shard.

## KI-072: Static-scene collision logic exposed an intermittent Jackal self-return

The first iteration-4 train replay was labeled `COLLISION` at 37.73 s even though the nearest human was 1.592 m away and the physical robot remained near the corridor center. Its final two scans contained broad 0.10--0.22 m clusters at both ends of the 270-degree scan and no interior return below 0.36 m. This is the previously observed Jackal rear-body GPU-LiDAR signature; the old filter applied only when a scenario declared no static objects. Preprocessing now suppresses near returns only when both edge sectors contain the broad signature. A unilateral close wall and every interior contact remain intact. The original outcome is immutable and remains a simulator-sensor false-positive diagnostic.

## KI-073: Brief hazard-clear gaps erase the emergency turn commitment

After correcting KI-072, iteration-4 remained collision-free but timed out after 180 s with 2.378 m progress. Emergency turning occupied 695 samples and changed side nine times; five reversals occurred after only 0.6--3.0 s without a turn command. A train-only candidate preserved turn preference across five seconds of clear time. With physical collision evaluation, it eliminated all turn-side switches but timed out with -0.146 m net progress, versus +2.378 m without the memory. The candidate is removed as a negative ablation: suppressing switches alone can commit to the wrong escape side.

## KI-074: Two-frame LiDAR contact debounce still admits transient self-returns

The first turn-memory replay terminated at 8.89 s after two sub-0.12 m scan frames even though the nearest human was 4.168 m away and the robot was about 1.36 m from each corridor wall. Across the 14 outcomes available at that point, the maximum consecutive evidence length was two frames, so confirmation was raised to three 10 Hz frames. A subsequent run exposed a longer artifact at 100.30 s with 8.080 m human clearance and 0.90 m or more wall-surface clearance. Debounce alone is therefore not a reliable static-contact classifier. Historical outcomes remain immutable diagnostics.

## KI-075: Generated shelf walls are absent from the navigation occupancy map

The generated corridor shelves have exact poses in the scenario but remain absent from Arena's `map_empty` occupancy map, so raw LiDAR cannot distinguish a wall contact from the intermittent Jackal GPU-LiDAR artifact. Evaluation now parses supported `shelf` poses and checks the actual Gazebo robot centre against the exact 0.9 by 0.4 m oriented shelf footprint plus the 0.36 m robot radius. Raw LiDAR termination remains enabled for unsupported static models; open scenes use neither static classifier. This evaluation-only pose never enters the detector or learned policy. A future scenario-map compiler should still rasterize these walls for the planner.

## KI-076: Independent expert labels omitted deployment's bounded-WAIT mask

The initial opposite-stream shard labeled each sampled state independently, although online Oracle and BC deployment disable WAIT after a three-decision no-progress budget when a safe escape exists. WAIT therefore occupied 227/342 sequence-relabelled states and short-horizon `predicted_success` overstated recurrent-flow recovery. Offline labeling now carries expert side/WAIT history and applies the same bounded-WAIT mask. An additional candidate exhausted the budget immediately on observable freeze/deadlock, reducing WAIT to 209/342, but its iteration-5 closed loop timed out with only 0.196 m progress. That immediate rule is removed; the original consecutive-WAIT budget remains.

## KI-077: A Nav2 lifecycle startup timeout preceded iteration-5 evaluation

The first iteration-5 closed-loop attempt never exposed a `NavigateToPose` action although Gazebo topics were present; Nav2's lifecycle manager logged service timeouts. No episode logger had started, so the original wrapper produced no outcome artifact. The event is now explicitly recorded as `SIMULATOR_FAILURE` with zero samples, and future pre-logger launch/topic failures atomically create the same outcome class before cleanup. The algorithm run is retried under a new episode ID and the failed attempt is excluded only from algorithm metrics.

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

## KI-027: Gazebo launched two conflicting map-to-odom localization sources

The Humble task generator unconditionally set `amcl=true` for Gazebo while its Gazebo simulator also launched a static ground-truth `map -> odom` transform. Nav2 paths consequently began 6–7 m from the odometry-derived robot position even though the requested complexity was known map/known pose. `task_generator_known_pose.patch` disables AMCL for this profile and retains the simulator transform as the single localization source. A 20 s replay produced 143 path samples with 0.047 m median and 0.127 m maximum path-start/robot error. All dynamic results produced before this patch are superseded for method claims and must be rerun.

## KI-028: Rule recovery avoids collision but can settle into WAIT deadlock

After localization and detector-history fixes, corrected head-on seed 2 changed from collision to timeout. The bounded-backup heuristic made 4.836 m net progress and maintained 0.739 m minimum human-center distance, but then remained near a yielding proxy and used WAIT for 777/1202 samples. This is retained as a negative heuristic result, not Gate 2 acceptance. Additional rule branches are frozen; the privileged rollout expert will be used to distinguish transient blockage from recoverable subgoals.

## KI-029: Single-step Oracle recovery is safe but does not complete a passage

Online Oracle diagnostics exposed several real integration defects: Nav2 temporary paths replaced the saved task path, CONTINUE failed to restore the original goal, subgoals were not replanned as people moved, repeated WAIT had no accumulated cost, PENDING_RECOVERY leaked classical commands, emergency release bypassed the pending state, and footprint hazards could trigger an unsafe blind backup. These defects now have regression coverage. With the corrected chain, high-density train seed 2 remains collision-free for the full 120 s but times out, and the low-density train scenario remains collision-free but exhausts recovery attempts. The remaining failure is structural: each short action is followed by an immediate original-goal rejoin that can erase lateral/retreat progress. Gate 3 remains failed; intermediate Oracle iterations are diagnostics, not ablations or accepted results.

## KI-030: Goal-never-active runs were mislabeled as algorithm timeouts

Two concurrent software-rendered Gazebo launches reduced the real-time factor and one crossing-flow Nav2 goal never entered accepted or executing state. The robot remained exactly at its start for the full horizon, which the logger originally called `TIMEOUT`. A no-active-goal/no-movement horizon is now `INVALID_RESET`; the interrupted companion is `SIMULATOR_FAILURE`. Both episode IDs are excluded. Dynamic validation runs sequentially unless independent simulator capacity is demonstrated.

## KI-031: Hard-stop proxy can make a two-person head-on corridor unrecoverable

The deterministic fallback pauses a pedestrian whenever its next route step would enter a 1.3 m robot-centered region. In the low-density head-on scenario, two fixed lanes span the corridor and pedestrians have no lateral degree of freedom. WAIT cannot clear the blockage, lateral robot subgoals have no collision-free gap, and retreating to the pedestrian waypoint causes route reversal before a pass. Safe Oracle timeouts are therefore classified as environment/model limitation cases. Oracle execution is validated on recoverable crossing and doorway states; this case remains in failure analysis and must not be presented as a recoverable benchmark.

## KI-032: Cyclic doorway routes can re-block immediately after YIELD

Doorway pedestrians reverse at their waypoint and traverse the same door indefinitely. The extended YIELD option correctly stopped periodic original-goal pulses and released when both threats moved away, but the next cycle returned before the robot cleared the bottleneck. The valid seed-1100 Oracle run remained collision-free and reached the door, then timed out with 6.105 m progress. Longer WAIT/BACKUP is not adopted as a fix; cyclic-flow recovery needs a lateral/REPLAN phase, and this episode remains a negative result.

## KI-033: Cyclic doorway does not segment into stable recurrent options

The progress-based recurrent-flow filter passes deterministic tests, but reason-instrumented doorway replays showed that the proxy interaction is represented online as one long-lived YIELD option with intermittent recovery completion, not a stable sequence of distinct activations. Consequently no `oracle_recurrent_yield_escape` action was observed in the 60 s diagnostic. This branch must be validated on a finite-blockage or reliably segmented scenario before it can support a method claim.

## KI-034: Baseline runner overrode the configured TTC with 3.0 seconds

The Arena episode runner passed `ttc_threshold_s:=3.0` even though `configs/failure/rules.yaml` specifies 1.5 s. This produced early recovery triggers in a validation episode that Base solved safely. The runner now propagates a configurable `RAMP_TTC_THRESHOLD_S` defaulting to 1.5 s, with a regression test forbidding the legacy literal. Historical recovery episodes are labeled legacy-trigger results; selected-trigger comparisons use new episode IDs and raw hashes.

## KI-035: Task reset latency changed pedestrian phase across policies

The actor controller previously advanced from node startup while the logger timed from its first odometry sample. Arena startup latency therefore shifted both pedestrian phase and robot progress across runs with the same seed. It also sent unchecked pose requests to absent native `ped_*` names in addition to the spawned LiDAR proxies. The explicit D-022 start barrier and proxy-health path fix both defects. All pre-barrier comparative results are superseded for paired claims. Arena can still intermittently fail before the barrier; these runs are classified separately, and a 90 s wall-clock startup watchdog bounds the loss.

## KI-036: Temporary blockage was cyclic and emergency stop lacked an observable escape

The original compiler reversed doorway-crossing actors forever and froze them 1.3 m from the robot, so “temporary” blockage could never clear. Separately, a robot stopped near a door frame could not BACKUP because the 270-degree LiDAR does not observe the rear centreline. D-023 corrects both issues without weakening collision classification. One final-definition Base attempt failed before required topics appeared and is retained as `INVALID_RESET`; its bounded retry produced the valid `PLANNER_FAILURE` row. Heuristic still times out at the upper door frame, while Oracle reaches the goal; learning labels must therefore come from the Oracle, not the heuristic.
## KI-037: Offline and online recovery masks initially disagreed

The initial labeler used privileged humans and a sparse 0.25 m grid clearance, while deployment also applied a stricter LiDAR swept capsule and rejected unobserved rear motion. This made some expert labels impossible for the deployed policy. D-024 replaces both paths with one shared observable scan-mask function and all learning artifacts were regenerated. Earlier 93.14% top-1 validation accuracy is invalidated and must not appear in the paper.

## KI-038: Emergency priority can hide policy quality in narrow static geometry

The safety layer correctly has higher priority than learning, but an omnidirectional footprint stop can own the controller around a door frame even when failure scores are high. Rotation uses the Jackal's inscribed lateral clearance and stopped-motion evidence is retained, but the Oracle-timeout temporary-blockage validation seed remains unresolved. It is reported as an environment/safety interaction; the learned-policy acceptance gate uses the recoverable crossing-flow validation case.

## KI-039: DAgger artifacts produced from a dirty tree need a clean-commit rerun

The first successful DAgger-1 artifact manifest records the previous HEAD while its mask and training changes were still uncommitted. Raw files and hashes are valid, but the project commit alone is insufficient provenance. Commit the code stage, then regenerate the selected checkpoint/manifest and rerun the held-out episode before paper tables are locked.

## KI-040: Host shell advertises ROS Iron while Arena is pinned to Humble

The host environment exports `ROS_DISTRO=iron`, so direct shell commands print a mixing warning. Project Make targets explicitly clear host ROS variables for offline work, and Arena runtime commands execute inside the pinned Humble container. Never source the host Iron installation into the Arena overlay; use `make test`, `make build`, or the documented container entry points.

## KI-041: Emergency reverse pulses formed a continuous-hazard limit cycle

A clean DAgger-1 validation rerun exposed a safety-layer failure that the first run did not: small timing differences changed the first turn angle, after which the controller repeatedly alternated STOP and BACKUP beside one stationary pedestrian and eventually collided. Restricting reverse to one option per uninterrupted emergency removed that collision but brief 0.5 s hazard-clear pulses reset the allowance and produced a safe timeout. The escape controller now requires three continuous clear seconds before resetting its one-backup allowance; a persistent or flickering hazard must transition to an observable turn/forward escape. Both failed reruns remain retained as counterexamples.

## KI-042: Same-seed Gazebo scheduling changes the interaction phase

Repeated runs share the same scenario seed and simulator-time actor controller but still show small early pose differences, which can move a near-threshold interaction between normal, emergency, and collision outcomes. No single run is treated as statistical evidence. Pilot/final comparisons must use repeated paired manifests, retain all valid outcomes, and report this residual nondeterminism as a Gazebo fallback limitation.

## KI-057: Static fallback proxies accepted pose requests without moving LiDAR geometry

The deterministic actor controller originally spawned pedestrian proxy cylinders with `<static>true>`. Gazebo's pose service returned success while a low-density run placed privileged truth at a 0.697 m robot--human centre distance and LiDAR still measured 1.473 m in the expected direction. A first non-static fix still published requested truth one 2 Hz step before geometry confirmation, producing up to 0.462 m error in one episode. Proxies are now gravity-disabled kinematic links, and route time plus privileged truth commit only after the matching pose future succeeds. `validate_human_proxy_lidar.py` requires near-human LiDAR agreement before an exposed episode can enter evidence. All six final density-precheck episodes pass at 99.4--100% visibility. Runs without a close encounter provide insufficient evidence rather than a proxy pass.

## KI-058: Kinematic-link model poses could diverge from physical bodies and odometry

Direct `/world/default/dynamic_pose/info` inspection showed kinematic-link proxies remaining near initial positions while internal routes advanced. Increasing request frequency to 5 Hz only barely passed one check, and 10 Hz caused service backlog and timeout. Separately, odometry and physical Jackal pose can differ during aggressive turns, invalidating centre-distance evaluation based on odometry. The accepted path uses non-kinematic dynamic proxy links and bridges actual Gazebo poses for both the robot and pedestrians. All pre-actual-pose comparisons are diagnostic-only. Privileged actual poses never enter the deployed BC policy.

## KI-043: LiDAR-proxy surface distance underestimates the collision margin

In head-on validation the collision monitor observed a 0.70 m robot-human centre distance while the point-like LiDAR proxy could still report 0.50--0.63 m, above the original 0.48 m generic footprint stop. The pedestrian controller had correctly yielded; the robot's recovery maneuver approached the stopped actor. The generic narrow-space threshold remains 0.48 m, but a latched observable collision prediction raises the emergency margin to 0.70 m so rotation starts before the centre-distance collision boundary. This is an empirical safety filter, not a formal collision guarantee.

## KI-044: Emergency forward escape originally checked only a centre ray

After the human-clearance correction, a head-on run avoided people but the emergency controller translated forward beside a wall and produced a 0.105 m LiDAR footprint collision. Forward escape now requires a short swept-footprint capsule to be free in addition to centre-ray clearance. This closes the static side-swipe path without changing ordinary planner commands.

## KI-045: Gazebo corridor shelves are absent from the `map_empty` occupancy map

The head-on stress scenario builds corridor walls from Gazebo shelf models while Nav2 receives `map_empty`; repeated lateral recovery can therefore leave the nominal corridor even though the research problem assumes known static geometry. Runtime and offline masks now enforce a configurable 0.9 m corridor around the preserved task-level global path and allow out-of-corridor actions only when they reduce deviation. A future scenario-map compiler should rasterize all static models into the occupancy map; until then this fallback mismatch is disclosed.

## KI-046: Out-of-order odometry cleared the collision-risk latch

A deploy-aligned crossing-flow replay retained collision risk in an offline reconstruction, but the live detector briefly returned zero while a pedestrian remained in the 90-degree collision sector. Nav2 goal preemption can expose a stale DDS odometry sample; the detector treated any backwards stamp as a simulator reset and erased its temporal collision history. Episodes already launch a fresh detector and disable automatic reset, so non-increasing samples are now discarded. The failed episode remains a collision counterexample and the corrected behavior requires a fresh closed-loop rerun.

## KI-047: Ordinary static clearance was too small for collision-latched actions

The observable mask originally used 0.25 m endpoint and 0.48 m swept clearance in every state. Gazebo's LiDAR pedestrian proxy is smaller than the 0.71 m combined robot-human collision radius, so those static clearances admitted a sequence of short goals aimed at a person while collision risk remained high. Collision-latched decisions now use 0.65 m observable endpoint and swept clearance, while the independent stop margin rises to 0.85 m to include braking and callback latency. The same conditional mask is applied during expert labeling; this remains an empirical safety filter rather than a formal guarantee.

## KI-048: The host has no system LaTeX installation

Neither `latexmk` nor `pdflatex` is installed and adding system TeX would require sudo. The isolated offline environment now declares Tectonic 0.17 and caches its TeX bundle in user space. `scripts/paper/build_paper.sh` prefers `latexmk` when available and otherwise uses Tectonic, then rejects unresolved references, citations, overfull boxes, or a missing PDF. This change does not touch the ROS/Arena runtime.

## KI-049: Swept-footprint escape rejected motion away from an existing overlap

The selected policy initially timed out on Base-solvable medium-density validation seed 2210. It spent 126.2 s in `EMERGENCY_STOP` and rotated beside a 0.24--0.35 m rear-side LiDAR cluster even though its forward half-plane had at least 1.86 m clearance. The emergency forward check used an ordinary swept capsule, which necessarily includes the already-overlapping start footprint and therefore rejected every escape translation. The check now exempts only initial returns whose dot product with the translation is strictly negative; all forward/lateral initial returns and every newly intersected return remain blocking. On the exact retained counterexample, the corrected policy reached the goal in 114.386 s with 0.964 m minimum human-center distance and 219 recovery samples versus the old timeout's 1275. This is an anti-regression result, not evidence of superiority over Base, which reached the goal in 100.866 s.

## KI-050: Rejoin retries could select CONTINUE indefinitely

A high-density replay escaped the immediate interaction but stopped at `(17.01, 14.47)` with a valid path and 0.97 m LiDAR clearance. Nav2 repeatedly reported `Failed to make progress`; after each five-second rejoin timeout the state machine entered `RECOVERY`, but the policy saw a cleared failure vector and selected CONTINUE with greater than 0.97 confidence. Re-submitting the unchanged task goal cannot resolve a failed rejoin. The deployment mask now disables CONTINUE for that retry only when a planning-valid subgoal, BACKUP, or REPLAN exists. The failed replay remains `PLANNER_FAILURE`; a fresh synchronized replay reached the goal in 107.426 s with 1.136 m minimum human distance. Same-seed Gazebo nondeterminism means this is a regression check, not a paired significance result.

## KI-051: Emergency threshold chatter reset the escape hold

One locked high-density repeat timed out beside two yielding pedestrians while LiDAR clearance oscillated around the 0.85 m collision-latched stop threshold. Alternating clear/hazard samples reset the 0.5 s emergency hold before the geometric escape could complete. An active emergency now requires 0.05 m additional motion and footprint clearance before release. Entry thresholds are unchanged. The timeout remains in `outputs/pilot/crossing_flow_high_validation_safety_iteration.csv`.

## KI-052: Collision prediction cleared before the safety margin was restored

Release hysteresis alone exposed two unsafe transitions. In the first, a turning observation temporarily cleared collision prediction at 0.825 m human-center distance, immediately reducing footprint margin from 0.85 m to 0.48 m; Nav2 rejoin then collided at 0.697 m. Retaining the margin until measured clearance exceeded 0.90 m fixed that transition, but the emergency forward capsule still used the generic 0.36 m clearance and selected motion away from one obstacle while approaching a second, colliding at 0.709 m. The final implementation latches both the 0.85 m stop margin and the emergency translation capsule until clearance release. Its fresh replay reached the goal with 1.161 m minimum human distance. Both collisions are retained and no formal safety guarantee is claimed.

## KI-053: Near-range LiDAR self-returns can imitate static contact

Two high-density crossing-flow replays terminated after consecutive 0.08--0.09 m LiDAR returns even though the robot was stationary, the scenario declared no static obstacles, and privileged human centres remained 1.16 m or farther away. Treating any such return as static contact creates a false collision label, while globally disabling LiDAR collision evidence would hide real shelf and doorway contacts. The runner now enables the debounced LiDAR static-collision classifier only when the compiled scenario declares static obstacles; the independent robot--human centre-distance classifier remains active in every scenario. A fresh same-scenario replay passed the former false-positive point and reached the goal in 141.891 s with 1.185 m minimum human distance. The earlier outcomes remain unchanged across this explicitly documented classifier-version boundary.

## KI-054: Privileged actor time could outrun an unfinished Gazebo pose request

The fallback actor controller originally advanced route time and published privileged positions even while the previous asynchronous `SetEntityPose` request remained unfinished. Under Gazebo service backlog, the evaluator could therefore place a human directly in front of the robot while its LiDAR proxy remained elsewhere. The controller now freezes that route until the pending request completes and marks actor health false after a two-second request timeout. Historical outcomes are not retroactively relabeled, but pre-fix collision rows are treated as development diagnostics rather than final evidence.

## KI-055: The Jackal GPU scan contains a broad near-field self-return cluster

Open-map crossing replays contain 40 or more contiguous returns between 0.16 and 0.33 m followed by a jump beyond 1.4 m, even with the nearest privileged human more than 1.0 m away. This is a robot-body/GPU-LiDAR self-return cluster, not a point outlier. In scenarios declaring zero static obstacles, detector and policy preprocessing now replace returns below 0.34 m with infinity. The human proxy reaches the geometric collision boundary at approximately 0.36 m, so the filter retains a 0.02 m hard boundary and the ordinary braking trigger acts earlier. Static-geometry scenarios apply no such filter.

## KI-056: Observable safety fixes can trade collision for long recovery time

The final development replay combining proxy synchronization, the open-map self-return filter, strict 0.85 m emergency-forward entry, and progress-gated backup reached the goal in 176.923 s with 0.995 m minimum human distance. It spent 653 samples in emergency state and 781 on non-CONTINUE recovery actions. This is a valid closed-loop success but is close to the 180 s timeout and does not establish an efficiency improvement. The preceding timeout and collision variants remain in `outputs/pilot/crossing_flow_high_validation_runtime_alignment_iteration.csv`.

## KI-059: Dynamic fallback pedestrians pushed the robot and episode cleanup hung

The first committed actual-pose comparison ended in collisions for both Base and BC. During the longer BC run, the teleported 70 kg pedestrian bodies physically displaced and rotated the Jackal; wheel odometry and Gazebo pose differed by 3.0 m at termination. The run is retained as a simulator-dynamics diagnostic and cannot support a policy claim. Fallback pedestrians are now contactless GPU-LiDAR visuals, while collision evaluation still uses actual centre geometry. In the same run, auxiliary ROS nodes ignored SIGINT and the cleanup trap waited indefinitely, leaving six Arena containers alive after their outcome files were complete. Every auxiliary shutdown now has bounded INT/TERM/KILL escalation. Fresh online validation is required for both corrections.

## KI-060: A direct debug invocation omitted the no-auto-reset profile

The contactless BC debug run bypassed `run_baseline_episode.sh`, so `RAMP_DISABLE_AUTO_RESET` retained the container default of zero. Gazebo reset the Jackal to its start twice while odometry continued, creating 6.2 m and then 25.7 m pose offsets; the resulting timeout is `INVALID_RESET` evidence even though its immutable outcome file predates the new detector. The inner runner now refuses to start unless auto reset is explicitly disabled, and the logger independently classifies any greater-than-1.0 m jump in actual Gazebo robot pose as `INVALID_RESET`. The corresponding contactless Base run terminated before any reset and remains a valid platform diagnostic.

## KI-061: Wheel odometry could declare a false goal reach

After no-auto-reset and command mux were restored, a recovery-heavy run ended with 0.236 m localized goal distance but 1.062 m physical Gazebo goal distance; wheel-integrated skid-steer odometry had accumulated 0.927 m position error. This run remains unchanged and is not goal-reach evidence. The known-pose Gazebo profile now separates DiffDrive wheel odometry onto diagnostic topics, maps Gazebo's pose-derived OdometryPublisher into the standard odometry and TF interfaces, and applies an identity map-to-odom transform. The logger requires physical goal distance at most 0.30 m in addition to the 0.25 m localized tolerance. The verified learned run ended at 0.299 m physical distance with 0.128 m maximum localization disagreement.

## KI-062: Physical goal confirmation initially sampled one stale pose frame

On independent validation seed 2202, Base physically reached the goal, while the first learned attempt was classified `SIMULATOR_FAILURE`: localized distance was 0.232 m and the latest Gazebo pose was 0.308 m from goal, only 8 mm outside the physical threshold with 0.077 m cross-topic offset. The logger had made a terminal decision on the first success callback instead of waiting for the asynchronous actual-pose stream. Goal confirmation now waits a fixed one-second steady-clock window for physical distance to enter 0.30 m; exceeding the window still produces `SIMULATOR_FAILURE`. The original outcome remains unchanged and a fresh replay is required.
