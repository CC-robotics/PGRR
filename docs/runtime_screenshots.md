# Real Arena runtime screenshots

Paper screenshots must come from a mapped application window during an actual
Arena episode.  Telemetry reconstructions are useful analysis figures, but they
are not presented as simulator screenshots.

The default capture command runs the committed moderate-v5 doorway scenario
through the same Arena, Gazebo, Nav2 DWB, deterministic actor controller, and
episode logger used by evaluation:

```bash
scripts/arena/capture_gazebo_snapshot.sh
```

The capture is isolated by `ROS_DOMAIN_ID`, `GZ_PARTITION`, and a dedicated
Xvfb display.  Arena is launched with `headless:=0`; after at least 60 genuine
episode samples, the script enumerates X11 windows and copies pixels from the
mapped Gazebo window.  The script rejects a missing window, a sub-640x480
frame, a nearly uniform Scene3D viewport, an incomplete episode, or an existing
output.  Before capture, it calls Gazebo's `/gui/move_to/pose` transport service
with a deterministic oblique camera pose derived from the robot start/goal
midpoint.  It resizes the mapped window to 1600x1000 and retries front-buffer
capture until the 3D viewport—not merely the GUI chrome—is populated.  Every
failure returns a non-zero exit code and all child processes are stopped.

The pinned minimal runtime does not ship Arena's empty reserved
`worlds/.generated/scenarios` GUI workspace.  Arena's RViz task panel queries
that path only when visualization is enabled; without it, the upstream
`task_generator` process exits before navigation activation.  The capture
inner script therefore creates that empty directory in the disposable
container layer before launch.  It does not change a scenario, map, planner,
controller, or evaluation timeout.

Artifacts are written to:

- `outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png`;
- `outputs/figures/runtime/gazebo_doorway_bottleneck_medium.metadata.json`;
- `paper/figures/runtime_gazebo_doorway_bottleneck_medium.png`;
- `outputs/logs/runtime_capture/` (ignored by Git but retained locally);
- `data/raw/runtime_capture_*.jsonl` and the corresponding outcome/metadata
  evidence (ignored by Git but retained locally).

The metadata contains the scenario, seed, commits, pinned image identifier,
window title, image hash, isolation values, and relative evidence paths.  PNG
text metadata is stripped before publication.  It contains no account name,
home directory, host name, or absolute host path.

To capture another committed scenario, provide a repository-relative path:

```bash
SCENARIO=scenarios/generated/moderate_v5/arena/map_empty/\
crossing_flow_high_validation_moderate_v5_r00_s75220.json \
RAMP_CAPTURE_ID=gazebo_crossing_flow_high \
ROS_DOMAIN_ID=227 GZ_PARTITION=pgrr_capture_crossing \
scripts/arena/capture_gazebo_snapshot.sh
```

Arena's documented local launch semantics are `0 = show all`, `1 = show only
RViz`, and `2 = show nothing`.  Therefore a Gazebo capture uses `0`.  A future
RViz-only capture may use `1`, but it must be labeled as RViz and must retain
the same raw runtime evidence; it must never be relabeled as Gazebo.
