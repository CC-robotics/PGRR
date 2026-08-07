from __future__ import annotations

import numpy as np
import pytest
from ramp_core.failure.labels import FailureLabelSeries, FailureType, generate_failure_labels
from ramp_core.failure.rules import RuleFailureConfig, TimedNavigationSample
from ramp_core.types import PlannerStatus


def _sample(timestamp: float) -> TimedNavigationSample:
    return TimedNavigationSample(
        timestamp=timestamp,
        position=(timestamp * 0.2, 0.0),
        goal_distance=10.0 - timestamp * 0.2,
        linear_velocity=0.2,
        angular_velocity=0.0,
        base_linear_command=0.2,
        base_angular_command=0.0,
        nearest_lidar_distance=4.0,
        planner_status=PlannerStatus.ACTIVE,
    )


def test_privileged_collision_label_respects_future_and_positive_windows() -> None:
    samples = [_sample(float(index)) for index in range(11)]
    labels = generate_failure_labels(
        samples,
        config=RuleFailureConfig(),
        collision_times=[10.0],
        collision_lookahead_s=2.0,
        pre_failure_window_s=3.0,
        post_failure_window_s=1.0,
    )
    collision = labels.failure[:, FailureType.COLLISION_RISK]
    assert not collision[:5].any()
    assert collision[5:].all()
    assert np.flatnonzero(labels.failure_onset).tolist() == [5]
    assert labels.time_to_failure[0] == pytest.approx(5.0)
    assert labels.time_to_failure[5] == pytest.approx(0.0)


def test_label_series_rejects_wrong_class_dimension() -> None:
    with pytest.raises(ValueError, match=r"\[T, 4\]"):
        FailureLabelSeries(
            failure=np.zeros((3, 3), dtype=np.bool_),
            failure_any=np.zeros(3, dtype=np.bool_),
            time_to_failure=np.zeros(3, dtype=np.float32),
            failure_onset=np.zeros(3, dtype=np.bool_),
            failure_end=np.zeros(3, dtype=np.bool_),
        )
