# PGRR agent contract

## Objective

Build and validate a failure-triggered dynamic social-navigation recovery system. A classical planner remains in control during normal navigation. Recovery is activated only for collision risk, freeze, oscillation, deadlock, or planner failure, and chooses one of 21 temporary subgoals plus WAIT, BACKUP, REPLAN, and CONTINUE. Temporary goals are executed by the classical planner and the original goal must be restored.

The release and paper name is **PGRR: Planning-Guided Failure-Triggered
Recovery and Rejoin for Dynamic Social Navigation**. Historical Python/ROS
packages, environment names, and runtime variables retain `ramp_*`/`RAMP_*` as
compatibility interfaces; they are not the public method name. PPO is not a
claimed contribution in this release.

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
- Keep `main` as the canonical integration branch and `home` as the synchronized
  working mirror. Do not hollow out the runnable baseline or rewrite published
  evidence history.

## Environment boundary

- ROS2/Arena runtime: Ubuntu 22.04, ROS2 Humble, Python 3.10, Arena/RosNav uv or venv. Conda must be deactivated before installing or running Arena.
- Offline work: Conda environment `ramp-offline` with Python 3.10 for data, imitation learning, statistics, figures, and tests. Never source ROS from its activation helper.
- Environments exchange HDF5, Parquet, JSON, YAML, TorchScript/ONNX, or SB3 checkpoints.

## Current milestone and acceptance

The final imitation-learning release is complete on the pinned
`arena_humble_docker` Gazebo profile. Run `95ec74c511bb` has 600/600 logical
episodes: Base, Standard, Heuristic, Uniform BC, and PGRR each cover the same
120 held-out conditions (eight families, three densities, five repeats).
PGRR/Base goal reaching is 109/120 versus 85/120 and collision is 0/120 versus
35/120; both paired differences are significant after the preregistered global
Holm correction. On 83 joint successes, PGRR is 15.88 s slower and 1.89 m
longer, and angular jerk is higher. The preregistered goal/collision/timeout
comparisons against Heuristic and Uniform BC do not establish general
superiority after global correction; planner failure remains descriptive.
Preserve this safety/completion gain and efficiency/smoothness cost in every
final summary.

One earlier frozen 64/64 audit remains a required historical boundary: PGRR
and Base collisions were 0/24 versus 19/24, timeouts were 16/24 versus 0/24,
and goal reaches were 8/24 versus 5/24; the adjusted goal-reaching comparison
was not significant. Never pool those rows with the final result or present
them as another current release.

The selected model is the validation-chosen Triggered-DAgger checkpoint exposed
at `checkpoints/final/best.onnx`. The two-round DAgger workflow completed, but
the second candidate was rejected on validation. Margin weighting did not
improve the frozen offline ablation. PPO, the learned detector, a second
planner, Flatland, hardware, and formal safety are not completed claims.

Final evidence lives under `outputs/moderate/final`, generated figures/tables
under `outputs/{figures,tables}`, and the compiled anonymous paper at
`paper/main.pdf`. The internal `moderate_v6` string is a frozen benchmark ID,
not a product version. Do not tune using the locked test, replace failed
episodes, or describe telemetry reconstructions as simulator camera
screenshots.
