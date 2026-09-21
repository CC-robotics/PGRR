# Lead-stop validation selector candidate

## Completed work

A single non-frozen validation development scenario has been generated and
statically preflighted:

- family: `lead_pedestrian_sudden_stop`
- scenario: `lead_pedestrian_sudden_stop_low_validation_r00_s93500`
- split/seed: validation / 93500
- robot route: `(5, 12)` to `(27, 12)`
- lead actor: `(10, 12)` to terminal stop `(16, 12)` at 0.55 m/s
- held-out test materialized: no

The scenario JSON, preview, split metadata, and SHA-256 are recorded in
`outputs/student/eight_family_geometry_draft/lead_stop_validation_smoke_manifest.json`.
The runtime contract preflight is recorded in
`outputs/student/eight_family_pilot/mask_trace_leadstop_validation_preflight.json`;
all four default-off/forwarding checks pass and the proposed episode ID does
not overwrite an existing local episode.

## Why this candidate was selected

The preserved train episode from the same family entered selector recovery and
produced 110 complete mask traces. The validation prototype retains the same
central, collinear lead-and-stop interaction while using the catalog's separate
validation seed. It is therefore a more evidence-based next smoke than another
diagonal retry, whose train and validation episodes both recorded zero failure
score, or the current head-on validation case, which went directly to emergency
stop without selector recovery.

This is only a likelihood argument. Static geometry cannot guarantee that ROS
timing, actor motion, perception, and the state machine will enter selector
recovery. The scenario is not a formal validation result, and its geometry is
not yet a strong held-out generalization test because it deliberately mirrors
the train prototype for cross-seed replication.

## Gate status

Static generation and preflight are complete. A later live run, if performed,
must use exactly the preflighted new episode ID, keep all detector and mask
thresholds fixed, preserve any failure outcome, and remain a non-frozen
development smoke. No live run was started in this gate.

