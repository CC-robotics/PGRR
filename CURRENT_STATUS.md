# Current status

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
