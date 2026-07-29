# Planning-Guided Failure-Triggered Recovery

RAMP is the internal repository name for a research system that lets a classical navigation planner handle normal motion and invokes a constrained recovery policy only near navigation failures.

> Status: Gate 0 environment bring-up. See [CURRENT_STATUS.md](CURRENT_STATUS.md).

The ROS2/Arena runtime and `ramp-offline` Conda environment are intentionally separate. ROS2 and Arena use the system Humble installation and their own virtual environments; Conda is reserved for data processing, offline learning, testing, statistics, and paper generation.

```bash
make preflight
make conda
make test
```

Full setup and reproduction instructions will be expanded only as each gate is validated.
