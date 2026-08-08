# Progress

## Final project state

All planned release gates are complete:

1. The Ubuntu 22.04 / ROS2 Humble / Arena Gazebo runtime is pinned and isolated
   from the Python 3.10 `ramp-offline` environment.
2. Base DWB, Standard Nav2 recovery, deterministic Heuristic recovery, Uniform
   BC, and PGRR share one configurable runner, scenario set, terminal-outcome
   schema, and retry policy.
3. The observable trigger covers collision risk, freeze, oscillation,
   deadlock, and planner failure. The recovery state machine preserves the
   original goal and rejoins the classical planner after progress resumes.
4. The privileged rollout expert, behavior cloning, and two DAgger rounds are
   complete. The validation-selected checkpoint is
   `checkpoints/final/best.onnx`; PPO and a learned detector are not release
   claims.
5. The final benchmark calibration was accepted using validation only. The
   held-out test remained sealed until configuration, scenario, checkpoint,
   runtime, concurrency, and hashes were frozen.
6. Run `95ec74c511bb` completed all 600 logical episodes at evaluation commit
   `6916e7cd586acfbe200045e49b093039e2a6980e`.
7. Collection, paired statistics, global Holm correction, failure analysis,
   figures, tables, real-environment evidence, and matched-run telemetry were
   generated from checked-in artifacts.
8. The 8-page paper, 32-page technical report, 30-slide presentation, and
   96-file release manifest passed clean-checkout validation and privacy QA.

## Final result

| Method | Goal | Collision | Timeout | Planner failure |
|---|---:|---:|---:|---:|
| Base DWB | 85 | 35 | 0 | 0 |
| Standard | 81 | 39 | 0 | 0 |
| Heuristic | 100 | 1 | 6 | 13 |
| Uniform BC | 104 | 1 | 5 | 10 |
| PGRR | 109 | 0 | 2 | 9 |

Relative to Base, PGRR has +20.00 percentage points goal reaching and -29.17
points collision; both comparisons remain significant after the preregistered
global Holm correction. It also has efficiency and smoothness costs: on 83
joint successes it is 15.88 s slower and 1.89 m longer, and angular jerk is
higher. The preregistered goal/collision/timeout comparisons with Heuristic and
Uniform BC do not establish general superiority after global correction;
planner failure remains descriptive.

The execution audit is complete: 600 algorithm outcomes, eight excluded
`SIMULATOR_FAILURE` attempts, six excluded `INVALID_RESET` attempts, and 42
no-outcome launch commands across 39 unique tasks are all preserved. Resumes
filled only incomplete tasks and never replaced an algorithm outcome.

## Release outputs

- `outputs/moderate/final/`: final results, statistics, failure analysis,
  matched evidence, media, and manifest.
- `paper/main.pdf`: 8-page anonymous manuscript.
- `report/PGRR_technical_report_zh.pdf`: 32-page technical report.
- `presentation/PGRR_report_zh.pptx` and PDF: 30-slide briefing.
- `README.md` and `REPRODUCIBILITY.md`: canonical project and reproduction
  entry points.

Internal strings such as `moderate_v6` are frozen dataset/provenance IDs, not
additional product versions. Earlier milestones remain recoverable from Git
history instead of being listed as competing current states.

## Historical boundary

The earlier 64/64 audit is retained in every summary because it prevents an
overstated claim: PGRR/Base collisions were 0/24 versus 19/24, timeouts 16/24
versus 0/24, and goal reaches 8/24 versus 5/24; adjusted goal-reaching was not
significant. It is not pooled with the final result.
