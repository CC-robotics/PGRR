# Current status

## 2026-08-01 — verified-pose DAgger pilot (active)

- The selected safety-aligned DAgger checkpoint has three current-version high-density validation goal reaches under frozen commit `8577ff1`. DWB reached 2/3 goals and collided once; DAgger reached 3/3 goals with no collision.
- Learned terminal physical goal errors are 0.215, 0.287, and 0.260 m. Median minimum robot--human centre distance changes from 0.927 m for DWB to 1.027 m for DAgger.
- All six evaluation-only LiDAR consistency gates pass; five are 100% visible and the remaining gate passes 77/80 near-human samples. Maximum pose-derived localization disagreement is below 0.142 m.
- Learned runs use 165--560 non-CONTINUE recovery samples, including WAIT, BACKUP, and temporary subgoals. Median terminal time increases from 91.7 to 128.4 s, so the safety--time trade-off is a current limitation.
- `paper/main.tex`, its generated three-seed table/figure, and `paper/main.pdf` are regenerated from tracked CSV evidence. The draft states that three validation seeds are insufficient for significance.
- Cross-family validation on `temporary_blockage_high_validation_s02720` is a retained failure: Base collided at 38.00 s and DAgger collided at 41.03 s after 71 recovery samples. Both LiDAR gates pass 100%. Replay shows collision risk remained zero while an off-axis return closed from 0.83 to 0.60 m; the configured 0.10 m/s radial-closing threshold is currently unused in the rule implementation. A detector correction and fresh same-manifest pair are required.
- The detector now applies the existing 0.10 m/s threshold only when the nearest return lies outside the forward/wide sector and the robot is not turning quickly. Unit tests preserve fixed-wall and jitter rejection. Offline replay advances the temporary-blockage warning from 39.83 to 34.13 s while changing crossing-flow onset by about 0.1 s; online validation and nominal false-trigger checks are pending.
- Online replay under `461ddc6` still collided: Base at 38.00 s and DAgger at 40.49 s. Recorded collision risk stayed zero until the final second despite the reconstructed trend, so the trend-only correction is insufficient. The next validation-only candidate uses the known empty static map to apply a 0.70 m omnidirectional dynamic-return trigger after self-return filtering; static-geometry scenarios keep it disabled.
- The map-conditioned 0.70 m trigger is implemented and tested: it is enabled only when the compiled scenario declares zero static obstacles, after filtering impossible Jackal self-returns below 0.34 m. Static-geometry scenarios retain a zero/disabled threshold. The full suite passes 221 tests; ROS build and online temporary-blockage/nominal checks are next.
- The fresh `e923536` temporary-blockage pair remains negative: Base collided at 37.995 s and DAgger at 39.993 s after 65 non-CONTINUE samples; both LiDAR consistency gates pass. The scenario declares 20 doorway wall objects, so the open-map guard was correctly disabled. Emergency braking began at 35.498 s and one bounded BACKUP increased measured clearance from 0.453 to 0.522 m, but the executor discarded that peak while decelerating and switched to rotation; the approaching pedestrian then collided. This is now an executor-state regression, not a reason to relax the static-map detector threshold.
- Emergency escape now retains the maximum observed clearance during each bounded BACKUP pulse and uses that value only after the robot has stopped to decide whether the existing 0.05 m improvement rule authorizes another pulse. Rear observability, swept-footprint permission, and the eight-pulse hard cap are unchanged. A deceleration regression test reproduces the 0.45 -> 0.52 -> 0.48 m trace; the complete offline suite passes 222 tests. Fresh online validation is pending.
- The fresh same-commit `0205d6e` temporary-blockage pair converts the Base collision at 37.995 s into a verified physical goal reach at 80.919 s. Terminal physical goal error is 0.195 m, minimum human-centre distance is 0.781 m, maximum localization disagreement is 0.130 m, and both LiDAR gates pass at 100% (31/31 Base, 181/181 recovery). The recovery run contains 132 non-CONTINUE samples. Trace inspection attributes the escape to the deterministic safety layer's turn and 0.12 m/s forward pulses, not to a learned temporary-subgoal selection, so this supports the complete hierarchy only and is not isolated DAgger-policy evidence.
- Next: expand the frozen validation pilot across additional seeds and scenario families before locking any final test manifest. PPO and the learned detector remain optional and are not claimed.
- Expansion seed 2220 is a retained counterexample: DWB reached the goal in 92.91 s, while DAgger timed out after 179.92 s and 1401 recovery samples. Its last 60 s were a pure emergency-turning live-lock with multiple fallback pedestrians frozen inside their 1.3 m avoidance radius. The actor rule now permits an already-close pedestrian to take a route step only when that step increases physical robot clearance; the conservative expert still models possible stop-short behavior. Fresh same-manifest replay is required.
- The first post-yield-fix replay preserved Base success and changed DAgger from timeout to a success callback, but its final 10 Hz row preceded the 2 Hz physical confirmation frame and remained 0.319 m from goal. New outcome artifacts include localized and physical terminal distances captured at finalization; the incomplete-evidence replay remains diagnostic and a fresh pair is required.

## Gate 2 failed / Gate 3 — privileged Oracle prevalidation (in progress)

### Completed

