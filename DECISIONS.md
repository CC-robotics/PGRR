# Decision log

## D-001: Strict offline/runtime environment separation

The host has both ROS2 Humble and Iron, while the initial shell selected Iron inside Conda base. Arena commands will run in a clean non-Conda shell that explicitly sources Humble. Offline ML commands will run only through `conda run -n ramp-offline` or the offline activation helper.
