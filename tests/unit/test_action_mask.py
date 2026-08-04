import numpy as np
from ramp_core.action_mask import (
    apply_observable_scan_mask,
    apply_path_corridor_mask,
    compute_action_mask,
    path_corridor_target_is_permitted,
    validate_selected_action,
)
from ramp_core.action_space import BACKUP_ACTION_ID, REPLAN_ACTION_ID, WAIT_ACTION_ID
from ramp_core.occupancy import OccupancyGrid
from ramp_core.types import Pose2D


def test_mask_blocks_obstacle_and_unavailable_replan() -> None:
    occupied = np.zeros((30, 30), dtype=np.bool_)
    occupied[10, 16] = True
    grid = OccupancyGrid(occupied, resolution=0.1)
    mask = compute_action_mask(Pose2D(1.0, 1.0, 0.0), grid, replan_available=False)
    assert mask.shape == (25,)
    assert not bool(mask[REPLAN_ACTION_ID])
    assert bool(mask[WAIT_ACTION_ID])
    assert np.any(~mask[:21])


def test_mask_blocks_unsafe_backup() -> None:
    occupied = np.zeros((20, 20), dtype=np.bool_)
    occupied[:, 3] = True
    grid = OccupancyGrid(occupied, resolution=0.1)
    mask = compute_action_mask(Pose2D(0.7, 1.0, 0.0), grid, replan_available=True)
    assert not bool(mask[BACKUP_ACTION_ID])
    validate_selected_action(WAIT_ACTION_ID, mask)


def test_mask_blocks_human_anywhere_along_backup_segment() -> None:
    grid = OccupancyGrid(np.zeros((30, 30), dtype=np.bool_), resolution=0.1)
    mask = compute_action_mask(
        Pose2D(1.0, 1.0, 0.0),
        grid,
        human_positions=((0.8, 1.0),),
        replan_available=True,
    )
    assert not bool(mask[BACKUP_ACTION_ID])


def test_observable_scan_mask_blocks_capsule_and_unobserved_backup() -> None:
    mask = np.ones(25, dtype=np.bool_)
    ranges = np.full(180, 6.0, dtype=np.float64)
    angle_min = -3.0 * np.pi / 4.0
    angle_increment = 3.0 * np.pi / 2.0 / 179.0
    center = round((0.0 - angle_min) / angle_increment)
    ranges[center] = 0.4
    constrained = apply_observable_scan_mask(
        mask,
        ranges,
        angle_min=angle_min,
        angle_increment=angle_increment,
    )
    assert not bool(constrained[BACKUP_ACTION_ID])
    assert not bool(constrained[3])


def test_path_corridor_blocks_outward_actions_and_allows_return() -> None:
    mask = np.ones(25, dtype=np.bool_)
    path = ((0.0, 0.0), (10.0, 0.0))
    inside = apply_path_corridor_mask(mask, Pose2D(2.0, 0.8, 0.0), path)
    assert not bool(inside[6])  # +90 degrees leaves the 0.9 m corridor.
    assert bool(inside[0])  # -90 degrees returns toward the task path.
    outside = apply_path_corridor_mask(mask, Pose2D(2.0, 1.2, 0.0), path)
    assert not bool(outside[6])
    assert bool(outside[0])


def test_emergency_translation_must_stay_in_or_improve_task_corridor() -> None:
    path = ((0.0, 0.0), (10.0, 0.0))
    assert path_corridor_target_is_permitted((2.0, 0.8), (2.2, 0.85), path)
    assert not path_corridor_target_is_permitted((2.0, 0.8), (2.0, 1.0), path)
    assert path_corridor_target_is_permitted((2.0, 1.1), (2.0, 0.9), path)
    assert not path_corridor_target_is_permitted((2.0, 1.1), (2.2, 1.1), path)
