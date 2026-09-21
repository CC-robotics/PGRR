# Validation trigger coverage audit

## Why this audit exists

The mask-trace replication produced no selector trace in two validation
episodes. That observation alone cannot tell us whether the scene contained no
detector-positive event, whether the detector missed a real interaction, or
whether safety handling bypassed temporary-subgoal selection. This audit reads
the preserved non-frozen JSONL episodes and separates those cases without
changing any threshold.

## Reproducible result

The checked-in report is
`outputs/student/eight_family_pilot/trigger_coverage_audit_20260912.json`.
It uses the configured `tau_on=0.65` and records the configured 0.9 m absolute
collision distance only as a comparison boundary.

| Episode | Split | Selector recovery | Emergency stop | Max score | Min robot-human proxy | Diagnosis |
|---|---|---:|---:|---:|---:|---|
| lead-stop retry02 | train | yes | yes | 1.00 | 0.786 m | selector recovery triggered |
| diagonal | train | no | no | 0.00 | 1.000 m | no recorded failure signal |
| diagonal | validation | no | no | 0.00 | 1.000 m | no recorded failure signal |
| head-on | train | yes | yes | 1.00 | 3.144 m | selector recovery triggered |
| head-on | validation | no | yes | 1.00 | 3.199 m | emergency-stop only |

The earlier phrase “both validation episodes remain NORMAL throughout” was too
coarse. The diagonal validation episode remains NORMAL, but the head-on
validation episode spends 886/896 samples in state 4 (`EMERGENCY_STOP`). It has
no temporary-subgoal selector trace because it never enters selector recovery,
not because the detector stays negative.

## Interpretation boundary

- The diagonal train/validation pair is a clean negative pair under the current
  recorded detector: every failure score is zero. Its privileged closest-human
  proxy is about 1.00 m, above the configured 0.9 m absolute collision boundary.
  This supports “no recorded detector-positive event,” not “proved safe.”
- The head-on validation episode is a safety-path observation: freeze/deadlock
  reach 1.0 and collision risk reaches 0.75, but the system remains in emergency
  stop rather than selecting a temporary subgoal. It therefore cannot answer
  the mask-layer replication question.
- `privileged.human_positions` is used only to reconstruct a diagnostic distance.
  It is never fed to the policy and cannot be used as a test observation.
- Observable minimum LiDAR range is not equated with human distance; walls and
  static geometry can be the closest return.

## Next safe gate

Select or generate one non-frozen validation prototype whose geometry produces
selector recovery (`PENDING_RECOVERY`/`RECOVERY`/`REJOIN`) rather than NORMAL or
emergency-only behavior. Preflight it first, keep all current thresholds fixed,
and run it only as a development smoke. This avoids blind seed retries and does
not touch `moderate_v6` or final evidence.

