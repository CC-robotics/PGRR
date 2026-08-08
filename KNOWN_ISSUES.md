# Known issues and release limitations

There are no open blockers for the frozen PGRR release. This file lists the
limitations that remain scientifically or operationally relevant. Resolved
development incidents are preserved in Git history and run manifests rather
than presented as current project variants.

## KI-F01: The gain over Base carries efficiency and smoothness costs

PGRR improves goal reaching by 20.00 percentage points and reduces collision by
29.17 points relative to Base DWB; both paired comparisons remain significant
after global Holm correction. It still records two timeouts and nine planner
failures. On the 83 joint-success pairs, it takes 15.88 s longer and travels
1.89 m farther, with higher angular jerk. Its observed personal-space violation
ratio is 4.13 points higher, although that comparison is not significant after
global correction.

Observed differences against Heuristic and Uniform BC on the three
preregistered terminal endpoints (goal, collision, and timeout) are not
significant after global correction; planner failure remains descriptive. The
result does not support universal superiority, better comfort, or a formal
safety claim.

## KI-F02: Planner failure remains a completion bottleneck

PGRR terminates with nine `PLANNER_FAILURE` outcomes versus none for Base.
Planner failure was not a preregistered binary inferential endpoint, so the
7.50-point marginal difference is descriptive and receives no post-hoc
significance test. Future work should reduce planner aborts without tuning on
the existing held-out test.

## KI-F03: The fallback map omits some physical shelf geometry

The Arena `map_empty` occupancy map does not include every shelf used to create
the physical interaction corridor. The observable safety layer and
scenario-aware checks compensate empirically, but Nav2 can still propose a
route through geometry that Gazebo treats as occupied. This contributes to
blind-corner and rejoin difficulty and prevents a formal map-consistency claim.

## KI-F04: Dynamic agents are deterministic proxies, not validated humans

The pinned Arena Humble fallback uses seeded LiDAR-visible cylindrical
pedestrian proxies with deterministic routes. They provide reproducible dynamic
interactions but do not model human intent or establish social acceptability.
The release has no human-subject, hardware, cross-simulator, unseen-map,
second-planner, or formal-safety validation.

## KI-F05: Gazebo startup required auditable retries

Six-worker execution completed every logical task, but the retained provenance
contains eight `SIMULATOR_FAILURE` and six `INVALID_RESET` physical attempts.
Attempt snapshots also contain 42 launch commands without outcome files over 39
unique tasks. Only incomplete infrastructure tasks were resumed; algorithm
outcomes were never replaced. This is a runtime robustness limitation, not an
algorithm failure count.

## KI-F06: Direct offline pytest can inherit an incompatible ROS plugin

Some host shells export ROS paths that expose an older `launch_testing` pytest
hook to the newer offline pytest/pluggy stack, causing collection to fail before
project tests run. Use `make test`, the offline activation helper, or the
sanitized environment command in `COMMANDS.md`. This does not affect the 703
project tests that passed in the clean release environment.

## KI-F07: The real screenshot and matched telemetry prove different things

`outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png` is a real Arena
Gazebo GUI capture with pixel and runtime provenance. It is a historical
moderate-v5 validation environment capture (benchmark provenance, not another
current release) demonstrating Jackal, Nav2 DWB, LiDAR, and dynamic actors; it
is not a camera frame from the held-out statistical episode set.

The Base--PGRR trajectory and recovery timeline in
`outputs/moderate/final/media/` come from a real identical-condition held-out
pair and bind to raw/result hashes, but they are telemetry reconstructions, not
camera screenshots. Neither evidence type may be relabeled as the other.

## KI-F08: One similarly named calibration file is not authoritative

The accepted calibration report is
`outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json`, SHA-256
`0fbf8a159a1e1b96e940bec0efb31e5952ba5b0333439992f370a9a9fb41e15f`.
An untracked `outputs/moderate/final/calibration_report.json` can be produced by
applying validation calibration logic to a test table; it is empty and
rejected. It is excluded from the release manifest and must not be cited.

## KI-F09: Internal dataset suffixes cannot be renamed post hoc

Paths and records containing `moderate_v6` are bound into scenario IDs, split
hashes, row-level provenance, the final configuration, and the artifact
manifest. Changing them would invalidate the published evidence. The suffix is
an internal benchmark identity; the supported project presented to users is
the single PGRR final release.

## KI-F10: Test-set tuning remains forbidden

The final 120-condition test has been opened and is permanently frozen.
Algorithm, checkpoint, threshold, scenario, or metric changes motivated by its
outcomes require a newly named, newly seeded future study. Failed episodes may
not be filtered or replaced, and validation rows may not populate final tables.

## Historical boundary

An earlier frozen 64/64 audit is retained to prevent selective reporting:
PGRR/Base collisions were 0/24 versus 19/24, timeouts were 16/24 versus 0/24,
and goal reaches were 8/24 versus 5/24; adjusted goal-reaching was not
significant. It is never pooled with the final 600-episode result.