- Read-only host preflight: Ubuntu 22.04.5, 62 GiB RAM, 442 GiB free disk, RTX 5090, ROS2 Humble present.
- Created a new Git repository on `teacher/reference`; no pre-existing target files were overwritten.
- Created `ramp-offline` with Python 3.10 and dual dependency locks.
- Validated Torch 2.13.0 + CUDA 13.0 on the RTX 5090.
- Passed Ruff, formatting, strict mypy, and 34 committed offline tests at the rule-detection stage.
- Installed the pinned Arena Humble fallback in the isolated `ramp-arena:humble` image without modifying host ROS.
- Built 48 Arena overlay source packages on the binary Humble base and selected Gazebo 8.14.0, Jackal, and DWB.
- Passed the automated Xvfb/software-rendered Arena smoke test.
- Added and tested ROS-independent geometry, occupancy, differential-drive, braking, A*, Pure Pursuit, observation, action-mask, and recovery-state primitives.
- Added the fixed 25-action contract and YAML IDs.
- Built `ramp_msgs`, `ramp_ros`, and `ramp_bringup`; `colcon test-result` reports zero failures.
- Passed static PointGoal navigation with DWB and a task-generated goal (`GOAL_REACHED`).
- Compiled 72 deterministic stress scenarios (8 families x 3 densities x 3 splits), with split-safe manifests and previews; all parse and load through the installed Arena schema.
- Added an online JSONL episode logger plus validated multi-episode HDF5 conversion with public/privileged field separation.
- Passed a single-agent dynamic episode (`GOAL_REACHED`, 158 samples) and reproduced a non-simulator multi-agent collision (`COLLISION`, 532 samples).
- Materialized and Arena-validated 30 fixed Gate 1 mining episodes (three core families x 10 seeds), each with a preview and hash.
- Stabilized headless corridor physics with locked planar-LiDAR and truly-static shelf asset overrides.
- Completed the metadata-locked canonical head-on seed 0 run: `COLLISION`, 1,138 samples, 112.9203 simulated seconds, 0.6835 m minimum human-center distance.
- Completed all 30 fixed Gate 1 algorithm episodes: 25 collisions, 3 timeouts, and 2 goal reaches; 16,140 samples and 30 unique raw hashes.
- Generated a three-panel trajectory PDF and three 15-second MP4 evidence videos directly from raw recorded episodes.
- Implemented configurable observable-only collision-risk, freeze, oscillation, and deadlock rules with exact time-window boundary tests.
- Generated dense offline labels for all 30 Gate 1 episodes: 16,140 samples in one HDF5 artifact with pre/post windows, onset/end, time-to-failure, and hard-negative metadata.
- Added the ROS2 failure detector node and passed an actual ROS message smoke test with a speed-dependent imminent-collision trigger.
- Added the command mux, Nav2 temporary-goal manager, safe 25-action heuristic policy, original-goal restoration, and recovery-aware logging.
- Patched the task generator so `auto_reset: false` is honored.
- Replaced LiDAR-invisible visual actors with uniquely named cylindrical LiDAR/collision proxies and deterministic robot-occupancy yielding. Simulator truth remains excluded from policy observations.
- Passed 75 offline tests and ROS smokes for failure detection, temporary-goal/rejoin recovery, command arbitration, paired statistics, strict simulator timestamps, terminal planner-abort tracking, and locked baseline profiles.
- Observed a development-only crossing seed-0 signal: base DWB collided after 6.891 m progress; heuristic recovery avoided collision and made 19.004 m progress, ending 1.996 m from the goal at timeout.
- Extended the corrected train-split mining manifest to 20 fixed seeds per core family and generated deterministic previews for all additions.
- Completed 20 paired corrected-proxy crossing episodes for B0 and B2. B0 produced 13 collisions/7 timeouts; B2 produced 9 collisions/11 timeouts; neither reached the goal.
- Added deterministic paired bootstrap intervals, exact McNemar, and Wilcoxon reporting. The crossing collision-rate difference is -0.20 (95% bootstrap CI [-0.45, 0.05], exact McNemar p=0.289); mean progress difference is +0.143 m (Wilcoxon p=0.898).
- Separated B0, B1, and B2 with pinned Arena behavior trees and recorded their installed-file SHA256 values.
- Completed all 20 B1 crossing episodes: 12 collisions, 8 timeouts, and no goal reaches. Versus B0, the collision-rate difference is -0.05 (95% bootstrap CI [-0.35, 0.25], exact McNemar p=1.0) and mean progress difference is -0.616 m (Wilcoxon p=0.812).
- Fixed slow-simulator duplicate logging. A real 5 s Arena smoke produced 51 samples, 51 unique stamps, and a strictly increasing sequence from 0.0 to 4.995 s; legacy conversion reports equal-stamp removal and rejects backwards time.
- Fixed terminal Nav2 abort classification. A real corrected head-on B0 seed now ends as `PLANNER_FAILURE` after 26.6733 simulated seconds and 269 strictly timed samples, rather than drifting until a false timeout.
- Removed the conflicting Gazebo AMCL source from the known-pose profile. A real 20 s replay keeps Nav2 path starts aligned to robot odometry within 0.047 m median and 0.127 m maximum.
- Added collision-risk latching, recovery-motion exclusion from freeze/deadlock windows, asynchronous subgoal-command settling, first-response WAIT, and a one-BACKUP-per-sequence cap.
- Implemented the ROS-independent privileged planning expert, cost decomposition, constant-velocity human rollout, fixed-mask/margin label, and a 20-scene PDF validator. Corrected the 180-beam heuristic mapping to the Jackal's actual 270-degree field of view. The complete quality suite passes 117 tests.
- Composed short expert decisions into recovery options, added bounded WAIT escalation, distinguished unobserved rear LiDAR from low clearance, removed double footprint inflation, and made emergency stops resume the interrupted recovery sequence without consuming a new recovery attempt.
- Added a privileged constant-velocity Oracle trigger and an interpretable longitudinal YIELD option. These are confined to the Oracle upper bound and are not available to the formal observable policy.
- Completed the first valid online Oracle recovery/rejoin success on `crossing_flow_low_train_s01200`: `GOAL_REACHED` after one temporary-subgoal intervention. Generated a raw-hash-linked Base/Oracle pair CSV.
- Added reset-validity classification for a goal that never becomes active. The complete quality suite now passes 164 tests and the three-package ROS overlay builds.
- Added a conservative recurrent-flow escape candidate filter: repeated YIELD activation without 0.75 m task progress may expose only already-valid lateral subgoals or REPLAN to the planning expert; if none exists, the original safe mask is retained. Raw episodes now record the recovery decision reason.
- Added an explicit episode-start handshake across Nav2, GoalMux, the deterministic actor controller, and the logger. Pedestrian routes remain at their configured initial coordinates and the command mux remains stopped until the logger is subscribed. Gazebo proxy pose responses are checked; any rejected update is immediately classified as `SIMULATOR_FAILURE`.

### Commands

```bash
make preflight
make conda
make arena
make smoke
make test
make build
make scenarios
make mine-failures SEED=0
env -u CONDA_PREFIX -u VIRTUAL_ENV scripts/arena/static_navigation.sh
env -u CONDA_PREFIX -u VIRTUAL_ENV RAMP_EPISODE_ID=ramp_dynamic_single_base_dwb_gate1 \
  RAMP_EPISODE_TIMEOUT_S=60 scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/ramp_dynamic_single.json
env -u CONDA_PREFIX -u VIRTUAL_ENV \
  RAMP_EPISODE_ID=crossing_flow_low_train_s01200_base_dwb_gate1 \
  RAMP_EPISODE_TIMEOUT_S=200 scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_low_train_s01200.json
scripts/bootstrap/arena_container.sh bash -lc \
  'cd /workspace/ros_ws && colcon test && colcon test-result --verbose'
conda run -n ramp-offline python scripts/data/label_failures.py \
  --results outputs/pilot/baseline_failure_mining.csv \
  --output data/interim/gate1_failure_labels.h5 \
  --summary data/manifests/failure_label_summary.json
scripts/arena/smoke_failure_detector.sh
scripts/arena/smoke_recovery_manager.sh
scripts/arena/smoke_goal_mux.sh
```

