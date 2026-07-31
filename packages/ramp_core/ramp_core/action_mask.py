"""Planning-derived validity mask for the fixed recovery actions."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.action_space import ACTION_COUNT, ACTIONS, BACKUP_ACTION_ID, REPLAN_ACTION_ID
from ramp_core.geometry import point_to_polyline_distance
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.online import directional_scan_clearance, scan_segment_is_free
from ramp_core.types import Pose2D


@dataclass(frozen=True, slots=True)
class ActionMaskConfig:
    robot_clearance: float = 0.25
    human_clearance: float = 0.65
    backup_distance: float = 0.45
    connectivity_limit_cells: int = 10_000


def compute_action_mask(
    robot: Pose2D,
    grid: OccupancyGrid,
    human_positions: Iterable[tuple[float, float]] = (),
    *,
    replan_available: bool,
    config: ActionMaskConfig | None = None,
) -> npt.NDArray[np.bool_]:
    """Return True for executable actions and guarantee at least WAIT is valid."""
    if config is None:
        config = ActionMaskConfig()
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    robot_index = grid.world_to_grid(robot.x, robot.y)
    humans = tuple(human_positions)
    for action in ACTIONS[:21]:
        target = action.target_pose(robot)
        assert target is not None
        target_index = grid.world_to_grid(target.x, target.y)
        valid = grid.is_free(target_index)
        valid = valid and grid.segment_is_free(
            (robot.x, robot.y), (target.x, target.y), config.robot_clearance
        )
        valid = valid and grid.connected(robot_index, target_index, config.connectivity_limit_cells)
        valid = valid and all(
            math.hypot(target.x - human[0], target.y - human[1]) >= config.human_clearance
            for human in humans
        )
        mask[action.action_id] = valid

    backup_end = (
        robot.x - config.backup_distance * math.cos(robot.yaw),
        robot.y - config.backup_distance * math.sin(robot.yaw),
    )
    mask[BACKUP_ACTION_ID] = grid.segment_is_free(
        (robot.x, robot.y), backup_end, config.robot_clearance
    ) and all(
        point_to_polyline_distance(human, ((robot.x, robot.y), backup_end))
        >= config.human_clearance
        for human in humans
    )
    mask[REPLAN_ACTION_ID] = replan_available
    return mask


def validate_selected_action(action_id: int, mask: npt.NDArray[np.bool_]) -> None:
    if mask.shape != (ACTION_COUNT,):
        raise ValueError(f"action mask must have shape ({ACTION_COUNT},)")
    if not 0 <= action_id < ACTION_COUNT or not bool(mask[action_id]):
        raise ValueError(f"action {action_id} is masked or out of range")


def apply_path_corridor_mask(
    mask: npt.ArrayLike,
    robot: Pose2D,
    global_path: Iterable[tuple[float, float]],
    *,
    maximum_deviation_m: float = 0.9,
    required_improvement_m: float = 0.05,
    backup_distance_m: float = 0.45,
) -> npt.NDArray[np.bool_]:
    """Keep translational recovery options inside or returning to the task path corridor."""
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    path = tuple(global_path)
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not path:
        raise ValueError("global path must not be empty")
    if maximum_deviation_m <= 0.0 or required_improvement_m < 0.0 or backup_distance_m < 0.0:
        raise ValueError("path-corridor distances are invalid")
    current_deviation = point_to_polyline_distance((robot.x, robot.y), path)

    def permitted(point: tuple[float, float]) -> bool:
        deviation = point_to_polyline_distance(point, path)
        return deviation <= maximum_deviation_m or (
            deviation <= current_deviation - required_improvement_m
        )

    for action in ACTIONS[:21]:
        target = action.target_pose(robot)
        assert target is not None
        constrained[action.action_id] &= permitted((target.x, target.y))
    backup_end = (
        robot.x - backup_distance_m * math.cos(robot.yaw),
        robot.y - backup_distance_m * math.sin(robot.yaw),
    )
    constrained[BACKUP_ACTION_ID] &= permitted(backup_end)
    return constrained


def apply_observable_scan_mask(
    mask: npt.ArrayLike,
    ranges: npt.ArrayLike,
    *,
    angle_min: float,
    angle_increment: float,
    swept_clearance_m: float = 0.48,
    target_clearance_m: float = 0.25,
    backup_distance_m: float = 0.45,
    sector_half_width_rad: float = math.radians(12.0),
    allow_unobserved_backup: bool = False,
) -> npt.NDArray[np.bool_]:
    """Apply the deployable LiDAR capsule and rear-observability constraints.

    This helper is shared by online inference and offline expert labeling so a
    demonstration can never rely on an action that the deployed policy masks.
    """
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if swept_clearance_m < 0.0 or target_clearance_m < 0.0 or backup_distance_m < 0.0:
        raise ValueError("scan-mask clearances and distances must be non-negative")
    for action in ACTIONS[:21]:
        assert action.radius is not None and action.angle_degrees is not None
        direction = math.radians(action.angle_degrees)
        directional_clearance = directional_scan_clearance(
            ranges,
            angle_min=angle_min,
            angle_increment=angle_increment,
            direction=direction,
            half_width_rad=sector_half_width_rad,
        )
        constrained[action.action_id] &= (
            directional_clearance is not None
            and directional_clearance >= action.radius + target_clearance_m
        )
        constrained[action.action_id] &= scan_segment_is_free(
            ranges,
            angle_min=angle_min,
            angle_increment=angle_increment,
            target=(
                action.radius * math.cos(direction),
                action.radius * math.sin(direction),
            ),
            clearance_m=swept_clearance_m,
        )
    rear_clearance = directional_scan_clearance(
        ranges,
        angle_min=angle_min,
        angle_increment=angle_increment,
        direction=math.pi,
        half_width_rad=sector_half_width_rad,
    )
    if rear_clearance is None:
        constrained[BACKUP_ACTION_ID] &= allow_unobserved_backup
    else:
        constrained[BACKUP_ACTION_ID] &= rear_clearance >= backup_distance_m + target_clearance_m
    return constrained
