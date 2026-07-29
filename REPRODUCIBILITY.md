# Reproducibility

All stochastic commands require `SEED` (default `0` for smoke tests). Final methods will share a locked episode manifest and test configuration. Generated artifacts record command, configuration hash, Git commit, and source-data hashes.

The offline and ROS2 environments are isolated by design. Use `scripts/bootstrap/activate_offline.sh` for offline work and `scripts/bootstrap/source_runtime.sh` for ROS2/Arena; never combine them.