### Acceptance results

- Host resource recommendations: PASS.
- ROS environment isolation: PASS; runtime reports Humble and system `bondcpp` while the invoking shell remains untouched.
- Offline environment isolation: PASS; inherited ROS Python paths are cleared and regression-tested.
- Arena smoke test: PASS. `/clock`, TF, LaserScan, Odometry, and NavigateToPose were discovered; one Nav2 goal was accepted; controlled cleanup completed.
- Offline architecture tests: PASS, including deterministic scenario and HDF5 regression coverage; Ruff, format check, and strict mypy pass.
- Project ROS overlay: PASS, 3 packages built; colcon reports 0 errors and 0 failures.
- Static navigation: PASS, `GOAL_REACHED`.
- Single-agent dynamic navigation: PASS, `GOAL_REACHED`, 15.6843 simulated seconds.
- Multi-agent failure reproduction: PASS, `COLLISION` at 0.6852 m center distance; not a simulator failure.
- Scenario catalog: PASS, 72 generated stress files plus acceptance fixtures; train/validation/test IDs are disjoint.
- The previously accepted 30-episode Gate 1 table is **superseded and ineligible for method claims** because the visual actors were absent from LiDAR. Its raw files remain provenance evidence; corrected paired baselines must be rerun before Gate 1 is accepted again.
- Failure-mining infrastructure: PASS; 30 scenarios parse in the installed Arena version, checkpoint CSV writes atomically, and completed outcomes resume without overwrite.
- Head-on mining seed 0: PASS as a reproducible algorithm failure (`COLLISION`), not a simulator failure.
- Simulator/reset exclusions: 6 `INVALID_RESET` attempts are reported separately and excluded; all corresponding fixed seeds later produced valid episodes.
- Failure evidence: `outputs/figures/baseline_failure_trajectories.pdf` and `outputs/videos/baseline_failure_*_seed00.mp4` pass PDF/FFmpeg validation.
- Rule/label tests: PASS; normal motion, goal-reached stationary state, turn noise, short stops, exact freeze/oscillation/deadlock windows, and imminent collision are covered.
- Gate 1 label artifact: PASS; 30 episodes, 16,140 samples, no NaN/Inf, with 2,830 collision-risk, 2,143 freeze, 0 oscillation, and 1,221 deadlock positives. The zero oscillillation count is retained rather than synthesized.
- ROS detector smoke: PASS; a 1.0 m/s observation with 0.20 m clearance publishes collision risk 1.0 and a triggered status.
- Recovery manager smoke: PASS; a temporary goal is accepted and the original `(5, 0)` goal is restored.
- Goal mux smoke: PASS; normal/subgoal pass through, WAIT/terminal output zero, and BACKUP outputs `-0.15 m/s`.
- Corrected-proxy crossing 20-seed pairing: COMPLETE but Gate 2 FAIL. Collision frequency fell from 13/20 to 9/20, but the paired result is not significant; timeout frequency rose from 7/20 to 11/20; both success rates are zero. These train-split pilot results are retained as a safety/efficiency tradeoff, not a method-improvement claim.
- Standard-recovery crossing pairing: COMPLETE but no improvement claim. B1 has 12/20 collisions and 8/20 timeouts versus B0's 13/20 and 7/20; both paired collision and progress tests are non-significant and all success rates are zero.
- Corrected crossing startup exclusions: 8 `INVALID_RESET` attempts are reported separately; all three methods ultimately have 20 valid algorithm outcomes.
- Planner-abort regression: PASS. Replacement active goals suppress stale abort records; an unopposed abort must persist for 5 s before B0/B1 terminate. B2 remains recoverable and reports `PLANNER_FAILURE` only when its recovery manager reaches `FAILED`.
- Known-pose TF regression: PASS. The 20 s seed-2 smoke made 3.384 m progress; 143 path samples had 0.047 m median path-start error and no AMCL/costmap-bound conflict.
- Expert synthetic validation: PASS for implementation smoke only. Twenty scenes, zero illegal selected actions, zero selected-rollout collisions, and 20 predicted-success labels under the selected yielding-human model. This is not an Arena Oracle comparison and does not pass Gate 3.
- Arena-to-expert labeling smoke: PASS as a data-pipeline check. Fifty recovery-relevant states from the corrected known-pose head-on seed-2 episode produced 50 finite legal labels and zero illegal selections. The expert selected lateral subgoals in 38/50 states, WAIT in 2/50, BACKUP in 2/50, and other special actions in 8/50. None met the current three-second rejoin-based `predicted_success` criterion, so this artifact verifies labeling and shows that prolonged WAIT is not the expert's preferred response; it does not establish Oracle recovery success.
- Deterministic start/proxy regression: PASS online. The synchronized first frame contains the robot exactly at `(5, 12)` and all six pedestrians exactly at their scenario initial coordinates. The corrected Base collision has 0.707 m human-center distance and 0.267 m LiDAR clearance, while Gazebo reports no rejected proxy update. This replaces startup-phase-dependent runs for comparative use.
- Synchronized high-density validation precheck: Base collided at 29.104 s after 6.824 m progress; Heuristic avoided collision but timed out at 119.913 s after 7.259 m progress and 944 recovery samples; Oracle reached the original goal at 96.404 s after 20.777 m progress with 108 recovery samples. Minimum human distances were 0.707, 0.834, and 0.974 m, respectively. The raw-hash-linked source is `outputs/pilot/crossing_flow_high_validation_sync3_methods.csv`. This is one validation seed and is not a significance claim.
- Finite-blockage train precheck: after correcting the scenario to one-shot routes, Base ended `PLANNER_FAILURE` at 73.493 s, Heuristic timed out, and Oracle reached the original goal at 105.894 s. Oracle made 16.779 m progress with 0.959 m minimum human distance and 0.445 m minimum LiDAR clearance. The auditable source is `outputs/pilot/temporary_blockage_high_train_finite2_methods.csv`; one seed is not a significance claim.
- MWBC pipeline smoke: 169 recovery states, 0 illegal expert actions, 68 predicted-success labels; the exported model has 0 invalid selections and single-episode holdout top-1/top-3 of 0.618/0.941. This random within-episode split is explicitly excluded from paper claims; scenario-disjoint data remains required.
- **Supersession boundary:** all dynamic comparative results below this line were generated before the explicit start handshake and unchecked-proxy-response fix. They remain useful diagnostic provenance but are ineligible for paired method claims. Trigger design choices remain frozen until revalidated on synchronized validation episodes.
- Historical single-step Oracle diagnostics: execution path passed but the head-on outcomes failed. High-density train seed 2 completed 120 s without collision and made 4.174 m net progress; the earlier low-density version remained collision-free but exhausted its recovery budget. These diagnostics motivated D-017 and are excluded from accepted comparisons.
- Sequence-level Oracle execution: PASS on one recoverable train episode, but Gate 3 remains pending multi-seed validation. In crossing-flow low seed 1200, Base and Oracle both reached the goal. Base used 102.231 s with 1.272 m minimum human distance; Oracle used 101.831 s with 1.244 m minimum human distance and a 2 s temporary-subgoal intervention. This single pair establishes execution and rejoin, not superiority. The auditable source is `outputs/pilot/crossing_flow_gate3_pair.csv`.
- Medium-density paired Oracle evidence: PASS for one fixed train seed. On `crossing_flow_medium_train_s01210`, Base collided with a human at 34.532 s after 6.627 m progress and 0.704 m minimum human distance. Oracle reached the original goal at 94.639 s after 20.777 m progress, with zero collision, 1.175 m minimum human distance, and masked subgoal/REPLAN interventions. The raw-hash-linked source is `outputs/pilot/crossing_flow_medium_gate3_pair.csv`. This is a favorable single pair, not a significance claim.
- High-density paired Oracle evidence: PASS for one fixed train seed. Base collided at 34.765 s after 6.787 m progress and 0.704 m minimum human distance. Oracle reached the goal at 93.640 s after 20.777 m progress, with zero collision, 1.036 m minimum human distance, and 83 recovery-action samples including subgoals, WAIT, and REPLAN.
- Descriptive density sweep: Base outcomes were `GOAL_REACHED`, `COLLISION`, `COLLISION`; Oracle outcomes were `GOAL_REACHED` in all three low/medium/high train scenarios. All six raw hashes are consolidated in `outputs/pilot/crossing_flow_density_gate3_pairs.csv`. This establishes density-level execution prevalidation only; three distinct scenarios with one seed each are not a statistical sample.
- Same-manifest medium-density method diagnostic: Base collided, Heuristic remained collision-free but timed out after 14.681 m progress with 425 recovery-action samples, and Oracle reached the goal with 20.777 m progress and 94 recovery-action samples. This demonstrates a concrete sequence-level Oracle advantage over the rule policy on seed 1210, while also showing that Heuristic improves safety without completing the task. The raw-hash-linked source is `outputs/pilot/crossing_flow_medium_gate3_methods.csv`.
- Same-manifest high-density counterexample: Base collided, while both Heuristic and Oracle reached the goal. Heuristic was slightly faster (93.140 s versus 93.640 s), maintained a larger minimum human distance (1.129 m versus 1.036 m), and used fewer recovery-action samples (39 versus 83). The source is `outputs/pilot/crossing_flow_high_gate3_methods.csv`. Oracle is therefore not claimed to dominate the rule policy; its high-density over-intervention motivates an explicit intervention-efficiency term/analysis before demonstration generation is scaled.
- Medium-density validation seed 2210: Base, Heuristic, and the original Oracle all reached the goal. Base used 100.866 s with zero intervention; Heuristic used 118.382 s and 202 recovery-action samples; original Oracle used 102.597 s and 197 samples. This independently confirmed over-triggering in a normal solvable episode.
- Planner-conditioned TTC trigger ablation: selected 1.5 s after validation. On validation seed 2210 it reduced Oracle intervention samples from 197 to 30 and navigation time from 102.597 s to 99.234 s while preserving success. On train seed 1210, where Base collided at 34.532 s, the selected trigger retained Oracle success at 96.004 s, increased minimum human distance from the legacy Oracle's 1.175 m to 1.222 m, reduced interventions from 94 to 40, and produced zero emergency-stop samples. The 1.0 s candidate also succeeded but triggered 83 emergency-stop samples and is rejected as too late. Sources are `outputs/pilot/crossing_flow_medium_validation_trigger_ablation.csv` and `outputs/pilot/crossing_flow_medium_train_trigger_ablation.csv`.
- Doorway Oracle diagnostic: valid but unsuccessful. The extended YIELD option prevented periodic rejoin pulses and reached the doorway before cyclic pedestrians returned; the episode then ended `TIMEOUT` at 119.947 s with 6.105 m net progress, zero collision, 1.106 m minimum human distance, and 0.755 m minimum LiDAR clearance. The raw-linked row is `outputs/pilot/doorway_gate3_oracle.csv`.
- Safety regression suite: PASS. The online iterations exposed and fixed task-path corruption, stale CONTINUE goals, non-receding expert actions, repeated-WAIT cost omission, unsafe pending-state command leakage, turning-sweep detector coverage, footprint braking distance, unsafe emergency backup, emergency-release command pulses, emergency interruption accounting, rear-sector observability, double obstacle inflation, the legacy 3.0 s TTC runtime override, policy-dependent actor phase, and unchecked proxy pose updates. The full offline suite now passes 164 tests and the three-package ROS overlay builds.

