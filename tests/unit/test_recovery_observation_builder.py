import inspect
import math

import numpy as np
import pytest
from ramp_core.recovery.observation_builder import RecoveryObservationBuilder
from ramp_core.types import FailurePrediction, PlannerStatus, Pose2D, Velocity2D


def _build(**overrides):
    values = {
        "pose": Pose2D(1.0, 2.0, math.pi / 2),
        "velocity": Velocity2D(0.3, -0.2),
        "goal": Pose2D(1.0, 5.0),
        "task_path": (),
        "lidar_history": [np.full(180, 2.0, dtype=np.float32)],
        "distance_history": [],
        "angular_velocity_history": [],
        "base_action": [0.4, 0.1],
        "planner_status": PlannerStatus.ACTIVE,
        "failure_prediction": FailurePrediction(0.7, 0.0, 0.0, 0.0),
    }
    values.update(overrides)
    return RecoveryObservationBuilder.build(**values)


def test_builder_preserves_node_padding_and_goal_fallback_contract():
    observation = _build()
    assert observation.lidar.shape == (5, 180)
    np.testing.assert_allclose(observation.lidar, 2.0)
    np.testing.assert_allclose(observation.goal_polar, [3.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(observation.path_waypoints[:, 0], 3.0, atol=1e-6)
    np.testing.assert_allclose(observation.path_waypoints[:, 1], 0.0, atol=1e-6)
    np.testing.assert_allclose(observation.progress_history, 3.0)
    np.testing.assert_allclose(observation.angular_velocity_history, 0.0)


def test_builder_uses_last_five_scans_and_last_ten_history_values():
    scans = [np.full(180, value, dtype=np.float32) for value in range(7)]
    observation = _build(
        lidar_history=scans,
        distance_history=list(range(12)),
        angular_velocity_history=list(range(12)),
    )
    np.testing.assert_allclose(observation.lidar[:, 0], [2, 3, 4, 5, 6])
    np.testing.assert_allclose(observation.progress_history, list(range(2, 12)))
    np.testing.assert_allclose(observation.angular_velocity_history, list(range(2, 12)))


def test_builder_keeps_deployable_fields_and_rejects_empty_lidar():
    parameters = inspect.signature(RecoveryObservationBuilder.build).parameters
    assert "humans" not in parameters
    assert "privileged" not in parameters
    observation = _build()
    np.testing.assert_allclose(observation.robot_velocity, [0.3, -0.2])
    np.testing.assert_allclose(observation.base_action, [0.4, 0.1])
    assert observation.failure_prediction.collision_risk == 0.7
    with pytest.raises(ValueError, match="at least one scan"):
        _build(lidar_history=[])


def test_builder_does_not_freeze_or_alias_mutable_controller_inputs():
    base_action = np.asarray([0.4, 0.1], dtype=np.float32)
    scan = np.full(180, 2.0, dtype=np.float32)

    observation = _build(base_action=base_action, lidar_history=[scan])

    assert base_action.flags.writeable
    assert scan.flags.writeable
    base_action[0] = 0.9
    scan[0] = 9.0
    np.testing.assert_allclose(observation.base_action, [0.4, 0.1])
    np.testing.assert_allclose(observation.lidar[:, 0], 2.0)
