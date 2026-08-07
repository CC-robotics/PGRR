# Progress log

## 2026-08-07 — moderate-v5 comparator validation and calibration gate

- Completed all 288 comparator validation tasks across Base, Standard, Heuristic,
  and Uniform BC on the 72-condition moderate-v5 validation manifest.
- Preserved 12 no-outcome Gazebo startup failures and used the runner's single-worker
  resume path to complete only the missing logical tasks.
- Collected immutable results: Base 57 goals / 15 collisions; Standard 58 / 14;
  Heuristic 63 goals / four planner failures / five timeouts; Uniform BC 64 goals /
  eight planner failures.
- Ran the preregistered Base calibration with no condition filtering. It rejected
  moderate-v5 because Base success was 79.17%, above the frozen 75% maximum. The
  other three checks passed.
- Kept every moderate-v5 test scenario sealed. The next gate is a newly identified,
  newly seeded validation-only benchmark revision; v5 test execution is prohibited.

## 2026-08-07 — validation-only timeout remediation

- Replayed the retained low-density blind-corner timeout and traced it to recurrent
  STOP/BACKUP/Nav2 release without goal progress. The static Gazebo shelf is absent
  from the `map_empty` Nav2 occupancy map, so the correction remains observable and
  bounded rather than using privileged shelf coordinates.
- Evaluated seven incremental candidates on the same validation probe and preserved
  every terminal outcome. In particular, the 0.36 m rotation-clearance candidate
  collided with the shelf and was rejected; planner-failure and timeout candidates
  were also not promoted as successes.
- Selected `eceeca8`: emergency budgets reset only after stable clearance plus
  observable original-goal progress; post-retreat release requires a turn; forward
  and reverse escape directions meet at 80 degrees; emergency escalation activates a
  bounded 2.5 m recurrent path envelope; and turning requires 0.60 m drift-aware
  clearance.
- Converted the fixed blind-corner validation timeout into a physically verified
  goal reach at 126.51 s and 0.243 m terminal physical error, without collision.
- Completed an eight-family low-density replicate-zero PGRR regression: 8/8 goal
  reaches, zero collisions, zero timeouts, and zero planner failures. One initial
  four-worker overtaking launch returned before the logger created an outcome; the
  one-worker resume regenerated only that missing task and the final manifest reports
  8/8 complete with `worker_errors=[]`.
- Generated checked-in Parquet/CSV/JSON evidence for both probes. These rows are
  validation-only and are not used as final paper results.
- Passed Ruff, formatting, strict mypy, all 636 offline tests, and the three-package
  ROS overlay build.
- Completed the full 72-condition PGRR validation manifest at project commit
  `22da999`: 62 goal reaches, one collision, one timeout, and eight planner failures.
  Four `SIMULATOR_FAILURE` attempts and three pre-logger launch gaps were preserved;
  one-worker resume filled only the missing work, and the final manifest reports
  72/72 complete with `worker_errors=[]`.
- The remaining failure distribution is explicit: four blind-corner planner failures;
  three doorway failures plus one doorway human collision; and one high-density
  temporary-blockage planner failure plus one high-density timeout. All other 62
  family--density--replicate conditions reached the goal.
- Generated compact Parquet/CSV/JSON evidence under
  `outputs/moderate/v5_validation_pgrr_22da999/`. The PGRR runtime candidate is fixed
  pending complete comparator validation and Base calibration; the held-out test has
  still not been run or inspected.

## 2026-08-06 — validation-only blind-corner clearance freeze

- Completed two bounded blind-corner geometry calibrations using validation only:
  `a52804c` (`9.00/16.00`) and `3406c08` (`8.75/16.25`, satisfying the catalog's
  2.85 m inflated-corner diagonal-clearance check).
- Both fixed five-case probes recorded three `GOAL_REACHED` outcomes, no collision,
  and `PLANNER_FAILURE` for the low- and high-density blind-corner cases. The hard
  cases remain in the benchmark; no further difficulty tuning is planned.
- Synchronized the frozen catalog, validation split, test split, and state-machine
  hashes to the `3406c08` files without running or inspecting the held-out test.

## 2026-08-04 — locked EI result and PGRR relocation

- Completed all 64 logical tasks in the frozen test manifest at commit `35d7e60`: 24
  paired Base/PGRR conditions and eight high-density Standard/Heuristic conditions.
  The final runner reports no worker error and the collector retains all 64 algorithm
  outcomes.
- Preserved and excluded exactly three technical attempts before retry: one
  `SIMULATOR_FAILURE` and two `INVALID_RESET` outcomes. The accepted retries were one
  PGRR timeout, one PGRR goal reach, and one Base collision. No failed algorithm
  episode was deleted.