### Failures

- The invoking shell had Conda base active and ROS Iron selected. Runtime scripts must clear this and source Humble explicitly.
- Native Arena installation needs sudo and the official installer contains a broad `$HOME/.pyenv` removal, so it was contained with Docker `runc`.
- The official Humble profile provides Gazebo rather than Flatland. The main simulator for this profile is therefore Gazebo; this is a recorded platform fallback, not a claimed Flatland result.
- The smoke goal was accepted but later aborted; static point-goal success is deliberately left for Gate 1 rather than misreported here.
- The pinned Arena source references a Gazebo HuNav plugin absent from its installer and depending on an unpublished `arena_people_msgs` package. Dynamic runs use the documented Gazebo kinematic proxy fallback and are not labeled as HuNav social-force runs.
- Legacy Nav2 lifecycle activation is intermittently unreliable; every invalid reset is archived, assigned a fresh ROS domain for bounded retry, and excluded rather than counted as an algorithm failure.
- The earlier dense label artifact was generated before LiDAR-visible pedestrian geometry was fixed and is superseded; it must be regenerated from the corrected baseline.
- Crossing-flow alone does not meet the heuristic MVP acceptance gate: it reduces observed collisions without significance and converts several failures into timeouts instead of successful navigation.
- The first strict head-on batch exposed that terminal NavigateToPose aborts were being recorded as timeouts after arbitrary post-abort motion. Those two partial episodes and logs are quarantined and excluded; no affected row is used in the corrected pilot.
- All B0/B1/B2 dynamic results generated before the known-pose localization patch are superseded for method claims and require paired replay.
- The final bounded heuristic seed-2 replay is safe but unsuccessful: `TIMEOUT`, 4.836 m progress, 0.739 m minimum human distance, with WAIT used for 777/1202 samples. Gate 2 remains failed.
- The two-person head-on corridor remains unrecoverable under the selected deterministic fallback's hard 1.3 m robot-avoidance stop: the two fixed pedestrian lanes span the corridor and the actors have no lateral avoidance behavior. Safe Oracle variants time out rather than inventing a passage. These runs are retained as failure analysis, not used to tune test data or claim recovery success.
- A parallel crossing-flow launch produced one interrupted `SIMULATOR_FAILURE` and one goal-never-active reset. Both are excluded. The logger now classifies a full-horizon no-active-goal/no-movement run as `INVALID_RESET`.
- The first medium-density Base attempt never activated NavigateToPose and remained exactly at its start. It is retained as one additional `INVALID_RESET`; the bounded retry produced the valid collision outcome used in the pair.
- Doorway low seed 1100 remains a negative Oracle case: cyclic two-person traffic returns immediately after the first YIELD release and re-blocks the doorway. YIELD is retained as an interpretable Oracle analysis option, not treated as a universal doorway solution.
- The recurrent-flow lateral escape filter is unit-tested and builds online, but the doorway proxy did not expose a clean second activation: the long-lived YIELD option remained latched across the cyclic interaction. A reason-instrumented 60 s run remained collision-free with 6.056 m progress, but contained no `oracle_recurrent_yield_escape` decision. This branch is not counted as online-validated.
- The first selected-trigger validation attempt was an `INVALID_RESET` with no active NavigateToPose goal and no robot movement. It is excluded; the bounded retry produced the valid result above.
- Five additional high-density setup attempts were classified as `INVALID_RESET` or `SIMULATOR_FAILURE` while developing the synchronization handshake. They have zero valid algorithm evidence and are excluded. A 90 s wall-clock startup watchdog now prevents a missing clock, input, or handshake from consuming the full episode horizon.

