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

The pinned Arena task generator injects `libHuNavSystemPluginIGN.so`, but the accepted installer does not install that plugin. The upstream plugin repository additionally depends on `arena_people_msgs`, which is neither published nor present in the Arena workspace. For Gate 1, Arena still owns Gazebo, Jackal, Nav2, LiDAR, maps, and scenario resets; a project ROS node spawns named cylindrical pedestrian proxies through the official `SpawnEntity` service and advances fixed scenario trajectories through `SetEntityPose`. It publishes confirmed positions only on a privileged topic. This is an explicit deterministic kinematic fallback, not a HuNav social-force result. Replacing it with a pinned complete HuNav dependency chain remains preferred when that chain is reproducibly available.

## D-011: Sensor timestamps are authoritative episode simulation time

In the mixed legacy Humble launch, the logger's ROS clock remained at zero even while `/clock` and stamped sensor streams advanced. Episode timing therefore uses odometry header stamps, which are generated by the simulator bridge, while every node still declares and receives `use_sim_time`. Sampling uses a steady wall timer so reset-time clock jumps cannot stall logging.

## D-012: Audited Gazebo asset overrides for stable headless experiments

The pinned Jackal asset renders a 640 x 16 GPU LiDAR through Mesa because the host Docker GPU runtime is incomplete, although the method uses a planar scan downsampled to 180 beams. The runtime bind-mounts a versioned 360 x 1, 10 Hz sensor definition and the Dataset still deterministically downsamples it to 180. Arena's asset named `obstacles/static/shelf` also declares `<static>false>`; 58 adjacent corridor shelves became interacting rigid bodies and stopped DART simulation time near 5 seconds. A second versioned override changes only that tag to `<static>true>`. Both source-derived files and their SHA256 values are locked; the container image and host ROS installation remain unchanged.

## D-013: LiDAR-visible, robot-yielding pedestrian fallback

Gazebo's task-generated `actor` entities are visible in rendering but produced no planar-LiDAR return. The fallback controller now spawns a uniquely named kinematic cylindrical proxy for every visual actor, advances it on the seeded route, and verifies each spawn and pose response. Route advancement pauses before the next step enters a 1.3 m robot-centered region and resumes after the robot yields, avoiding the artifact of a kinematic pedestrian walking through a stopped robot. Robot pose is used only by simulator behavior and is not included in recovery observations. Earlier actor-only results are retained but superseded.

## D-014: Direction-consistent braking clearance

The braking equation is longitudinal, so its clearance input is measured along current translation: forward motion checks a forward laser sector and reverse motion checks the rear. This prevents a safe parallel side wall from being treated as longitudinal stopping distance. Emergency stop remains above policy output and is not claimed as a formal guarantee.

## D-015: Separate classical and standard-recovery behavior trees

The corrected Gate 1 `base` profile uses Arena's `navigate_w_replanning_time` tree (DWB plus periodic replanning, without a recovery subtree). The `standard` profile uses the installed `navigate_to_pose_w_replanning_and_recovery` tree. The `heuristic` profile uses the same base tree plus RAMP's observable detector and recovery manager. This keeps B0, B1, and B2 distinct without adding a custom C++ Nav2 plugin; the exact mapping is locked in `configs/planner/baselines.yaml`.

## D-016: Known-pose Gazebo uses one ground-truth localization source

The selected experiment is a known-map, known-pose simulator profile. Arena Humble's simultaneous AMCL and static map-to-odom publishers are therefore reduced to the static simulator transform using a versioned, runtime-validated patch. This is not privileged policy input: the learned observation remains LiDAR, goal/path, velocity, planner state, and temporal history. Ground-truth actor state remains confined to the expert and evaluation fields.

## D-017: Recovery must be a bounded sequence-level option

The online Oracle demonstrates that independently safe 0.5 s decisions do not necessarily compose into a successful passage: restoring the original goal after every WAIT, BACKUP, or short lateral action repeatedly drives the robot back into the same reciprocal deadlock. The implementation retains the fixed 25-action interface but now composes actions inside a bounded option, escalates repeated WAIT when a planned escape is safe, and treats emergency stops as preemptions of the same sequence. Safety monitoring remains receding-horizon and may interrupt any phase.

## D-018: Oracle trigger and YIELD are privileged upper-bound components

Gazebo proxy actors can intermittently be absent from planar LiDAR, so an Oracle driven by the observable rule trigger is not a valid expert upper bound. The Oracle profile now uses privileged relative position/velocity for a finite-horizon closest-approach trigger. For longitudinally approaching humans it executes an interpretable YIELD option: bounded BACKUP followed by WAIT until the threat passes. Neither signal is exposed to heuristic or learned test-time policies. Main-method claims must use the selected observable detector; Oracle results are labeled upper bounds.

