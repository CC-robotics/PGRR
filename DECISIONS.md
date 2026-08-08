# Final release decisions

This file records the decisions that define the single supported PGRR release.
Detailed intermediate deliberations remain in Git history and immutable run
manifests; they are not separate maintained product versions.

## D-F01: PGRR is a failure-triggered layer, not a replacement planner

Nav2 DWB controls normal navigation. PGRR activates only for observable
collision risk, freeze, oscillation, deadlock, or planner failure. It selects
one of 21 robot-relative temporary subgoals plus `WAIT`, `BACKUP`, `REPLAN`, or
`CONTINUE`. The classical planner executes temporary goals, and the original
task goal must be restored during rejoin. PPO, continuous learned velocity
control, a learned detector, and a second planner are outside the release
claim.

## D-F02: Keep privileged information in training only

The rollout expert may inspect simulator robot and pedestrian state while
labeling legal actions. Deployed PGRR receives only observable LiDAR, path,
goal, velocity, planner-command, progress, status, and rule-score history.
Privileged fields are written separately and cannot enter test observations.
The selected learner is Uniform BC followed by validation-selected DAgger; the
second DAgger candidate was rejected on validation.

## D-F03: Use one bounded, fail-closed recovery state machine

The action mask removes unsafe, occupied, disconnected, occluded, or
unavailable actions and always retains a safe fallback. The system stores the
original goal, runs bounded recovery, requires stable clearance and at least
0.25 m original-goal progress before resetting the recurrence budget, completes
a post-retreat turn before release, and rejoins Nav2. Emergency stopping remains
independent of policy output. These are empirical safety mechanisms, not a
formal collision-free guarantee.

## D-F04: Separate ROS runtime and offline analysis environments

Online execution uses the pinned Ubuntu 22.04 / ROS2 Humble / Arena Gazebo
profile with Jackal, Nav2 DWB, planar LiDAR, Xvfb, and software rendering.
Offline data, learning, statistics, figures, and tests use the Python 3.10
`ramp-offline` Conda environment. Runtime helpers remove Conda and foreign ROS
variables; offline helpers never source ROS. The deterministic cylindrical
pedestrian proxies are simulator actors, not a validated human-intent model.

## D-F05: Freeze one benchmark identity and preserve its hashes

The public product has one release. Its internal benchmark ID is
`moderate_social_navigation_v6`, retained because it is embedded in scenario
IDs, split hashes, results, and the 96-file artifact manifest. Renaming that ID
after evaluation would break provenance; the suffix is therefore an immutable
dataset identifier rather than a user-facing version choice.

The final benchmark contains eight interaction families, three densities, and
five held-out repeats: 120 shared conditions per method and 600 logical
method--episodes over Base, Standard, Heuristic, Uniform BC, and PGRR. Train,
validation, and test use disjoint scenario IDs and seed blocks. The accepted
calibration report is fixed by SHA-256 in the final configuration.

## D-F06: Reject a calibration before test rather than relax its threshold

One earlier validation candidate let Base reach 57/72 goals (79.17%), above
the preregistered 75% ceiling. Its test was never opened. The final benchmark
retained its geometry, changed only the Crossing Flow timing band from
validation evidence, used fresh seeds, and passed the unchanged calibration.
This history remains in the paper because it demonstrates that the test was
not used for benchmark tuning; it is not presented as another current release.

## D-F07: Keep algorithm outcomes and infrastructure attempts distinct

`GOAL_REACHED`, `COLLISION`, `TIMEOUT`, and `PLANNER_FAILURE` are final
algorithm outcomes and are never retried. Only classified
`SIMULATOR_FAILURE` or `INVALID_RESET` attempts may be retried, at most twice,
and every physical attempt remains in provenance. A logical result is accepted
only when the final run manifest is complete and the collector can bind the
terminal artifact to its task and scenario hashes.

The final record contains 600 algorithm outcomes, eight excluded simulator
failures, six excluded invalid resets, and 42 no-outcome command records over
39 unique tasks. Resumes recovered only incomplete tasks.

## D-F08: Use paired tests and one global multiple-comparison correction

All methods share the same 120 condition keys. Goal, collision, and timeout
comparisons use exact paired tests; every preregistered hypothesis across
methods and endpoints enters one Holm family. `PLANNER_FAILURE` is reported as
a separate descriptive terminal class because it was not a preregistered
binary inferential endpoint. Duration and path length use only joint-success
pairs and must state that conditioning explicitly.

## D-F09: Bound the scientific claim to the observed trade-offs

PGRR versus Base improves goal reaching by 20.00 percentage points and reduces
collision by 29.17 points, both significant after global Holm correction. It
also takes 15.88 s longer and travels 1.89 m farther on 83 joint successes,
with higher angular jerk. The preregistered goal/collision/timeout comparisons
against Heuristic and Uniform BC do not establish general superiority after
correction; planner failure remains descriptive. The release claims a Base-DWB
safety and completion improvement with efficiency/smoothness costs, not better
comfort, formal safety, universal superiority, unseen-map generalization, or
hardware readiness.

## D-F10: Bind publication claims to checked-in evidence

Every paper number is generated from the final Parquet/JSON/CSV bundle. The
anonymous paper must be exactly 8 pages, the Chinese report exactly 32 pages,
and the presentation exactly 30 slides/pages. The release manifest binds 96
artifacts, document page counts, the evaluation commit, the generation commit,
and media hashes. Release mode runs only from a clean worktree and validates
without regenerating files.

The real Gazebo GUI image is labeled as a historical moderate-v5 validation
environment capture (benchmark provenance, not another current release); it is
not called a camera frame from the held-out statistical run. The same-condition
Base--PGRR trajectory and recovery timeline are real telemetry reconstructions
and are not called screenshots.

## D-F11: Preserve one historical boundary without pooling it

The earlier frozen 64/64 audit remains visible because it prevents selective
reporting: PGRR/Base collisions were 0/24 versus 19/24, timeouts were 16/24
versus 0/24, and goal reaches were 8/24 versus 5/24; the adjusted goal-reaching
comparison was not significant. Those rows are not pooled with, copied into,
or used to tune the final benchmark.

## D-F12: Publish the same release state on `main` and `home`

`main` is the canonical integration branch and `home` is the synchronized
working mirror requested for this project. A release is complete only when the
same final project commit is reachable from both remote branches and a clean
checkout passes the release validator.
