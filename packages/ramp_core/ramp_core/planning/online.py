"""Pure helpers for constructing an online privileged expert state."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from ramp_core.observations import HumanState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.types import Pose2D, Velocity2D


def sanitize_near_field_returns(
    ranges: npt.ArrayLike,
    *,
    minimum_valid_range_m: float,
    bilateral_edge_self_return_max_m: float = 0.0,
) -> npt.NDArray[np.float64]:
    """Replace impossible near-field returns and the Jackal edge signature."""
    if not math.isfinite(minimum_valid_range_m) or minimum_valid_range_m < 0.0:
        raise ValueError("minimum valid LiDAR range must be finite and non-negative")
    if (
        not math.isfinite(bilateral_edge_self_return_max_m)
        or bilateral_edge_self_return_max_m < 0.0
    ):
        raise ValueError("bilateral edge self-return range must be finite and non-negative")
    values = np.asarray(ranges, dtype=np.float64).copy()
    if values.ndim != 1:
        raise ValueError("ranges must be one-dimensional")
    self_returns = np.isfinite(values) & (values >= 0.0) & (values < minimum_valid_range_m)
    values[self_returns] = math.inf
    if bilateral_edge_self_return_max_m > 0.0 and values.size >= 18:
        edge_count = max(3, math.ceil(values.size / 9.0))
        minimum_hits = max(2, math.ceil(edge_count * 0.3))
        low = np.isfinite(values) & (values >= 0.0) & (values < bilateral_edge_self_return_max_m)
        # Gazebo's Jackal GPU scan occasionally sees the rear body as broad
        # simultaneous clusters at both ends of the 270-degree scan. A real
        # unilateral wall/contact is deliberately preserved. Any close return
        # in the scan interior also remains observable.
        if (
            int(np.count_nonzero(low[:edge_count])) >= minimum_hits
            and int(np.count_nonzero(low[-edge_count:])) >= minimum_hits
        ):
            edge_mask = np.zeros(values.size, dtype=np.bool_)
            edge_mask[:edge_count] = True
            edge_mask[-edge_count:] = True
            values[low & edge_mask] = math.inf
    return values


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


def scan_segment_is_free(
    ranges: npt.ArrayLike,
    *,
    angle_min: float,
    angle_increment: float,
    target: tuple[float, float],
    clearance_m: float,
    allow_initial_overlap_when_separating: bool = False,
) -> bool:
    """Check a robot-frame segment against the swept circular footprint.

    Each finite LiDAR return is treated as an obstacle-surface point.  The
    segment is executable only when every point lies outside the capsule made
    by the robot centreline and ``clearance_m`` radius.  A bounded emergency
    escape may permit points already inside the initial footprint only when
    the commanded translation moves strictly away from every such point.
    """
    if angle_increment <= 0.0:
        raise ValueError("scan angle increment must be positive")
    if clearance_m < 0.0:
        raise ValueError("clearance_m must be non-negative")
    endpoint = np.asarray(target, dtype=np.float64)
    if endpoint.shape != (2,) or not bool(np.isfinite(endpoint).all()):
        raise ValueError("target must contain two finite coordinates")
    values = np.asarray(ranges, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("ranges must be one-dimensional")
    valid = np.isfinite(values) & (values >= 0.0)
    if not bool(valid.any()):
        return True
    angles = angle_min + np.flatnonzero(valid) * angle_increment
    distances = values[valid]
    points = np.column_stack((distances * np.cos(angles), distances * np.sin(angles)))
    initial_distances = np.linalg.norm(points, axis=1)
    initially_overlapping = initial_distances < clearance_m
    if bool(initially_overlapping.any()):
        if not allow_initial_overlap_when_separating:
            return False
        # For p relative to the robot and translation e, p.e < 0 means that
        # ||p - t e|| grows immediately for t > 0.  Do not exempt a lateral or
        # forward obstacle: those motions can scrape or approach it.
        if bool(np.any(points[initially_overlapping] @ endpoint >= 0.0)):
            return False
    length_squared = float(endpoint @ endpoint)
    if length_squared <= 1.0e-12:
        closest = np.zeros_like(points)
    else:
        fractions = np.clip(points @ endpoint / length_squared, 0.0, 1.0)
        closest = fractions[:, None] * endpoint
    distances_to_segment = np.linalg.norm(points - closest, axis=1)
    if allow_initial_overlap_when_separating:
        distances_to_segment[initially_overlapping] = clearance_m
    return bool(np.all(distances_to_segment >= clearance_m))


def privileged_time_to_collision(
    robot: Pose2D,
    velocity: Velocity2D,
    humans: Sequence[HumanState],
    *,
    horizon_s: float = 3.0,
    robot_radius_m: float = 0.36,
    prediction_margin_m: float = 0.25,
    prediction_step_s: float = 0.1,
) -> float | None:
    """Return first predicted overlap time along a constant-control trajectory."""
    if (
        horizon_s <= 0.0
        or robot_radius_m <= 0.0
        or prediction_margin_m < 0.0
        or prediction_step_s <= 0.0
    ):
        raise ValueError("prediction horizon/radius must be positive and margin non-negative")
    steps = max(1, math.ceil(horizon_s / prediction_step_s))
    angular = velocity.angular
    for step in range(steps + 1):
        time_s = min(horizon_s, step * prediction_step_s)
        if abs(angular) <= 1.0e-6:
            robot_x = robot.x + velocity.linear * math.cos(robot.yaw) * time_s
            robot_y = robot.y + velocity.linear * math.sin(robot.yaw) * time_s
        else:
            future_yaw = robot.yaw + angular * time_s
            radius = velocity.linear / angular
            robot_x = robot.x + radius * (math.sin(future_yaw) - math.sin(robot.yaw))
            robot_y = robot.y - radius * (math.cos(future_yaw) - math.cos(robot.yaw))
        for human in humans:
            human_x = human.position[0] + human.velocity[0] * time_s
            human_y = human.position[1] + human.velocity[1] * time_s
            if (
                math.hypot(human_x - robot_x, human_y - robot_y)
                <= robot_radius_m + human.radius + prediction_margin_m
            ):
                return time_s
    return None


def privileged_collision_risk(
    robot: Pose2D,
    velocity: Velocity2D,
    humans: Sequence[HumanState],
    *,
    horizon_s: float = 3.0,
    robot_radius_m: float = 0.36,
    prediction_margin_m: float = 0.25,
    prediction_step_s: float = 0.1,
) -> bool:
    """Predict overlap along the planner's constant-control unicycle trajectory."""
    return (
        privileged_time_to_collision(
            robot,
            velocity,
            humans,
            horizon_s=horizon_s,
            robot_radius_m=robot_radius_m,
            prediction_margin_m=prediction_margin_m,
            prediction_step_s=prediction_step_s,
        )
        is not None
    )


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
