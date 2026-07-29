"""Planning-derived validity mask for the fixed recovery actions."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.action_space import ACTION_COUNT, ACTIONS, BACKUP_ACTION_ID, REPLAN_ACTION_ID
from ramp_core.occupancy import OccupancyGrid
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
    )
    mask[REPLAN_ACTION_ID] = replan_available
    return mask


def validate_selected_action(action_id: int, mask: npt.NDArray[np.bool_]) -> None:
    if mask.shape != (ACTION_COUNT,):
        raise ValueError(f"action mask must have shape ({ACTION_COUNT},)")
    if not 0 <= action_id < ACTION_COUNT or not bool(mask[action_id]):
        raise ValueError(f"action {action_id} is masked or out of range")
