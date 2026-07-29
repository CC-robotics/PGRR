# Known issues

## KI-001: Default interactive shell selects ROS Iron

The machine contains Humble and Iron, and the initial shell reported `ROS_DISTRO=iron`. Arena runtime scripts explicitly unset inherited ROS setup variables where practical and source `/opt/ros/humble/setup.bash`. Do not run Arena from Conda base.

## KI-002: Inherited ROS pytest plugin contaminated Conda tests

The initial `make test` inherited `/opt/ros/iron` through `PYTHONPATH`, loading an incompatible `launch_testing` pytest plugin. Offline commands now clear ROS discovery variables, the activation helper does the same, and a regression test checks that no `/opt/ros` path is visible. The Makefile also enables `pipefail` so `tee` cannot hide test failures.

## KI-003: Full Conda SAT solve was unnecessarily slow

Putting the scientific and PyTorch stack across Conda channels spent nine minutes in dependency solving without creating an environment. The Conda layer now contains Python 3.10 and pip; all declared wheels remain in `environment.yml` and exact resolved versions are locked in `requirements-offline.lock.txt`.