- Recovered from a first four-worker pass in which two launch wrappers produced no
  outcome artifact. The three-worker resume pass reused completed hash-verified rows,
  regenerated the missing high-density doorway Base and medium-density group-blocking
  PGRR work, and completed 64/64.
- Final Base/PGRR outcomes are 5/19/0 and 8/0/16 for
  goal/collision/timeout. Collision reduction is significant after Holm correction;
  goal-reach improvement is not, and the timeout/intervention/jerk increases establish
  a strong safety--completion trade-off.
- Final high-density Standard/Heuristic outcomes are 1/7/0 and 1/0/7. These eight
  single-condition-per-family rows are retained as descriptive mechanism evidence, not
  a standalone statistical claim.
- Generated `results.parquet`, `summary.csv`, `statistics.json`, the offline policy
  ablation, final failure analysis, paper figures/tables, a telemetry reconstruction
  video, and an eight-page IEEE PDF. Every paper number is generated from final
  artifacts rather than manually entered.
- Adopted PGRR as the public name: Planning-Guided Failure-Triggered Recovery and
  Rejoin. Internal `ramp_*` package names and `method=bc` artifact identifiers remain
  for compatibility; the selected method is Uniform BC + DAgger, not MWBC or PPO.
- Atomically relocated the full 9.2 GB working repository to `${PROJECT_ROOT}`.
  Archived the host-path ROS caches and old venv without
  deletion, recreated the venv/editable packages at the new path, and retained the
  root-owned Docker ROS caches after confirming that they use only `/workspace` and
  contain no host-path references.
- Revalidated Gate 0 after relocation. The first smoke exposed an upstream idle
  odometry bridge; the wrapper now mounts the same pinned Jackal mapping used by
  evaluated episodes and verifies real samples rather than topic names. The fresh
  run passed clock, TF, LiDAR, odometry, goal acceptance, and controlled cleanup.
- Revised the eight-page manuscript around the verified hierarchy, collision endpoint,
  and DAgger ablation. Timeout remains in the main and statistical tables and is
  interpreted once in Results and once in Limitations; repetitive negative wording was
  removed without changing any result.
- Regenerated all seven paper figures at IEEE one- or two-column dimensions with a
  color-vision-safe three-color palette, shape redundancy, larger effective type, and
  confidence intervals where replication supports them. Regenerated five result tables
  with `booktabs`, explicit units, sample sizes, comparison direction, and compact notes.
- Recompiled and visually audited all eight pages. The paper has no unresolved reference,
  overfull box, Type 3 font, or unembedded font; the complete quality suite passes 286
  tests.