YIELD uses a separate 30 s hard limit while ordinary recovery actions retain the configured 8 s limit. It releases when tracked threats pass or all reverse away after predicted risk clears. Cyclic doorway traffic can return and re-trigger it, so YIELD is not the complete doorway method; repeated flow requires lateral escape or replanning.

## D-019: Recurrent-flow escalation is progress-based and mask-conservative

Repeated blockage is defined by insufficient robot task progress between YIELD activations, rather than persistent pedestrian IDs. After the configured recurrence count, the Oracle may evaluate only action-mask-valid lateral subgoals and REPLAN. The restriction is not applied when no such candidate exists, preserving WAIT/BACKUP as the safe fallback. The branch is covered by unit tests but is not yet an accepted online result: the cyclic doorway proxy produced a single long-lived YIELD option rather than a clean repeated activation.

## D-020: Expert quality includes intervention efficiency

The medium-density train diagnostic favored Oracle over Heuristic, but the high-density diagnostic did not: both succeeded and Heuristic used fewer interventions with slightly better time and clearance. Planning-expert quality therefore cannot be judged only by collision-free predicted success. Demonstration analysis must include intervention count/duration and CONTINUE frequency, and an explicit unnecessary-intervention penalty may be tuned only on validation data. No expert-dominance claim is made from the current single-seed diagnostics.

## D-021: Trigger on planner-conditioned TTC at 1.5 seconds

The runtime had overridden the configured 1.5 s rule TTC with 3.0 s, and the privileged trigger ignored planner angular commands. Normal validation showed that these choices caused unnecessary recovery in a Base-solvable episode. The trigger now predicts the Jackal's constant-control unicycle trajectory from DWB's current `(v, omega)`, retains a 3.0 s analysis horizon, and intervenes only when predicted TTC is at most 1.5 s. A 1.0 s candidate reduced normal interventions but caused 83 emergency-stop samples on a train collision case; it is rejected as too late. The selected 1.5 s value reduced validation interventions from 197 to 30 while retaining safe recovery on the train failure case. No further threshold tuning is allowed on these episodes.

## D-022: Pair experiments at an explicit navigation/actor/logger start barrier

Arena task reset latency allowed deterministic actor routes to advance before the logger began, producing method-dependent pedestrian phase and robot progress despite identical scenario seeds. Comparative episodes now use a repeated `/ramp/episode_started` handshake: Nav2 must be active, the logger must be discovered, actors are reset to route time zero, and GoalMux remains stopped until the signal arrives. The logger defines episode time zero at this barrier. Only synchronized episodes may support paired claims; earlier dynamic results remain diagnostic provenance.

The kinematic fallback now updates only the spawned `ramp_lidar_proxy_*` models and checks every `SetEntityPose` response. Rejected updates set `SIMULATOR_FAILURE` through an explicit health topic. This makes the privileged trajectory, LiDAR geometry, and action mask auditable against one physical proxy source.

## D-023: Finite blockage semantics and observable geometric safety escape

`temporary_blockage` uses one-shot pedestrian routes whose endpoints lie outside the doorway; cyclic reversal was inconsistent with the scenario name and made clearance impossible. Its actors retain a 0.8 m robot stop distance, above the 0.71 m combined collision radii, while other social scenarios retain 1.3 m. Recovery subgoals are masked against the full LiDAR-derived swept-footprint capsule rather than only a narrow target ray. If a footprint stop occurs with an unobserved rear sector, the safety layer may rotate in place and make a bounded, observed forward escape; this deterministic reflex remains above the learned policy and is not a formal safety guarantee.
## D-024: Share one observable action mask between labeling and deployment

The first BC deployment exposed that offline labels allowed privileged/unobserved BACKUP and used a looser grid clearance than the ROS policy. Expert demonstrations are now constrained first by the exact deployable 270-degree LiDAR mask: unobserved rear motion is disabled, each temporary goal must have directional clearance, and its full centreline capsule must have 0.48 m swept clearance. Privileged human trajectories affect expert rollout cost, not the deployed mask. All affected labels and checkpoints were regenerated; pre-alignment accuracy numbers are superseded.

## D-025: Select DAgger over margin or full-cost weighting on closed-loop evidence

Margin weighting and a clipped differentiable full-cost regret term did not improve scenario-disjoint validation. BC-0 also entered a repeat CONTINUE/safety-BACKUP loop online. DAgger-1 added only train-split policy-visited states and produced a held-out `GOAL_REACHED` on the synchronized crossing-flow validation episode. The selected minimum method is therefore Uniform BC plus DAgger and planning masks. MWBC and full-cost losses remain honest negative ablations unless later evidence changes the selection.

