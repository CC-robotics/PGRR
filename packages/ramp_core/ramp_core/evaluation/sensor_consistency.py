"""Checks relating privileged simulated humans to observable LiDAR returns."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class HumanLidarConsistency:
    """Expected and observed range for the nearest simulated human."""

    center_distance_m: float
    expected_surface_distance_m: float
    sector_distance_m: float
    relative_bearing_rad: float

    def is_visible(self, tolerance_m: float) -> bool:
        """Return whether LiDAR contains a surface no farther than expected."""

        if tolerance_m < 0.0:
            raise ValueError("tolerance_m must be non-negative")
        return self.sector_distance_m <= self.expected_surface_distance_m + tolerance_m


def nearest_human_lidar_consistency(
    robot_pose: Sequence[float],
    lidar: NDArray[np.floating],
    human_positions: Sequence[Sequence[float]],
    *,
    human_radius_m: float = 0.35,
    lidar_field_of_view_rad: float = 2.0 * math.pi,
) -> HumanLidarConsistency | None:
    """Compare the nearest human cylinder with LiDAR at its expected bearing.

    The result is an evaluation-only diagnostic: privileged human positions
    must never be fed to the deployed detector or recovery policy.
    """

    if len(robot_pose) < 3:
        raise ValueError("robot_pose must contain x, y, and yaw")
    if lidar.ndim != 1 or lidar.size < 2:
        raise ValueError("lidar must be a one-dimensional scan")
    if human_radius_m <= 0.0:
        raise ValueError("human_radius_m must be positive")
    if not 0.0 < lidar_field_of_view_rad <= 2.0 * math.pi:
        raise ValueError("lidar_field_of_view_rad must lie in (0, 2*pi]")
    if not human_positions:
        return None

    robot_x, robot_y, robot_yaw = map(float, robot_pose[:3])
    human_x, human_y = min(
        ((float(item[0]), float(item[1])) for item in human_positions),
        key=lambda item: math.dist((robot_x, robot_y), item),
    )
    center_distance = math.dist((robot_x, robot_y), (human_x, human_y))
    bearing = (math.atan2(human_y - robot_y, human_x - robot_x) - robot_yaw + math.pi) % (
        2.0 * math.pi
    ) - math.pi
    angle_min = -0.5 * lidar_field_of_view_rad
    angle_max = 0.5 * lidar_field_of_view_rad
    if bearing < angle_min or bearing > angle_max:
        return None

    coordinate = (bearing - angle_min) / lidar_field_of_view_rad * (lidar.size - 1)
    angular_radius = math.asin(
        min(0.99, human_radius_m / max(center_distance, 1.01 * human_radius_m))
    )
    half_beams = max(
        2,
        math.ceil(angular_radius / lidar_field_of_view_rad * (lidar.size - 1)) + 1,
    )
    lower = max(0, int(coordinate) - half_beams)
    upper = min(lidar.size, int(coordinate) + half_beams + 1)
    sector_distance = float(np.min(lidar[lower:upper]))
    return HumanLidarConsistency(
        center_distance_m=center_distance,
        expected_surface_distance_m=max(0.0, center_distance - human_radius_m),
        sector_distance_m=sector_distance,
        relative_bearing_rad=bearing,
    )