### Next

Freeze the selected 1.5 s TTC trigger and D-023 geometry. Expand synchronized Oracle evaluation on train and untouched validation scenarios, then generate a smoke expert dataset only from legal Oracle states. Gate 2 remains failed and Heuristic is retained as a weak baseline; two synchronized scenario families now demonstrate Oracle goal recovery, but Gate 3 remains statistically unaccepted.
## 2026-07-31 — Gate 5 DAgger-1 held-out closed-loop success

- Completed: a single observable LiDAR action mask is now shared by offline expert labeling and ROS inference; rear-unobserved BACKUP is excluded, swept subgoals use a 0.48 m capsule, and every regenerated expert label is legal.
- Completed: Uniform BC, MWBC, and full-cost-sensitive BC were trained with scenario-disjoint validation and exported to TorchScript/ONNX. MWBC and full-cost loss did not improve the selected validation distribution and remain negative ablations.
- Completed: ONNX inference runs inside the Humble Arena container with median logged latency around 0.15 ms and zero masked selections.
- Completed: DAgger iteration 1 aggregated 11 train episodes, 11,706 observations, and 1,153 expert-labeled recovery states. `data/manifests/dagger_iter1_manifest.json` records hashes.
- Initial acceptance candidate: on synchronized `crossing_flow_high_validation_s02220`, Base=`COLLISION` at 29.104 s, Heuristic=`TIMEOUT`, BC-0=`TIMEOUT`, DAgger-1=`GOAL_REACHED` at 106.893 s, and Oracle=`GOAL_REACHED` at 96.404 s. A clean rerun exposed nondeterministic emergency-escape behavior, so this single comparison was not accepted as final evidence.
- Failed/degraded: `temporary_blockage_high_validation_s02720` remains an Oracle-timeout environment case; it is retained for safety/failure analysis rather than used as a success gate. One crossing-flow startup without a Nav2 action was classified `INVALID_RESET` and retried once.
- Validation: `make test` passed 179 tests; the Humble overlay built all three ROS packages.
- Next: commit the mask/deployment stage, collect train-only DAgger-2 states, retrain iteration 2, and rerun held-out validation with a clean commit ID.

## 2026-07-31 — Gate 5 two-round DAgger accepted, model selection provisional

- Fixed and retained two validation counterexamples: one DAgger-1 rerun collided because the safety layer repeatedly backed beside a pedestrian; a one-backup rule removed the collision but brief hazard-clear pulses reset it and caused timeout. A three-second clear hysteresis now prevents the cross-state loop and passes 180 tests.
- With commit `6bf5063`, DAgger-1 reached the goal in 2/2 repeated validation runs (both 90.909 s); minimum human distance was 1.104 m and 1.033 m, and median ONNX latency was 0.151 ms and 0.149 ms. Both runs selected only CONTINUE, so this is stability/non-degradation evidence, not active recovery evidence.
- DAgger iteration 2 collected three train-only policy trajectories with outcomes PLANNER_FAILURE, COLLISION, and GOAL_REACHED. It added 230 legal expert states, producing 14 episodes, 14,778 observations, and 1,383 recovery samples in total.
- DAgger-2 validation was mixed: one GOAL_REACHED at 111.389 s and one COLLISION at 74.692 s. It was slower and less safe than DAgger-1 on this pilot and remains a negative ablation.
- Selected candidate: DAgger-1. Gate 5 is accepted because both aggregation rounds and validation analysis are complete; method-performance claims remain provisional until paired multi-scenario pilots show learned non-CONTINUE recovery actions.
- Evidence: `outputs/pilot/crossing_flow_high_validation_learning_pilot.csv`, `data/manifests/dagger_iter1_manifest.json`, and `data/manifests/dagger_iter2_manifest.json`.
- Next: run current Base/Heuristic/DAgger-1/Oracle on additional locked validation scenarios, then decide whether optional PPO is justified or the imitation-only manuscript is the honest endpoint.