- 2026-08-01: Completed two verified-pose high-density crossing-flow validation pairs under frozen commit `6cf9535`. DWB collided on seeds 2201 and 2202; triggered DAgger physically reached the goal on both. All four near-human LiDAR gates passed at 100% visibility. Added raw-hash-linked pair CSVs and regenerated the manuscript with a descriptive two-seed table and figure; no significance claim is made.
- 2026-08-01: Retained high-density validation seed 2220 as a nominal-regression counterexample: Base reached the goal and DAgger timed out in an emergency-turning live-lock. Fixed the fallback yielding rule so a pedestrian inside the avoidance radius may move away but not closer; expert rollout remains conservative to a possible stop. Added seven unit tests; the full suite passes 217 tests and the ROS overlay builds.
- 2026-08-01: Post-fix seed 2220 preserved Base goal reach and allowed DAgger to exit the live-lock, but exposed missing terminal-pose provenance: physical success was confirmed on a 2 Hz pose callback after the final 10 Hz JSONL row. Added explicit localized/physical terminal distances to every new outcome and backward-compatible summary provenance. The pre-field replay remains diagnostic and will not be promoted as verified goal evidence.
- 2026-08-01: Replayed all three available high-density crossing-flow validation scenarios under terminal-evidence commit `8577ff1`. Base produced two goals and one collision; DAgger produced three physical goal reaches. All six LiDAR gates passed, every learned terminal physical distance was at most 0.287 m, and all raw hashes are preserved. The generated IEEE table/figure now uses only these same-version pairs and reports the observed safety--time trade-off without significance language.
- 2026-08-01: Added a cross-family temporary-blockage validation pair. Both Base and DAgger collided; DAgger delayed collision by 3.03 s but did not recover. Sensor gates passed. Failure replay exposed that `collision_closing_speed_mps` was declared and validated but never applied, while the omnidirectional branch subtracted the full robot speed from lateral closing motion. The negative pair is retained before correcting the observable detector.
- 2026-08-01: Implemented off-axis radial-closing detection using the existing configured 0.10 m/s threshold, gated by sector separation and angular speed. Two new regression tests cover moving-robot lateral approach and sub-threshold jitter; 219 tests pass. Raw replay moves the temporary-blockage warning 5.69 s earlier and crossing-flow onsets about 0.10 s earlier, but also lengthens warning holds, so online validation is required before selection.
- 2026-08-01: The fresh temporary-blockage pair remained negative after off-axis trend correction: Base collided at 37.995 s and DAgger at 40.493 s with 55 recovery samples. Both sensor gates passed. The online failure stream still triggered only during the terminal emergency, so the trend candidate is insufficient by itself; the next bounded candidate uses known-map absence of static geometry for a conservative omnidirectional dynamic-return threshold.
- 2026-08-01: Added a map-conditioned 0.70 m omnidirectional collision-risk trigger for scenarios declaring no static obstacles. The runtime enables it only alongside the existing open-map self-return filter; mapped static-geometry scenarios leave it disabled. Unit tests cover trigger activation, negative-value rejection, and runtime wiring; 221 tests pass.
- 2026-08-01: Retained the `e923536` temporary-blockage replay as a third cross-family failure. Base collided at 37.995 s and DAgger at 39.993 s; both sensor gates pass. The open-map guard was correctly inactive because this scenario contains 20 doorway walls. Trace analysis found a concrete executor defect: the first emergency BACKUP raised nearest clearance by 0.069 m, but the repeat decision was made only after braking had erased the measured gain, causing an ineffective rotation instead of the already-authorized improving repeat.
- 2026-08-01: Fixed the emergency executor to retain within-pulse peak clearance across post-command deceleration. The new regression follows a 0.45 -> 0.52 -> 0.48 m dynamic-obstacle trace and authorizes another bounded pulse only after full stop. Existing rear-clearance, separation-direction, swept-footprint, per-pulse duration, and maximum-eight-pulse constraints remain active. Ruff, formatting, strict mypy, and all 222 tests pass.
- 2026-08-01: Completed a same-commit cross-family temporary-blockage pair after the executor correction. Base collided at 37.995 s; the full DAgger hierarchy reached the physically verified goal at 80.919 s with 0.195 m terminal error and 0.781 m minimum human distance. Both proxy-to-LiDAR gates passed at 100%, and raw hashes are recorded. The observed escape used deterministic emergency turn/forward motion rather than a learned temporary subgoal, so it is retained as hierarchical-system evidence, not isolated network evidence.
- 2026-08-01: Replaced the emergency logger's BACKUP/non-BACKUP boolean with exact mode-transition telemetry. STOP, BACKUP, TURN_LEFT, TURN_RIGHT, and FORWARD now receive stable reason labels; the fixed 25-action contract remains unchanged. Five parameterized tests cover the mapping and all 227 offline checks pass.
- 2026-08-01: On the untouched high-density group-blocking validation seed, Base collided at 42.990 s while the full hierarchy reached the physically verified goal at 112.887 s with 0.197 m terminal error. Both LiDAR gates passed at 100%. The learned policy selected multiple temporary subgoals (IDs 2, 3, and 11), while exact telemetry separately records bounded safety modes. Added an automatically generated cross-family table and flat-vector PDF figure to the IEEE manuscript; the two single-seed families remain descriptive only.
- 2026-08-01: Completed a strict same-commit four-method group-blocking check. Base and Standard Recovery collided; Heuristic and DAgger reached the physical goal. DAgger finished 23.44 s sooner than Heuristic, used 211 fewer recovery samples, and maintained 0.178 m greater minimum human distance in this run. All four sensor gates passed. The manuscript now generates a dedicated mechanism table from the four-row CSV; the single seed is explicitly non-statistical.
- 2026-08-01: Retained the first opposite-streams validation failure without deletion. Base collided after 3.497 s; DAgger avoided collision but timed out with only 0.200 m net progress, 1,633 recovery samples, and negative progress over the final minute. Both LiDAR gates passed at 100%. This identifies an uncovered recurrent-flow distribution rather than a threshold target: the next training step collects policy-visited states only from opposite-streams train scenarios and relabels them with the privileged expert.

