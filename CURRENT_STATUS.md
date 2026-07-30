# Current status

## Gate 1 revalidation / Gate 2 — observable recovery MVP (in progress)

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
- Implemented the ROS-independent privileged planning expert, cost decomposition, constant-velocity human rollout, fixed-mask/margin label, and a 20-scene PDF validator. The complete quality suite passes 116 tests.

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
- Expert synthetic validation: PASS for implementation smoke only. Twenty scenes, zero illegal selected actions, zero selected-rollout collisions, and 16 predicted-success labels. This is not an Arena Oracle comparison and does not yet pass Gate 3.

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

### Next

Connect recorded privileged Arena states to the planning expert and validate Oracle recovery on the corrected known-pose profile. Keep Gate 2 marked failed and do not begin neural-policy training until paired baselines and expert rollouts are validated.
