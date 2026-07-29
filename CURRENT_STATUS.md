# Current status

## Gate 2 — rule-triggered recovery MVP (in progress)

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
  --manifest outputs/pilot/baseline_failure_mining.csv \
  --output data/interim/gate1_failure_labels.h5 \
  --summary data/manifests/failure_label_summary.json
scripts/arena/smoke_failure_detector.sh
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
- Gate 1 full acceptance: PASS. Failure rates are 100% for head-on corridor (7 collision, 3 timeout), 100% for doorway bottleneck (10 collision), and 80% for crossing flow (8 collision, 2 goal reached).
- Failure-mining infrastructure: PASS; 30 scenarios parse in the installed Arena version, checkpoint CSV writes atomically, and completed outcomes resume without overwrite.
- Head-on mining seed 0: PASS as a reproducible algorithm failure (`COLLISION`), not a simulator failure.
- Simulator/reset exclusions: 6 `INVALID_RESET` attempts are reported separately and excluded; all corresponding fixed seeds later produced valid episodes.
- Failure evidence: `outputs/figures/baseline_failure_trajectories.pdf` and `outputs/videos/baseline_failure_*_seed00.mp4` pass PDF/FFmpeg validation.
- Rule/label tests: PASS; normal motion, goal-reached stationary state, turn noise, short stops, exact freeze/oscillation/deadlock windows, and imminent collision are covered.
- Gate 1 label artifact: PASS; 30 episodes, 16,140 samples, no NaN/Inf, with 2,830 collision-risk, 2,143 freeze, 0 oscillation, and 1,221 deadlock positives. The zero oscillillation count is retained rather than synthesized.
- ROS detector smoke: PASS; a 1.0 m/s observation with 0.20 m clearance publishes collision risk 1.0 and a triggered status.

### Failures

- The invoking shell had Conda base active and ROS Iron selected. Runtime scripts must clear this and source Humble explicitly.
- Native Arena installation needs sudo and the official installer contains a broad `$HOME/.pyenv` removal, so it was contained with Docker `runc`.
- The official Humble profile provides Gazebo rather than Flatland. The main simulator for this profile is therefore Gazebo; this is a recorded platform fallback, not a claimed Flatland result.
- The smoke goal was accepted but later aborted; static point-goal success is deliberately left for Gate 1 rather than misreported here.
- The pinned Arena source references a Gazebo HuNav plugin absent from its installer and depending on an unpublished `arena_people_msgs` package. Dynamic runs use the documented Gazebo kinematic proxy fallback and are not labeled as HuNav social-force runs.
- Legacy Nav2 lifecycle activation is intermittently unreliable; every invalid reset is archived, assigned a fresh ROS domain for bounded retry, and excluded rather than counted as an algorithm failure.

### Next

Implement the masked heuristic selector and integrate it with the Nav2 temporary-goal/rejoin state machine, then run the three-method fixed-seed Gate 2 pilot before any network training.
