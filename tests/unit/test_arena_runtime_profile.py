from __future__ import annotations

from pathlib import Path

import yaml


def test_arena_task_boundary_exceeds_algorithm_episode_timeout() -> None:
    root = Path(__file__).resolve().parents[2]
    profile = yaml.safe_load(
        (root / "configs" / "platform" / "arena_task_generator_no_auto_reset.yaml").read_text()
    )
    parameters = profile["/**"]["ros__parameters"]
    assert parameters["auto_reset"] is False
    assert isinstance(parameters["timeout"], int)
    assert parameters["timeout"] > 120.0


def test_known_pose_profile_uses_gazebo_pose_odometry() -> None:
    root = Path(__file__).resolve().parents[2]
    plugin = (root / "configs/platform/jackal_planar_lidar.gazebo").read_text()
    mappings = (root / "configs/platform/jackal_mappings_mux.yaml").read_text()
    assert "gz-sim-odometry-publisher-system" in plugin
    assert "/model/$(arg name)/ground_truth_odometry" in plugin
    assert "/model/$(arg name)/wheel_odometry" in plugin
    assert "/model/$(arg name)/wheel_tf" in plugin
    assert '"gz_topic": "/model/{robot_name}/ground_truth_odometry"' in mappings
    assert '"gz_topic": "/model/{robot_name}/ground_truth_pose"' in mappings
    container = (root / "scripts/bootstrap/arena_container.sh").read_text()
    assert "task_generator_ground_truth_odom.patch" in container
