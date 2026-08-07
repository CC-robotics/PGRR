from __future__ import annotations

import math

import numpy as np
import pytest
from ramp_core.evaluation.sensor_consistency import nearest_human_lidar_consistency


def test_human_proxy_is_found_at_expected_lidar_bearing() -> None:
    scan = np.full(180, 12.0, dtype=np.float32)
    scan[87:94] = 0.8
    result = nearest_human_lidar_consistency((0.0, 0.0, 0.0), scan, ((1.15, 0.0),))
    assert result is not None
    assert result.center_distance_m == pytest.approx(1.15)
    assert result.expected_surface_distance_m == pytest.approx(0.8)
    assert result.sector_distance_m == pytest.approx(0.8)
    assert result.is_visible(0.05)


def test_human_proxy_check_uses_robot_yaw_and_rejects_missing_surface() -> None:
    scan = np.full(180, 12.0, dtype=np.float32)
    result = nearest_human_lidar_consistency((0.0, 0.0, math.pi / 2.0), scan, ((0.0, 1.15),))
    assert result is not None
    assert result.relative_bearing_rad == pytest.approx(0.0)
    assert not result.is_visible(0.2)


def test_human_proxy_check_returns_none_without_privileged_humans() -> None:
    assert (
        nearest_human_lidar_consistency((0.0, 0.0, 0.0), np.ones(180, dtype=np.float32), ()) is None
    )
