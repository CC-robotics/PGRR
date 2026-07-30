"""Pure helpers for constructing an online privileged expert state."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from ramp_core.observations import HumanState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.types import Pose2D, Velocity2D


def directional_scan_clearance(
    ranges: npt.ArrayLike,
    *,
    angle_min: float,
    angle_increment: float,
    direction: float,
    half_width_rad: float,
) -> float | None:
    """Return sector clearance, or None when that direction is not observed."""
    if angle_increment <= 0.0 or half_width_rad < 0.0:
        raise ValueError("scan angle increment must be positive and half-width non-negative")
    values = np.asarray(ranges, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        return None
    angles = angle_min + np.arange(values.size) * angle_increment
    errors = np.abs(np.arctan2(np.sin(angles - direction), np.cos(angles - direction)))
    observed = errors <= half_width_rad
    sector = values[observed & np.isfinite(values) & (values >= 0.0)]
    return float(np.min(sector)) if sector.size else None


def privileged_collision_risk(
    robot: Pose2D,
    velocity: Velocity2D,
    humans: Sequence[HumanState],
    *,
    horizon_s: float = 3.0,
    robot_radius_m: float = 0.36,
    prediction_margin_m: float = 0.25,
) -> bool:
    """Predict a privileged constant-velocity overlap within a finite horizon."""
    if horizon_s <= 0.0 or robot_radius_m <= 0.0 or prediction_margin_m < 0.0:
        raise ValueError("prediction horizon/radius must be positive and margin non-negative")
    robot_velocity = (
        velocity.linear * math.cos(robot.yaw),
        velocity.linear * math.sin(robot.yaw),
    )
    for human in humans:
        relative_position = human.position[0] - robot.x, human.position[1] - robot.y
        relative_velocity = (
            human.velocity[0] - robot_velocity[0],
            human.velocity[1] - robot_velocity[1],
        )
        speed_squared = (
            relative_velocity[0] * relative_velocity[0]
            + relative_velocity[1] * relative_velocity[1]
        )
        closest_time = (
            0.0
            if speed_squared <= 1.0e-9
            else max(
                0.0,
                min(
                    horizon_s,
                    -(
                        relative_position[0] * relative_velocity[0]
                        + relative_position[1] * relative_velocity[1]
                    )
                    / speed_squared,
                ),
            )
        )
        closest_distance = math.hypot(
            relative_position[0] + closest_time * relative_velocity[0],
            relative_position[1] + closest_time * relative_velocity[1],
        )
        if closest_distance <= robot_radius_m + human.radius + prediction_margin_m:
            return True
    return False


def estimate_human_states(
    positions: Sequence[tuple[float, float]],
    previous_positions: Sequence[tuple[float, float]],
    elapsed_s: float,
    *,
    radius_m: float = 0.35,
    maximum_speed_mps: float = 2.0,
) -> tuple[HumanState, ...]:
    """Estimate index-stable human velocities and reject implausible jumps."""
    if elapsed_s < 0.0:
        raise ValueError("elapsed_s must be non-negative")
    if radius_m <= 0.0 or maximum_speed_mps <= 0.0:
        raise ValueError("human radius and maximum speed must be positive")
    states: list[HumanState] = []
    for index, position in enumerate(positions):
        velocity = (0.0, 0.0)
        if elapsed_s > 1.0e-6 and index < len(previous_positions):
            velocity = (
                (position[0] - previous_positions[index][0]) / elapsed_s,
                (position[1] - previous_positions[index][1]) / elapsed_s,
            )
            speed = math.hypot(*velocity)
            if speed > maximum_speed_mps:
                scale = maximum_speed_mps / speed
                velocity = velocity[0] * scale, velocity[1] * scale
        states.append(HumanState(position=position, velocity=velocity, radius=radius_m))
    return tuple(states)


def augment_grid_with_scan(
    grid: OccupancyGrid,
    robot: Pose2D,
    ranges: npt.ArrayLike,
    *,
    angle_min: float,
    angle_increment: float,
    minimum_range_m: float,
    maximum_range_m: float,
    inflation_m: float = 0.25,
) -> OccupancyGrid:
    """Add current LiDAR endpoints to a copy of a static occupancy grid."""
    if angle_increment <= 0.0:
        raise ValueError("angle_increment must be positive")
    if minimum_range_m < 0.0 or maximum_range_m <= minimum_range_m:
        raise ValueError("invalid scan range limits")
    if inflation_m < 0.0:
        raise ValueError("inflation_m must be non-negative")
    values = np.asarray(ranges, dtype=np.float64)
    occupied = np.array(grid.occupied, copy=True)
    radius_cells = math.ceil(inflation_m / grid.resolution)
    for index, distance in enumerate(values):
        if not math.isfinite(float(distance)):
            continue
        if not minimum_range_m <= distance < maximum_range_m:
            continue
        angle = robot.yaw + angle_min + index * angle_increment
        endpoint = (
            robot.x + float(distance) * math.cos(angle),
            robot.y + float(distance) * math.sin(angle),
        )
        row, column = grid.world_to_grid(*endpoint)
        for delta_row in range(-radius_cells, radius_cells + 1):
            for delta_column in range(-radius_cells, radius_cells + 1):
                if delta_row * delta_row + delta_column * delta_column > radius_cells**2:
                    continue
                candidate = row + delta_row, column + delta_column
                if grid.in_bounds(candidate):
                    occupied[candidate] = True
    return OccupancyGrid(occupied, grid.resolution, grid.origin_x, grid.origin_y)
