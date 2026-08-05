# Moderate v5 benchmark

Moderate v5 is a predeclared, split-safe calibration of the social-navigation
benchmark. It was designed **only from moderate-v4 validation outcomes**. No v4
or v5 test episode was inspected or executed while choosing its geometry,
routes, speeds, or seed blocks.

## Validation evidence and scope

The complete v4 classical-planner validation run contained 72 valid episodes:
36 `GOAL_REACHED` and 36 `COLLISION`. Successes per nine episodes were
`blind_corner=0`, `crossing_flow=9`, `doorway_bottleneck=7`,
`group_blocking=9`, `head_on_corridor=5`, `opposite_streams=1`,
`overtaking=2`, and `temporary_blockage=3`. Trace inspection found two
benchmark-construction problems rather than informative recovery failures:

- the nominal DWB trajectory clipped the zero-margin static shelf intersection
  in every blind-corner condition; and
- temporary-blockage actors were initialized on the doorway wall and their
  long vertical routes crossed the static shelves.

The 0.65 m inner lanes used by overtaking and opposite streams were also below
the 0.71 m combined robot--pedestrian collision radii. Those interactions left
essentially no physically meaningful recovery margin. V5 corrects these
construction issues while retaining the same eight families, 1/2/4 actor
densities, robot footprint, nominal planner, actor controller, and one-shot
protocol. This is distribution calibration, not post-selection of episodes.

## Declared v5 changes

- `blind_corner` replaces the overlapping inner shelf corner with a 0.78 m
  footprint-inflated diagonal chamfer. The oncoming route still passes through
  the occluded turn, so dynamic conflict remains.
- `group_blocking` moves the nearest row to a 1.15 m nominal centerline offset.
  Across declared geometry offsets, it stays at least 0.30 m beyond the 0.73 m
  swept hard guard while leaving a lower recovery channel.
- `overtaking` and `opposite_streams` use family-specific 0.96/1.16 m nominal
  lane offsets. Including split geometry offsets, the closest lane remains at
  least 0.84 m from the robot centerline: collision-clear but still socially
  close.
- `temporary_blockage` widens only its doorway center gap from 2.0 to 2.2 m.
  Actors follow statically valid three-waypoint routes: a 1.4 m lead-in and a
  2.0 m crossing inside the opening. The 0.07--0.13 m/s speed range phases
  arrivals near the robot's doorway approach instead of spawning people in the
  wall.
- the vertical shelf terminates at 10.00 m, leaving a footprint-clear
  diagonal turn instead of making DWB graze the shelf tip;
- the compiler now rejects every v5 actor waypoint or route segment that
  intersects human-radius-inflated static geometry.

Head-on, doorway-bottleneck, and crossing-flow construction is unchanged apart
from fresh seeds. All knobs are explicit in
`configs/experiments/scenario_catalog_moderate_v5.yaml`.

## Splits and calibration gate

V5 reserves disjoint blocks 74000 (train), 75000 (validation), and 85000
(test), with 3/3/5 repetitions. The compiled manifests contain 72/72/120
episodes. Scenario IDs, seeds, serialized SHA-256 values, actor route clearance,
and robot-footprint A* reachability are checked automatically.

`scenarios/splits/moderate_v5_validation_calibration_smoke.yaml` predeclares 12
r0 validation episodes spanning the v4 hard families, the group guard, and
head-on/doorway controls. It is the only permitted first calibration set. Full
validation may be used to decide whether v5 produces a useful approximately
60--70% classical baseline and leaves recoverable failures for PGRR. The test
manifest remains sealed until configuration and code are frozen; no target
success rate is guaranteed in advance.

Generate the benchmark with:

```bash
conda run -n ramp-offline python scripts/data/compile_moderate_benchmark.py \
  --config configs/experiments/scenario_catalog_moderate_v5.yaml \
  --output-root scenarios
```

Results from v4 and v5 must remain labeled by revision and must never be pooled
without explicitly reporting the distribution change.
