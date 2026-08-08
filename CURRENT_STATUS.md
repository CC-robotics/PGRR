# Current status

## Final release — complete

This repository now exposes one project state: **PGRR: Planning-Guided
Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation**. The
implementation, frozen evaluation, statistics, paper, technical report, and
presentation are complete. Names such as `moderate_social_navigation_v6` that
remain inside manifests and paths are immutable experiment identifiers, not
parallel product versions.

The authoritative held-out run is `95ec74c511bb`, recorded at evaluation
commit `6916e7cd586acfbe200045e49b093039e2a6980e`. It contains 600/600 logical
method--episodes: five methods evaluated on the same 120 conditions (eight
interaction families, three densities, and five repeats). The horizon is 240 s,
the frozen runner concurrency is six, and the final manifest reports no worker
errors.

| Method | Goal reached | Collision | Timeout | Planner failure |
|---|---:|---:|---:|---:|
| Base DWB | 85 | 35 | 0 | 0 |
| Standard Nav2 recovery | 81 | 39 | 0 | 0 |
| Heuristic recovery | 100 | 1 | 6 | 13 |
| Uniform BC | 104 | 1 | 5 | 10 |
| PGRR | 109 | 0 | 2 | 9 |

Against Base on 120 paired conditions, PGRR improves goal reaching by 20.00
percentage points (109/120 versus 85/120; global Holm-adjusted McNemar
`p=1.031e-4`) and reduces collision by 29.17 points (0/120 versus 35/120;
global Holm `p=2.561e-9`). The timeout difference is +1.67 points with global
Holm `p=1`. Planner failure is +7.50 points and is descriptive because it was
not a preregistered binary endpoint.

The result is not cost-free. On the 83 pairs where both Base and PGRR reach the
goal, PGRR takes 15.88 s longer (95% paired-bootstrap CI 11.43--20.83 s;
global Holm `p=3.318e-9`) and travels 1.89 m farther (CI 1.20--2.69 m; global
Holm `p=7.420e-7`). Mean absolute angular jerk is 0.185 rad/s^3 higher (global
Holm `p=4.585e-10`), while the observed +4.13-point personal-space violation
ratio is not significant after global correction (`p=1`). Comparisons against
Heuristic and Uniform BC on the three preregistered terminal endpoints (goal,
collision, and timeout) are also not significant after global correction;
planner failure remains descriptive. The supported claim is therefore a
safety and completion gain over Base DWB with measurable efficiency and
smoothness costs, not unqualified superiority over all recovery systems.

## Completeness and provenance

- All 600 algorithm outcomes are retained. Algorithm failures were never
  retried because they were unfavorable.
- The manifest retains 614 outcome-bearing physical attempts: 600 algorithm
  episodes plus eight `SIMULATOR_FAILURE` and six `INVALID_RESET` attempts
  excluded under the frozen infrastructure-failure rule.
- Attempt snapshots retain 42 commands without outcome files across 39 unique
  tasks. Resuming only incomplete tasks recovered all of them; none was
  converted into an algorithm outcome.
- The accepted calibration evidence is
  `outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json`, SHA-256
  `0fbf8a159a1e1b96e940bec0efb31e5952ba5b0333439992f370a9a9fb41e15f`.
  The similarly named file under `outputs/moderate/final/` is an untracked,
  rejected empty-test byproduct and is not release evidence.
- `outputs/moderate/final/artifact_manifest.json` binds 96 release files to
  their hashes and records the evaluation commit independently from the
  document-generation commit.

## Delivered artifacts

- Anonymous paper: `paper/main.pdf` — exactly 8 pages.
- Chinese technical report: `report/PGRR_technical_report_zh.pdf` — exactly
  32 pages.
- Presentation: `presentation/PGRR_report_zh.pptx` and PDF — exactly 30
  slides/pages.
- Final result bundle: `outputs/moderate/final/`.
- Real Gazebo GUI evidence:
  `outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png`, explicitly
  labeled as a historical moderate-v5 validation environment capture
  (benchmark provenance, not another current release) rather than a camera
  frame from the held-out statistical run.
- Real same-condition Base--PGRR telemetry comparison:
  `outputs/moderate/final/media/moderate_matched_base_pgrr_trajectory.pdf` and
  `outputs/moderate/final/media/moderate_pgrr_recovery_timeline.pdf`, explicitly
  labeled as telemetry reconstructions rather than screenshots.

Development QA passed Ruff, formatting, mypy, 703 tests, exact document page
counts, PDF text/font checks, and document validators. The clean-checkout
release gate separately passed the privacy audit and byte-level verification of
all 96 manifest artifacts without modifying the checkout.

## Historical boundary retained for scientific honesty

An earlier frozen 64/64 audit remains a boundary on interpretation: across 24
Base--PGRR pairs, PGRR/Base collisions were 0/24 versus 19/24, timeouts were
16/24 versus 0/24, and goal reaches were 8/24 versus 5/24; the adjusted
goal-reaching comparison was not significant. Those rows are never pooled
with the final 600-episode result. The Git history and immutable manifests
retain the full development audit without presenting those milestones as
separate current releases.

## Remaining work

No implementation, simulation, statistics, or publication gate remains open.
Future work is limited to new research beyond this frozen release: reduce
planner failures, recovery duration, path overhead, social-space exposure, and
angular jerk, then evaluate on additional planners, maps, simulators, and
hardware without tuning on the existing held-out test.
