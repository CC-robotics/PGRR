# RAMP agent contract

## Objective

Build and validate a failure-triggered dynamic social-navigation recovery system. A classical planner remains in control during normal navigation. Recovery is activated only for collision risk, freeze, oscillation, deadlock, or planner failure, and chooses one of 21 temporary subgoals plus WAIT, BACKUP, REPLAN, and CONTINUE. Temporary goals are executed by the classical planner and the original goal must be restored.

The working paper title is **Planning-Guided Failure-Triggered Recovery via Imitation and Reinforcement Learning for Dynamic Social Navigation**. `RAMP` is only the repository name and must not be presented as a novel paper acronym.

## Non-negotiable execution rules

- Work gate-by-gate: environment, classical baseline, heuristic MVP, privileged expert, BC, two DAgger rounds, optional PPO, final evaluation, paper.
- Implement and run code; do not substitute plans or fabricated artifacts for execution.
- Never fabricate results, citations, simulator status, training completion, or statistical significance.
- Every paper number must be generated from checked-in CSV, Parquet, or JSON artifacts.
- Split train/validation/test by scenario and map, never by frame; never tune on test.
- Preserve every episode outcome: GOAL_REACHED, COLLISION, TIMEOUT, PLANNER_FAILURE, SIMULATOR_FAILURE, or INVALID_RESET.
- Every random process accepts an explicit seed. Paths, ROS names, frames, and endpoints are configurable.
- ROS nodes support `use_sim_time`. Privileged simulator fields must never enter test observations.
- Keep core logic in Python. Do not add complex C++ Nav2 plugins.
- Do not damage existing ROS installations or delete unknown user data.
- Maintain `CURRENT_STATUS.md`, `PROGRESS.md`, `DECISIONS.md`, `COMMANDS.md`, and `KNOWN_ISSUES.md` after each gate.
- Commit each completed stage on `teacher/reference`; later produce `student/reproduce` without hollowing out the runnable baseline.

## Environment boundary

- ROS2/Arena runtime: Ubuntu 22.04, ROS2 Humble, Python 3.10, Arena/RosNav uv or venv. Conda must be deactivated before installing or running Arena.
- Offline work: Conda environment `ramp-offline` with Python 3.10 for data, imitation learning, statistics, figures, and tests. Never source ROS from its activation helper.
- Environments exchange HDF5, Parquet, JSON, YAML, TorchScript/ONNX, or SB3 checkpoints.

## Current milestone and acceptance

Gate 0 is accepted with the pinned `arena_humble_docker` Gazebo profile. The original 30-episode Gate 1 table is superseded because visual actors were invisible to LiDAR; corrected runs use uniquely named LiDAR/collision proxies with deterministic robot-occupancy yielding. Current work is **Gate 1 paired revalidation and Gate 2 rule-based heuristic recovery**. Do not begin network training before corrected baseline evidence and multi-seed heuristic acceptance are complete.

If PPO, the learned detector, a second planner, or Gazebo cannot be completed honestly, follow the documented imitation-learning minimum path; do not block the core system or claim those modules succeeded.