## 2026-07-31 — Active-recovery repeat-5 pilot

- Added a train-only head-on coverage shard (234 states; 103 REPLAN, 105 WAIT) and selected epochs on a two-scenario validation set without adding validation frames to training.
- Added bounded no-progress WAIT/REPLAN masks, collision-latched rejoin blocking, a collision-risk clearance margin, swept emergency-translation checks, and a 0.9 m original-path corridor mask. The current suite passes 185 tests.
- `head_on_corridor` remains a retained failure: its Gazebo shelf walls are absent from `map_empty`, so recovery/rejoin can collide with unmodeled static geometry. `overtaking` is also not an acceptance scenario because the current Oracle collided.
- On recoverable `crossing_flow_high_validation_s02220`, five valid Base repeats produced 0 GOAL_REACHED / 5 COLLISION. Five coverage-policy repeats produced 3 GOAL_REACHED / 2 COLLISION and executed WAIT plus +60-degree temporary subgoals.
- Pilot estimates: Base success 0.0 (95% Clopper--Pearson [0.000, 0.522]); coverage success 0.6 ([0.147, 0.947]); unpaired Fisher p=0.167. Coverage median minimum human distance was 1.115 m and median successful navigation time was 110.889 s.
- Evidence: `outputs/pilot/crossing_flow_coverage_repeat5.csv` and `outputs/pilot/crossing_flow_coverage_repeat5_summary.json`. This is not final multi-seed statistical evidence.
- Next: regenerate all selected train labels under the latest path mask, retrain the candidate, then run a multi-seed validation pilot before deciding on PPO or the imitation-only paper scope.

## 2026-08-01 — Deploy-aligned safety candidate

- Regenerated 14 reviewed expert shards after applying the same collision-latched rejoin, path-corridor, LiDAR endpoint, and swept-clearance masks offline and online. All 1,786 selected labels are legal.
- Fixed a live collision-warning blind spot: stale DDS odometry delivered during Nav2 preemption used to clear all detector history. Non-increasing stamps are now discarded; a fresh detector process remains the episode reset boundary.
- Increased only collision-latched candidate clearance to 0.65 m and the independent stopping margin to 0.85 m, matching the Gazebo fallback's combined 0.71 m robot-human collision boundary plus braking/callback latency. These are empirical filters, not formal safety guarantees.
- The selected `coverage_safety_aligned` checkpoint has scenario-disjoint validation top-1 0.910, top-3 0.985, near-optimal rate 0.955, zero invalid selections, and zero catastrophic selections. CPU ONNX inference is approximately 0.035 ms in a local smoke loop.
- On five retained repeats of `crossing_flow_high_validation_s02220`, Base produced 0/5 `GOAL_REACHED` and 5/5 `COLLISION`; the safety-aligned policy produced 3/5 `GOAL_REACHED`, 0/5 `COLLISION`, and 2/5 `TIMEOUT`. Successful navigation time median was 110.423 s and minimum human-distance median was 1.080 m.
- Exact success intervals remain wide: Base 0.0 [0.000, 0.522], learned 0.6 [0.147, 0.947], unpaired Fisher p=0.167. This is repeated same-seed pilot evidence, not final multi-seed significance.
- One timeout stopped beside a 0.22 m lateral LiDAR return that matched neither the empty static scenario nor any privileged pedestrian position; it is retained as an algorithm timeout and a Gazebo proxy/self-return failure case, not excluded.
- Evidence: `outputs/pilot/crossing_flow_safety_aligned_repeat5.csv`, `outputs/pilot/crossing_flow_safety_aligned_repeat5_summary.json`, and `data/manifests/dagger_coverage_safety_aligned_manifest.json`.
- Next: run scenario/seed-expanded validation with a locked 180 s manifest, preserve the imitation-only method as the minimum paper path, and attempt PPO only after the multi-seed candidate remains collision-safe.

## 2026-08-01 — Compilable imitation-only pilot manuscript

- Created a three-page anonymous IEEEtran pilot manuscript with a verified related-work matrix, method formulation, limitations, and claims restricted to committed artifacts.
- Generated the system architecture as a white-background, three-color Graphviz vector figure and generated the pilot outcome figure/table from the committed result JSON.
- Installed user-space Tectonic 0.17 in `ramp-offline`; `make figures`, `make tables`, and `make paper` now complete without sudo or ROS activation.
- `paper/main.pdf` compiles with BibTeX, no unresolved citations/references, and no overfull boxes. Remaining underfull warnings are non-fatal line-breaking warnings.
- The title intentionally omits reinforcement learning because PPO has not been implemented or validated. The abstract explicitly labels the 5-repeat result as a non-conclusive pilot.
- Validation: `make test` passes 186 tests and `make paper` produces a nonempty PDF.
- Next: expand and lock the multi-scenario evaluation before replacing pilot wording with final claims.

## 2026-08-01 — Medium-density emergency-escape regression fixed

- Diagnosed a real learned-policy degradation on synchronized `crossing_flow_medium_validation_s02210`: Base reached the goal in 100.866 s, while the selected policy timed out after 180 s with 1262 emergency-stop samples and 1275 recovery-action samples.
- The terminal LiDAR cluster was not isolated noise. It occupied roughly 16 contiguous beams, remained behind the robot while it rotated, and coexisted with at least 1.86 m forward clearance. The ordinary swept-capsule check nevertheless rejected forward escape because the conservative start footprint was already overlapping.
- Added a strictly separating emergency-capsule mode. Only initial returns behind the requested translation are exempted; forward/lateral overlaps and all newly swept obstacles remain blocking. Two regression tests cover the allowed rear escape and forbidden front escape.
- Corrected online replay on the exact scenario reached the goal in 114.386 s, with 0.964 m minimum human-center distance, 0.300 m minimum LiDAR distance, and 219 recovery samples. The old timeout is retained and linked in `outputs/pilot/crossing_flow_medium_validation_escape_regression.csv`.
- Validation: `make test` passes 188 tests and the Humble overlay builds all three packages.
- Next: run independent low/medium/high validation seeds, then update the pilot statistics and manuscript only with all valid outcomes retained.