- 2026-07-29: Began Gate 0; completed non-mutating system inventory and created the repository skeleton.
- 2026-07-29: Created and locked `ramp-offline`; verified CUDA access and repaired inherited ROS pytest contamination. Offline quality checks pass.
- 2026-07-29: Accepted Gate 0 using the pinned Arena Humble Docker fallback. Gazebo spawned Jackal; clock, TF, LiDAR, odometry, and NavigateToPose were live; goal submission and controlled teardown passed.
- 2026-07-29: Implemented the first modular core and ROS architecture. Eighteen offline tests, strict mypy, three-package colcon build, and colcon test-result pass.
- 2026-07-29: DWB reached a static PointGoal. Generated and Arena-validated 72 stress scenarios with disjoint splits and previews.
- 2026-07-29: Added versioned JSONL/HDF5 episode logging. A single-agent run reached its goal; a two-agent crossing-flow run produced a real collision at 0.6852 m center distance. Gate 1 now proceeds to 10-seed failure mining.
- 2026-07-30: Added a 30-episode fixed-seed mining manifest with previews, resume-safe execution, and per-episode logs. Diagnosed and corrected Arena's dynamic `static/shelf` asset plus its oversized 3-D software-rendered LiDAR. After correcting the human-model metadata and rerunning rather than reusing data, the first canonical head-on run ended in a real collision at 112.9203 simulated seconds.
- 2026-07-30: Accepted Gate 1 after 30 valid fixed-seed runs and 16,140 samples. Failure rates were corridor 100%, doorway 100%, and crossing 80%; six invalid resets were separately retained and excluded. Generated three raw-data trajectory videos and a combined PDF. Advanced to rule detection and heuristic recovery.
- 2026-07-30: Implemented and validated the observable rule detector, dense temporal label generator, and ROS2 detector node. Labeled all 30 Gate 1 episodes in one HDF5 file; 34 committed offline tests and the real-message ROS detector smoke pass. Next is heuristic Nav2 temporary-goal execution and original-goal rejoin.
- 2026-07-30: Integrated the goal mux, recovery manager, heuristic policy, directional safety filter, path-local observations, auto-reset patch, and active-status aggregation. Failure-detector, recovery-manager, and goal-mux ROS smokes pass; the offline suite has 64 tests.
- 2026-07-30: Found Arena's fallback visual actors were invisible to LiDAR, invalidating the earlier Gate 1 table for learning claims. Added unique LiDAR/collision cylinders and deterministic robot-occupancy yielding, and marked prior results as superseded.
- 2026-07-30: Corrected-proxy crossing seed 0 produced a development-only paired signal: base collision after 6.891 m progress versus heuristic timeout after 19.004 m progress with 1.205 m minimum human distance. Multi-seed revalidation remains pending.
- 2026-07-30: Completed corrected-proxy B0/B2 crossing evaluation on 20 fixed train seeds. Collision rate changed 65% to 45% but exact McNemar p=0.289; timeouts increased and both methods had zero successes, so Gate 2 remains failed. Added auditable paired statistics and distinct pinned B0/B1/B2 Arena behavior-tree profiles; B1 is now running.
- 2026-07-30: Completed B1 crossing on the same 20 seeds: 12 collisions and 8 timeouts, with no significant paired change from B0. The complete B0/B1/B2 crossing comparison therefore remains a negative Gate 2 result. Fixed and Arena-validated strict simulation-time logging; the full offline suite now passes 71 tests.
- 2026-07-30: Corrected a terminal-outcome bug exposed by strict head-on replay. A sustained top-level Nav2 abort now becomes `PLANNER_FAILURE` after a 5 s replacement-goal grace; the real seed-0 regression ended at 26.6733 simulated seconds with 269 strictly increasing samples. Interrupted pre-fix artifacts are quarantined and excluded; all 75 offline tests pass.
- 2026-07-30: Diagnosed Arena Humble's conflicting AMCL and static ground-truth TF publishers. The pinned known-pose patch reduced path-start/robot disagreement from 6–7 m to 0.047 m median and 0.127 m maximum over 143 samples. All earlier dynamic method tables are superseded pending replay.
- 2026-07-30: Improved collision latching, recovery-history isolation, subgoal preemption settling, and bounded backup. Corrected head-on seed 2 avoided collision and made 4.836 m progress but timed out in a WAIT deadlock, so Gate 2 remains failed.
- 2026-07-30: Implemented the first privileged planning-expert core with 3 s differential-drive rollouts, A*/Pure Pursuit, constant-velocity human prediction, hard collision cost, continuous social/progress/rejoin/smoothness terms, action masks, and margins. Twenty rendered synthetic scenes produced zero illegal selections and zero selected-rollout collisions; corrected the heuristic's 270-degree Jackal scan indexing; full quality checks pass with 117 tests.
- 2026-07-30: Connected corrected Arena JSONL recovery states to the privileged expert HDF5 label format. A 50-state stride smoke produced zero illegal labels and finite selected costs throughout; the expert preferred lateral subgoals in 38 states rather than the heuristic's prolonged WAIT. Zero states satisfied the strict three-second predicted-success criterion, which is retained as an honest limitation pending online Oracle execution.
- 2026-07-30: Deployed the privileged expert online and used nine high-density plus five low-density diagnostic replays to repair the actual recovery/safety chain. The final high-density train replay avoided collision for 120 s but timed out after 4.174 m progress; the final low-density replay avoided collision but exhausted recovery attempts after 79.054 s and 5.140 m progress. Gate 3 remains failed. The verified failure mode is now sequence-level: immediate rejoin repeatedly undoes short recovery actions, so the next method revision is a bounded multi-phase recovery option rather than further single-seed threshold tuning.
- 2026-07-30: Implemented bounded recovery composition, wait escalation, rear-sector observability, non-duplicated footprint clearance, emergency-resume accounting, a privileged predictive trigger, and a longitudinal YIELD option. The hard-stop two-person head-on fallback remains safely unrecoverable. On recoverable crossing-flow low train seed 1200, the online Oracle executed a temporary subgoal, rejoined, and reached the original goal in 101.831 s with no collision; paired Base also succeeded in 102.231 s. This is Gate 3 execution prevalidation, not a performance claim.
- 2026-07-30: Added threat-reversal release and a separately bounded 30 s YIELD duration while preserving the normal 8 s action limit. Doorway low seed 1100 remained a safe timeout after cyclic pedestrians returned and re-blocked the door: 6.105 m progress, 1.106 m minimum human distance. The result is retained as a negative limitation; the full suite passes 154 tests.
- 2026-07-30: Added progress-based recurrent-flow memory, a conservative lateral/REPLAN candidate filter, and per-sample recovery-reason telemetry. The filter preserves the original mask when no escape candidate exists. Offline checks pass with 159 tests and the ROS overlay builds. Two reason-instrumented doorway diagnostics remained safe timeouts and did not enter the recurrent-escape branch because the online YIELD remained one long-lived option; this is recorded as an unvalidated branch rather than an improvement.
- 2026-07-30: Completed a valid medium-density crossing-flow Base/Oracle pair on fixed train seed 1210 after excluding one correctly classified invalid reset. Base collided at 34.532 s with 0.704 m minimum human distance; Oracle used masked temporary goals and REPLAN, remained collision-free, and reached the original goal at 94.639 s with 1.175 m minimum human distance. Raw hashes are recorded in `outputs/pilot/crossing_flow_medium_gate3_pair.csv`; the favorable single pair is not treated as statistical evidence.
- 2026-07-30: Completed fixed-seed low/medium/high crossing-flow density prevalidation. Base reached the goal only at low density and collided at medium/high density; Oracle reached the original goal in all three, with zero collision. High-density Base/Oracle outcomes were collision at 34.765 s versus goal reached at 93.640 s. The six raw hashes are consolidated in `outputs/pilot/crossing_flow_density_gate3_pairs.csv`; comparative Gate 3 acceptance still requires same-manifest heuristic and multi-seed evidence.
- 2026-07-30: Added the same-manifest medium-density Heuristic diagnostic. Base collided after 6.627 m progress; Heuristic avoided collision but timed out after 14.681 m with 425 recovery-action samples; Oracle reached the goal after 20.777 m with 94 recovery-action samples. This single train seed supports the sequence-level value of planning-expert action selection over repeated rule recovery, but is not a statistical claim.
- 2026-07-30: Completed the high-density Heuristic diagnostic and retained the counterexample. Both Heuristic and Oracle reached the goal; Heuristic was 0.500 s faster, kept 0.093 m more minimum human clearance, and used 44 fewer recovery-action samples. This prevents a blanket Oracle-superiority claim and motivates validation of an unnecessary-intervention penalty before large-scale expert labeling.
- 2026-07-31: Ran Base/Heuristic/Oracle on medium validation seed 2210. All succeeded, but the original recovery methods over-intervened: Base 100.866 s/0 actions, Heuristic 118.382 s/202 actions, Oracle 102.597 s/197 actions. Offline replay exposed a hard-coded 3.0 s TTC override and showed that planner-conditioned 1.0--1.5 s TTC retained collision lead time while rejecting most distant crossings.
- 2026-07-31: Selected a 1.5 s planner-conditioned TTC intervention horizon. Validation Oracle retained success at 99.234 s with 30 action samples; train seed 1210 retained recovery from the Base collision, reached the goal at 96.004 s with 1.222 m minimum human distance, 40 actions, and no emergency stop. The 1.0 s candidate is retained as a negative late-trigger ablation. Full checks pass with 162 tests.
- 2026-07-31: Found and fixed policy-dependent scenario phase drift. The actor controller now holds all pedestrians at their initial coordinates until Nav2 is active and the episode logger is subscribed; GoalMux holds zero velocity until the same repeated start signal. The logger starts time at the handshake and aborts a stalled startup after 90 wall-clock seconds.
- 2026-07-31: Stopped updating nonexistent native `ped_*` entities, validated every Gazebo proxy pose response, and wired proxy health into episode outcome classification. A synchronized Base collision measured 0.707 m human-center distance and 0.267 m LiDAR clearance with no rejected pose update.
- 2026-07-31: Completed the first fully synchronized high-density validation triplet. Base collided at 29.104 s, Heuristic remained collision-free but timed out with 944 recovery samples, and Oracle reached the original goal at 96.404 s with 108 recovery samples. The single-seed raw-hash table is `outputs/pilot/crossing_flow_high_validation_sync3_methods.csv`; all pre-handshake comparisons are diagnostic-only.
- 2026-07-31: Corrected `temporary_blockage` from cyclic traffic to finite one-shot routes and added route-specific collision-safe actor yielding. Added a swept-footprint LiDAR action mask and an observable turn/forward emergency escape reflex. All 72 scenarios parse, 168 tests pass, and the ROS overlay builds.
- 2026-07-31: On synchronized high-density train seed 1720 with the final finite-blockage definition, Base ended `PLANNER_FAILURE`, Heuristic timed out, and the privileged Oracle reached the original goal in 105.894 s. The raw-hash table is `outputs/pilot/temporary_blockage_high_train_finite2_methods.csv`; this is execution evidence, not statistical acceptance.
- 2026-07-31: Exported 169 finite-blockage recovery states with complete observable arrays and expert labels: 0 illegal actions and 68 expert-predicted successes. Trained and exported the first action-masked MWBC smoke model; its single-episode holdout reached 0.618 top-1, 0.941 top-3, 0 invalid action rate, and 0.122 expert-cost regret. This validates the pipeline only.
## 2026-07-31