## D-026: Expand only the train split with deterministic speed variants

The original single crossing-flow train seed was a difficult negative that did not reproduce the validation interaction phase. Three train-only variants change only deterministic pedestrian speeds and receive distinct seeds, IDs, files, and hashes. Validation and test files remain untouched. This expands DAgger coverage without frame-level leakage or test tuning.

## D-027: Select DAgger-1 provisionally; do not assume more aggregation is better

DAgger-2 adds genuine policy-visited train states and completes the prescribed two-round workflow, but its locked validation repeats were one success and one collision, versus two successes for DAgger-1 after the same safety fix. DAgger-1 is therefore the provisional model. The second iteration is retained as a negative result rather than selected by iteration count. Because the two DAgger-1 successes selected only CONTINUE, active learned-recovery benefit still requires evidence on other validation scenarios.

## D-028: Apply temporal and collision-latched masks to learned options

Head-on validation exposed two deployment semantics missing from the learned policy: WAIT and REPLAN could repeat without progress, and CONTINUE/REPLAN remained available while observable collision risk was latched. The BC mask now budgets three no-progress WAIT decisions and one REPLAN, and blocks rejoin actions while collision risk is at least the configured 0.65 trigger threshold. A budget is enforced only when a planning-valid alternative exists; otherwise WAIT remains the safe fallback.

## D-029: Treat repeat-5 active recovery as pilot evidence only

The current coverage model converted three of five repeated crossing-flow Base-failure trials into verified goal reaches and selected real temporary subgoals, but two trials still collided. Exact intervals are wide and Fisher p=0.167. The method is therefore promising enough to continue, but no significance or robustness claim is permitted until scenario/seed expansion. Head-on and overtaking counterexamples remain in failure analysis rather than being removed.

## D-030: Select deploy-aligned safety over a collision-prone equal-success candidate

The earlier coverage checkpoint reached the goal in three of five crossing-flow repeats but collided twice. Offline analysis then exposed two deployment mismatches: collision-risk rejoin actions were not represented in label masks, and ordinary static clearances underestimated the Gazebo fallback's combined robot-human collision radius. After aligning masks and preserving collision history across stale odometry, the safety checkpoint also reached three of five trials but produced zero collisions; the remaining two trials timed out and are retained. This checkpoint is selected for expanded validation because the research question prioritizes recovery without degrading safety. Its longer tail is reported directly, and the 180 s pilot is not mixed with earlier 120 s timeout counts in formal statistics.

## D-031: Use the imitation-only title until PPO earns a closed-loop claim

The repository does not yet contain a validated PPO environment or training result, while the planning-expert, BC, two-round DAgger, deployment mask, and closed-loop policy are implemented and evidenced. The manuscript therefore uses *Planning-Guided Failure-Triggered Recovery via Imitation Learning for Dynamic Social Navigation*. PPO remains optional future work; it may enter the title and contributions only after multiple seeds outperform or complement the selected DAgger policy without reward hacking.

## D-032: Permit emergency translation only when it separates every initial overlap

A footprint capsule is correct for an ordinary candidate action but cannot represent recovery when the robot is already inside its conservative clearance boundary: every segment contains the unsafe start point. The emergency reflex may therefore ignore an initially overlapping LiDAR return only if the proposed translation immediately increases its distance (`point dot translation < 0`). It still applies the full swept capsule to all other returns, retains the 0.36 m translation clearance, moves at 0.12 m/s for at most 0.8 s per option, and remains interruptible. This observable geometric exception repaired a retained medium-density limit cycle without reducing collision thresholds or changing the learned checkpoint.

## D-033: A failed rejoin must try a different executable option

The state-machine transition `rejoin_failure_retry` is direct evidence that CONTINUE failed to produce progress for the configured five-second window. During that transition only, CONTINUE is removed from the BC action mask if at least one already-mask-valid locomotion alternative exists. The learner then chooses among its remaining ranked actions; no action is hard-coded and WAIT remains available. If no subgoal, BACKUP, or REPLAN is safe, CONTINUE is retained rather than creating an empty or WAIT-only mask. This is a temporal action constraint analogous to the bounded WAIT and REPLAN budgets, not a model retraining change.

## D-034: Release collision safety only after measured clearance recovery

Collision prediction is an anticipatory trigger, not a reliable release signal during rapid in-place rotation. Once its 0.65 threshold is crossed, the 0.85 m footprint and emergency-translation clearances remain latched until the nearest observed return exceeds 0.90 m. Emergency entry thresholds do not change, and a 0.05 m release hysteresis prevents threshold chatter from resetting the escape controller. A bounded translation may still begin inside the conservative capsule only when it strictly separates from every overlapping return. This composes prediction, measured geometry, and hysteresis without exposing privileged state or weakening the collision boundary.