## 2026-08-01 — High-density stalled-rejoin regression fixed

- Retained a post-escape `PLANNER_FAILURE`: the policy reached `(17.01, 14.47)` with 0.97 m LiDAR clearance and a valid global path, but Nav2 repeatedly failed its progress checker for roughly 90 s.
- Diagnosed the temporal loop from raw rows and runtime logs. Each five-second rejoin timeout correctly requested a recovery retry, but the cleared detector vector led BC to select CONTINUE again, repeatedly submitting an unchanged task goal.
- Added a deployment-only temporal mask that blocks CONTINUE on a failed-rejoin retry only when a planning-valid locomotion alternative exists. WAIT remains available and a no-alternative mask retains CONTINUE.
- Fresh synchronized high-density replay reached the goal in 107.426 s with 1.136 m minimum human-center distance, 0.588 m minimum LiDAR distance, and 187 recovery samples. Base's retained synchronized outcome is collision at 29.104 s; the preceding failed learned replay remains in the comparison artifact.
- Validation: `make test` passes 190 tests and the Humble overlay builds all three packages.
- Evidence: `outputs/pilot/crossing_flow_high_validation_rejoin_regression.csv` with raw SHA256 values.
- Next: repeat the corrected high-density configuration and construct validation-only seed variants before any statistical claim.

## 2026-08-01 — Collision-safety release and multi-obstacle escape aligned

- A locked-code high-density repeat produced a retained timeout at the collision-latched 0.85 m boundary. LiDAR jitter repeatedly reset the emergency hold, so the escape option could not complete.
- Release hysteresis alone escaped the early interaction but exposed an unsafe rejoin: collision prediction cleared for one turning frame, generic 0.48 m clearance resumed, and the episode collided at 0.697 m human-center distance.
- Latching the stop margin removed that release path, but the emergency forward capsule still used 0.36 m and moved away from one obstacle while approaching another, colliding at 0.709 m.
- The selected safety composition keeps the 0.85 m stop and multi-obstacle translation capsule active until observed clearance exceeds 0.90 m. A translation from overlap remains legal only if it increases distance from every overlapping return.
- Fresh online replay reached the goal in 113.986 s with 1.161 m minimum human-center distance, 0.640 m minimum LiDAR distance, and 262 recovery samples.
- Validation: `make test` passes 193 tests and the Humble overlay builds all three packages.
- Evidence: all timeout/collision/success rows and raw hashes are retained in `outputs/pilot/crossing_flow_high_validation_safety_iteration.csv`.
- Next: freeze this code and collect repeated high-density outcomes before updating aggregate claims.

## 2026-08-01 — Scenario-aware collision classification validated online

- Retained two high-density runs that were labeled collision after consecutive 0.08--0.09 m LiDAR returns despite a stopped robot, no declared static obstacles, and more than 1.16 m privileged human-centre clearance.
- Added two-frame debounce and a scenario-derived switch: LiDAR static-contact termination is enabled only for scenarios with declared static obstacles. Evaluation-time human overlap remains independently active for every scenario.
- Increased the observable turning-sector collision guard to 0.85 m, latched collision safety immediately in the detector callback, and preserved a chosen emergency turn direction until a safe separating translation is available.
- A fresh synchronized high-density replay crossed the former false-contact point and reached the original goal in 141.891 s. It maintained 1.185 m minimum human-centre distance and 0.421 m minimum LiDAR distance while executing 494 non-CONTINUE recovery samples.
- Validation: `make test` passes 197 tests and the Humble overlay builds all three packages.
- Evidence: `outputs/pilot/crossing_flow_high_validation_static_collision_classifier_regression.csv` contains both unchanged outcomes and raw SHA256 values.
- One preceding launch lacked a Nav2 action server and produced no algorithm result; it is retained only as a startup diagnostic and excluded from metrics.
- Next: collect independent validation seeds under this classifier version before locking the final manifest.

## 2026-08-01 — Proxy synchronization and observable escape candidate

- A high-density temporary-blockage validation run exposed a 1441-sample emergency-spin timeout. An attempted task-aligned forward escape caused a real 0.706 m human overlap and was fully removed.
- Replaced that unsafe branch with progress-gated BACKUP: another bounded reverse pulse is legal only after at least 0.05 m measured clearance gain, with eight pulses maximum. The hard temporary-blockage phase remained a safe timeout after 30 reverse control samples, so the scenario stays a failure case.
- Fixed a ROS initialization typo caught only online and made runner crash scanning ignore tracebacks after the explicit cleanup marker while retaining real pre-cleanup crashes.
- Found that fallback privileged actor trajectories could outrun pending Gazebo pose updates. Route time now freezes on pending futures, and a two-second backlog marks actor health false.
- Added a scenario-derived near-field filter for the 0.16--0.33 m Jackal self-return cluster only when no static obstacles are declared. Static scenarios retain unfiltered LiDAR.
- Tightened emergency FORWARD entry and continuation to 0.85 m directional clearance while preserving the 0.85 m collision-latched swept capsule.
- Final development replay reached the original high-density crossing-flow goal in 176.923 s with 0.995 m minimum human-centre distance, 653 emergency samples, 51 reverse-control samples, and 291 emergency-forward samples.
- Validation: `make test` passes 202 tests and the Humble overlay builds all three packages.
- Evidence: `outputs/pilot/crossing_flow_high_validation_runtime_alignment_iteration.csv` and `outputs/pilot/temporary_blockage_high_validation_escape_safety_iteration.csv` retain every valid timeout/collision/success variant and raw hash.
- This remains validation-only development evidence; multi-scenario locked evaluation is still required before a paper performance claim.

## 2026-08-01 — Independent medium-density candidate pair

- Froze commit `100b09f` and reran both methods on `crossing_flow_medium_validation_s02210` after actor synchronization.
- Base collided at 29.204 s after 6.937 m progress and 0.707 m minimum human-centre distance.
- The selected DAgger recovery avoided collision for 179.920 s and made 9.210 m progress, but timed out after 1286 recovery samples; minimum human-centre distance was 0.774 m.
- This is a safety/stall tradeoff, not a recovery-success result. It confirms the candidate still over-intervenes outside the tuned high-density replay.
- Evidence: `outputs/pilot/crossing_flow_medium_validation_candidate_100b09f_pair.csv` with both raw SHA256 values.
- Next: run the low-density validation pair without parameter changes; reject the candidate from final evaluation if it also fails to complete.