- Aligned offline and online action-mask semantics and regenerated all six initial train shards plus the validation shard.
- Added CPU ONNX inference to `recovery_manager`, configurable model paths, BC episode profile, and inference-environment validation.
- Added mirror-safe episode stacking, scenario-disjoint validation, cost-sensitive diagnostics, train-only speed variants, and a reproducible one-round DAgger orchestrator.
- Ran five train-only DAgger-1 policy episodes. Two generated crossing-flow variants reached the goal in 105.395 s and 99.900 s; all new expert actions were legal.
- Achieved the first held-out learned recovery success: DAgger-1 reached the goal in a crossing-flow case where Base collided and BC-0 timed out.
- Completed DAgger iteration 2 with three new train-only policy trajectories and 230 legal expert labels; the aggregate now contains 14 episodes and 1,383 recovery samples.
- Diagnosed two emergency-backup counterexamples and added sustained-clear hysteresis. Under the corrected executor, DAgger-1 reached the locked crossing-flow validation goal in 2/2 repeats, while DAgger-2 reached only 1/2 and is retained as a negative ablation.
- Added head-on train coverage, multi-scenario epoch selection, bounded learned options, collision-latched masks, swept emergency motion, and a path-corridor constraint after retaining several closed-loop counterexamples.
- Completed a no-deletion repeat-5 pilot on crossing flow: Base 0/5 goals and coverage policy 3/5 goals. The learned policy executed actual +60-degree temporary subgoals; Fisher p=0.167, so the result remains preliminary.
- Regenerated every selected expert shard with deploy-equivalent collision/rejoin/path masks, fixed stale-odometry collision-latch resets, and trained the safety-aligned coverage checkpoint. Scenario-disjoint validation reached 0.910 top-1 with zero invalid or catastrophic actions.
- Completed a second no-deletion repeat-5 crossing pilot: Base was 0/5 goals with 5 collisions; safety-aligned recovery was 3/5 goals with zero collisions and two timeouts. The learned policy used WAIT, BACKUP, and multiple temporary subgoals. Fisher p=0.167, so multi-seed expansion remains required.
- Wrote and compiled the first evidence-linked IEEEtran imitation-only manuscript. Reproducible scripts generate the architecture figure, pilot plot, and LaTeX table; Tectonic resolves BibTeX and creates `paper/main.pdf` with no unresolved references or overfull boxes.
- Repaired the final high-density safety/classification chain: widened the observable turning guard, latched safety at detector frequency, made emergency turn direction persistent, debounced near-range contact, and enabled LiDAR static-contact termination only when scenario geometry declares static obstacles. The fresh high-density replay reached the original goal in 141.891 s with 1.185 m minimum human distance; 197 tests and the ROS overlay pass.
- Diagnosed and removed an unsafe task-aligned emergency-forward experiment, added progress-gated bounded retreat, synchronized privileged actor time to completed Gazebo pose requests, and filtered the Jackal's 0.16--0.33 m self-return cluster only in open maps. The resulting crossing-flow replay reached the goal in 176.923 s with 0.995 m minimum human distance; the static temporary-blockage case remains a retained timeout. The suite now passes 202 tests.
- Froze `100b09f` for an independent medium-density validation pair. Base collided at 29.204 s; learned recovery avoided collision but timed out at 179.920 s after 9.210 m progress. This is retained as a safety-versus-completion negative result.
- Invalidated pre-kinematic dynamic comparisons after proving that static Gazebo proxy geometry could lag privileged pedestrian truth. Converted proxies to gravity-disabled kinematic links, made privileged route state commit only after pose confirmation, and added an automated privileged-to-LiDAR gate. Under the final semantics, Base collided at all three crossing-flow densities while DAgger reached the goal at all three; every selected episode passed the sensor gate. This is a three-pair execution precheck, not statistical evidence.
- Superseded the kinematic-link precheck after direct Gazebo pose inspection proved that accepted model updates could still leave collision bodies near initial positions. Dynamic gravity-disabled proxies now move physically, and actual Gazebo robot/pedestrian poses feed evaluation-only topics. The first admissible pair is Base collision versus DAgger goal reach at 173.9 s; its 0.733 m minimum centre distance and 832 recovery samples require further work.
- Superseded that pair after exposing rigid-body impulse artifacts, missing no-reset/mux guards in direct debug calls, and 0.93 m wheel-odometry drift. The verified-pose profile uses contactless rendered pedestrians, actual-pose collision evaluation, protected launch semantics, pose-derived known localization, and physical goal confirmation. On commit `2164e08`, Base collided at 29.47 s while DAgger physically reached the goal at 98.43 s with 1.203 m minimum human distance; both sensor gates passed 100%. The IEEE TeX, generated table/figure, and PDF now use only this artifact and explicitly make no statistical claim.
- Added independent validation seed 2202 after introducing a fixed one-second asynchronous physical-goal confirmation window. Same-commit Base and DAgger both physically reached the goal in 93.606 s and 92.907 s; DAgger used only 29 temporary-subgoal samples. This is one nominal non-degradation pair, while the first immediate-confirmation attempt remains an unchanged simulator-failure artifact.
- Collected a disjoint train-only opposite-stream DAgger trajectory and unified the online/offline empty-path fallback. The repaired expert pipeline labeled 273 policy-visited states with zero illegal actions and 266 predicted-success actions; all 229 offline tests and the three-package ROS build pass. Held-out validation data remain excluded from training.
- Completed DAgger iteration 4 with 1,660 train samples across 13 episodes. On the unchanged scenario-disjoint validation set, the selected epoch reports 0.947 top-1, 1.000 top-3, zero invalid/catastrophic actions, and 0.0107 expert-cost regret. The checkpoint remains a candidate until closed-loop validation.
- Diagnosed the candidate's first train replay as an intermittent bilateral Jackal GPU-LiDAR self-return rather than a physical collision. Added shared geometric suppression that preserves unilateral walls and interior contacts; 231 tests and the ROS overlay pass. The original false-positive outcome is retained unchanged.
- Retained the post-filter train timeout: collision-free, 2.378 m progress, but 695 emergency-turn samples and repeated side reversals across sub-three-second hazard gaps. Added a configurable five-second turn-preference memory with reset tests; the full suite passes 233 tests.
- Audited all 14 historical LiDAR-footprint terminations after another train false positive. None had more than two consecutive sub-0.12 m frames. Raised only the static LiDAR contact debounce to three 10 Hz frames; independent physical human-contact detection remains unchanged.
- A later three-frame artifact proved debounce insufficient. Added exact oriented shelf-footprint collision evaluation from scenario poses and actual Gazebo robot pose, while retaining LiDAR fallback for unsupported models. The policy still receives only observable scan/odometry inputs; 235 tests and the ROS overlay pass.
- Rejected the train-only five-second turn-memory candidate: it removed all turn-side switches but worsened net progress from +2.378 m to -0.146 m and still timed out. Restored within-hazard-only persistence and retained the run as a negative method ablation.
- Aligned offline expert and online policy sequence semantics with a shared failure-conditioned bounded-WAIT mask. Sequence relabeling reduces WAIT from 227/342 to 209/342 and optimistic predicted-success labels from 294 to 276 with zero illegal actions; 235 tests pass.
- Completed DAgger iteration 5 with 2,002 samples across 14 train episodes. Scenario-disjoint validation is 0.922 top-1, 1.000 top-3, zero invalid/catastrophic actions, and 0.0154 regret; the candidate remains unselected pending closed-loop checks.
- Classified the first iteration-5 launch as a zero-sample `SIMULATOR_FAILURE` after Nav2 lifecycle startup timed out. The runtime now writes auditable outcome JSON even when failure occurs before the episode logger exists; retry uses a new episode ID.
- Rejected iteration 5 after a valid train retry timed out with 0.196 m progress versus iteration 4's 2.378 m. Lower WAIT use was offset by 317 BACKUP samples and persistent emergency control. Removed failure-conditioned immediate WAIT exhaustion while retaining sequence-aware three-WAIT labeling as a future ablation.
- Added an evidence-linked opposite-stream failure-analysis CSV, generated LaTeX table, and publication-ready vector figure. The compiled IEEE manuscript now retains the validation safe-stagnation counterexample and both rejected train corrections; 234 tests and the paper build pass.
- Added a current verified-pose high-density overtaking pair at frozen commit `324fcdf`: DWB collided at 82.02 s; triggered DAgger physically reached the goal at 178.39 s with 0.224 m terminal error and 1.156 m minimum human distance. Both sensor gates pass 100%; the narrow timeout margin is retained as a limitation.
- Retained a same-commit blind-corner counterexample: DWB physically hit declared static geometry at 49.48 s; triggered DAgger avoided collision and made more progress but timed out 8.16 m from the goal. Both pedestrian LiDAR reports are explicitly inconclusive because no human entered the 1.3 m audit radius.
- Reproduced the same static-corner delay on train seed 1320 and implemented a static-aware emergency-margin candidate. Exact shelf parsing is now shared by evaluator and controller; nearest LiDAR endpoints matching known geometry use footprint-safe static margins while unknown/dynamic returns retain the larger social margin. Offline validation passes 238 tests and the ROS overlay.
- The first static-aware train replay improved the timeout from 5.09 m to 1.01 m remaining but did not pass. Removed duplicated tangential braking inflation only for matched known-static nearest returns; forward braking, swept-footprint checks, and all dynamic margins remain intact. The refinement passes 239 tests and the ROS overlay.
- The refined static-aware candidate passed the train closed-loop gate: physical goal reach at 173.89 s and 0.195 m error, versus two retained timeouts. Minimum human distance was 1.285 m; the three-version CSV preserves raw hashes. Held-out validation is next without further tuning.
- On held-out blind corner, same-commit DWB collided at 45.99 s while the static-aware hierarchy avoided collision but timed out 5.385 m from goal. This improves the pre-fix 8.162 m remainder but is still a failed recovery. The learned sensor gate passes 196/196; no further tuning is authorized from this validation result.
- Rejected the radial no-braking refinement after it physically hit a temporary-blockage door frame at 72.49 s during an emergency turn. Restored the full stopping-distance term despite its train success; the unsafe raw outcome remains immutable. The first-stage static endpoint classifier now faces an independent safety replay.
- Rejected and removed the remaining static endpoint classifier after its restored-braking replay misclassified a pedestrian beside the doorway and collided at 0.705 m centre distance. The regression CSV retains the historical goal and both unsafe candidates. Recovery control is back to uniform dynamic-safe margins; shelf geometry remains evaluation-only.
- Repeated temporary blockage under the restored selected controller and obtained a same-commit negative pair: Base collided at 37.995 s and DAgger at 40.027 s. A two-centimetre backup-gain candidate avoided collision but timed out, and it also regressed the frozen overtaking success to timeout. The candidate is removed, both raw hashes are retained, and the paper no longer treats the historical temporary-blockage success as repeatable evidence.
- 2026-08-04: Replaced the missing final-evaluation entry point with a tested
  four-worker runner. Locked a 64-episode test: Base/Triggered-DAgger on all 24 test
  scenarios plus Standard/Heuristic on the eight high-density cases. The selected
  checkpoint is explicitly recorded as uniform BC + DAgger, not MWBC or PPO.