## D-035: Bind static-contact evidence to declared scenario geometry

Gazebo near-range LiDAR can report the robot body or proxy artifacts below the 0.12 m static-contact threshold. The episode runner therefore derives `lidar_static_collision_enabled` from the compiled scenario's `obstacles.static` count. Static shelves, corridor walls, and doorway geometry retain a two-frame LiDAR contact classifier; open-map crossing flow does not. Human collision classification is independent and always enabled through the privileged centre-distance monitor used only for evaluation. This changes terminal labeling, not policy observations, action selection, or safety control.

## D-036: Repeat emergency backup only with measured clearance gain

One reverse pulse remains available only with observed rear clearance. A continuous hazard may request another pulse only if the completed pulse increased the nearest observed clearance by at least 0.05 m, and no more than eight pulses are permitted. Unchanged-clearance cycles therefore still transition to turning, while a bottleneck retreat can accumulate bounded progress. The temporary-blockage validation replay used 30 reverse control samples and remained collision-free but timed out; this is retained as safe negative evidence, not a recovery-success claim.

## D-037: Synchronize privileged actor truth to accepted pose updates

Route time no longer advances while the corresponding proxy has an unfinished `SetEntityPose` future. A request outstanding for more than two seconds marks `/ramp/actors_healthy` false so the logger reports simulator failure rather than algorithm performance. This preserves the deterministic route definition while preventing privileged evaluation state from accumulating unbounded lead over the LiDAR-visible proxy.

## D-038: Filter only geometrically impossible open-map near returns

For scenarios with no declared static obstacles, ranges below 0.34 m are excluded consistently from the rule detector and recovery observation. The threshold is below the 0.36 m proxy-surface distance at the combined robot--human collision radius. Scenarios with shelves, walls, or door frames retain every non-negative return. Raw episode logs are unchanged so the preprocessing remains auditable.

## D-039: Admit dynamic evidence only after a kinematic-proxy sensor check

Fallback pedestrian cylinders are non-static links with gravity disabled and kinematic motion enabled. Route time and privileged positions commit only after Gazebo confirms the matching collision-geometry update. For any validation episode that brings a privileged human centre inside 1.3 m, an evaluation-only checker projects that centre into the 360-degree LiDAR and requires at least 90% of five or more exposed samples to contain a surface return within 0.20 m of the expected cylinder range. Privileged positions are used only for this simulator-validity check and outcome evaluation, never by the deployed policy. Pre-confirmed dynamic tables remain available for diagnosis but cannot support manuscript performance claims.

## D-040: Evaluation truth comes from Gazebo dynamic-pose feedback

SetEntityPose success is treated only as command acknowledgement. Fallback pedestrian links are dynamic with gravity disabled, and their physical poses plus the Jackal physical pose are read from `/world/default/dynamic_pose/info` through `ros_gz_bridge`. The actor controller publishes these on evaluation-only privileged topics and fails health on stale feedback. Collision classification and the LiDAR consistency gate use actual-to-actual centre geometry; policy observations continue to use odometry and LiDAR. This decision supersedes D-039's kinematic-link implementation while retaining its sensor gate.

## D-041: Separate LiDAR visibility from contact dynamics in fallback pedestrians

The fallback cylinder is an evaluation surrogate, not a rigid-body model of a person. A 70 kg teleported collision body pushed the Jackal during prolonged close recovery, creating up to 3.0 m disagreement between wheel odometry and Gazebo pose. The proxy therefore retains its rendered cylinder for GPU LiDAR but has no contact collision element. Robot--human collision remains the unchanged actual-pose centre-distance test, and the sensor-consistency gate must confirm that the visual is observed by LiDAR. Pedestrian route yielding uses the actual Gazebo Jackal position once available. This removes an unintended simulator impulse without weakening terminal collision labels or exposing privileged data to the policy.

## D-042: Use pose-derived odometry in the known-pose Gazebo profile

Gazebo DiffDrive integrates wheel motion as odometry. The four-wheel skid-steer Jackal accumulated 0.93 m position error during a recovery-heavy run and declared success while the physical model remained 1.06 m from the goal. The Gazebo profile now routes DiffDrive odometry to an unused diagnostic topic and publishes the standard `odom` interface from Gazebo's `OdometryPublisher`, which derives motion from the model pose. This is the simulator's declared known-pose localization source, analogous to replacing it with AMCL on a mapped real platform; pedestrian truth remains excluded from policy input. Episode success still requires a physical-pose goal-distance check.