## 2026-08-01 — Kinematic pedestrian proxy validity gate

- Rejected the previous dynamic validation evidence after a low-density run exposed a privileged pedestrian centre at 0.697 m while LiDAR still reported 1.473 m in the expected direction. The fallback proxy had been declared static, so accepted pose-service responses did not establish collision-geometry motion.
- Replaced each static proxy with a gravity-disabled kinematic link and added an evaluation-only privileged-to-observable LiDAR consistency checker. Privileged positions remain excluded from detector and policy inputs.
- In the corrected BC replay, all 89 samples with a human centre inside 1.3 m contained a LiDAR return in the expected angular footprint. The nearest centre distance was 1.149 m, the expected cylinder-surface distance was 0.799 m, and the measured sector range was approximately 0.789--0.803 m; maximum positive surface-range error was 0.019 m.
- A second audit found one remaining actor-step lead: requested privileged poses were published before the associated geometry update was confirmed. Route time and privileged truth now commit only after the Gazebo future succeeds; requests in flight freeze the public state.
- Under the final confirmed semantics, Base collided at low, medium, and high crossing-flow density after 29--30 s. The selected DAgger checkpoint reached the original goal in all three paired episodes in 108.924, 117.915, and 125.408 s. Minimum human-centre distances were 1.166, 1.151, and 0.936 m, respectively.
- Every selected episode passed the privileged-to-LiDAR gate; the six visible ratios are between 99.4% and 100%. One low-density BC launch lacking the NavigateToPose action server is retained as an invalid startup and excluded from algorithm metrics.
- Validation: 205 offline tests, Ruff, Mypy, and the three-package Humble overlay pass. Evidence is retained in `data/manifests/*confirmed_proxy*lidar_consistency.json` and `outputs/pilot/crossing_flow_density_confirmed_proxy_pairs.csv`, with raw SHA256 values.
- This is a three-pair precheck, not a significance result. All pre-confirmed dynamic tables are diagnostic-only. Next: freeze this implementation and expand independent validation seeds without tuning.

## 2026-08-01 — Full Gazebo actual-pose evaluation path

- Direct Gazebo transport inspection showed that link-level `kinematic=true` could leave proxy collision bodies near their initial poses despite accepted model-pose requests. A 5 Hz workaround only barely passed the sensor gate and 10 Hz caused backlog, so frequency was not used to hide the error.
- Proxies are now movable `static=false`, `gravity=false`, `kinematic=false` models. A pinned `ros_gz_bridge` maps `/world/default/dynamic_pose/info` into ROS. The actor controller publishes actual Gazebo pedestrian and Jackal poses on privileged topics; missing or stale feedback marks the episode as simulator failure.
- Observable policy inputs remain odometry and LiDAR. Actual model poses are used only for outcome classification, simulator-validity checking, and future privileged expert labels.
- On `crossing_flow_medium_validation_s02201`, Base collided at 29.004 s and 0.710 m actual centre distance. The selected DAgger policy reached the original goal at 173.893 s with 0.733 m minimum actual distance and 832 recovery samples.
- The learned run passed 774/781 near-human sensor checks (99.1%); Base passed 21/21. This is the first admissible positive pair, but its safety and timeout margins are narrow and no statistical claim is authorized.
- Validation: 207 tests, Ruff, Mypy, and the Humble overlay pass. Next: commit the actual-pose platform fix, regenerate corrected training data, and rebuild a multi-seed pilot from this version only.

## 2026-08-01 — Verified-pose recovery pair and manuscript refresh

- Invalidated the preceding “first admissible” pair after two independent checks: a 70 kg teleported pedestrian collision body perturbed Jackal motion, and wheel-integrated skid-steer odometry declared arrival while the physical model remained 1.06 m from the goal.
- Fallback pedestrians are now contactless GPU-LiDAR visuals; robot--human overlap is still classified from actual Gazebo centre distance. The protected runner requires no-auto-reset and command mux, uses bounded teardown, and rejects physical pose jumps.
- The known-pose Gazebo profile now uses Gazebo's pose-derived OdometryPublisher for the standard odometry/TF interface. Goal success requires both localized distance at most 0.25 m and physical Gazebo distance at most 0.30 m.
- At commit `2164e08`, the synchronized medium crossing-flow validation pair produced Base COLLISION at 29.4705 s and DAgger GOAL_REACHED at 98.4348 s. Physical goal error was 0.299 m; minimum human distances were 0.665 m and 1.203 m.
- LiDAR validity passed 26/26 near-human Base frames and 30/30 learned frames. Maximum localization--physical error in the learned run was 0.128 m. The learned controller executed 117 non-CONTINUE samples including temporary subgoals, WAIT, and BACKUP.
- Evidence: `outputs/pilot/crossing_flow_medium_s02201_2164e08_pair.csv`, the two `data/manifests/*2164e08*lidar_consistency.json` files, generated LaTeX table/figure, and raw hashes in the CSV.
- Validation: 210 tests, Ruff, Mypy, three ROS packages, `make figures`, `make tables`, and `make paper` pass. `paper/main.pdf` is current.
- This is a verified single-seed execution result, not statistical evidence. Next: rerun independent validation variants under the frozen platform, then regenerate training data if the existing checkpoint does not generalize.

## 2026-08-01 — Independent nominal-case non-degradation pair

- On validation seed 2202, both methods physically reached the goal under commit `a856923`: Base in 93.606 s and triggered DAgger in 92.907 s.
- Physical goal errors were 0.119 m and 0.289 m; minimum human distances were 1.335 m and 1.330 m. DAgger used 29 temporary-subgoal samples and no WAIT/BACKUP, avoiding the long-intervention failure seen in earlier development runs.
- Neither run placed a human centre inside the sensor checker's 1.3 m audit radius, so their per-episode proxy reports correctly state insufficient evidence. The selected platform's close-range validity remains established by the seed-2201 26/26 and 30/30 checks.
- The first BC attempt on this seed remains an unchanged `SIMULATOR_FAILURE` because the old logger compared asynchronous localized/physical frames immediately. The fixed one-second confirmation window produced the fresh valid pair; no outcome was rewritten.
- Evidence: `outputs/pilot/crossing_flow_medium_s02202_a856923_pair.csv` with raw SHA256 values. This is a nominal non-degradation check, not a recovery improvement claim.
