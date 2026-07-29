# Planning-Guided Failure-Triggered Recovery

RAMP is the internal repository name for a research system that lets a classical navigation planner handle normal motion and invokes a constrained recovery policy only near navigation failures.

> Status: Gate 0 accepted; Gate 1 classical baseline is in progress. See [CURRENT_STATUS.md](CURRENT_STATUS.md).

The ROS2/Arena runtime and `ramp-offline` Conda environment are intentionally separate. ROS2 and Arena use the system Humble installation and their own virtual environments; Conda is reserved for data processing, offline learning, testing, statistics, and paper generation.

```bash
make preflight
make conda
make test
make arena
make smoke
```

`make arena` uses the pinned isolated Humble/Gazebo image because the reviewed fallback installer requires privileged host mutations. `make smoke` runs Jackal and DWB under Xvfb, verifies live clock/TF/LiDAR/odometry, and submits a Nav2 goal. It never activates Conda or changes the host ROS selection.

Full training and paper reproduction instructions are expanded only as their gates are actually validated.
