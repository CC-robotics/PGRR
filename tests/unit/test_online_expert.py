from __future__ import annotations

import math

import numpy as np
import pytest
from ramp_core.action_mask import compute_action_mask
from ramp_core.action_space import BACKUP_ACTION_ID
from ramp_core.observations import HumanState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.online import (
    augment_grid_with_scan,
    directional_scan_clearance,
    estimate_human_states,
    privileged_collision_risk,
    privileged_time_to_collision,
    scan_segment_is_free,
)
from ramp_core.types import Pose2D, Velocity2D


def test_human_velocity_estimation_is_index_stable() -> None:
    states = estimate_human_states(
        ((1.0, 0.0), (0.0, 2.0)),
        ((0.5, 0.0), (0.0, 1.5)),
        0.5,
    )
    assert states[0].velocity == pytest.approx((1.0, 0.0))
    assert states[1].velocity == pytest.approx((0.0, 1.0))


def test_human_velocity_estimation_caps_discontinuity() -> None:
    state = estimate_human_states(((10.0, 0.0),), ((0.0, 0.0),), 0.1)[0]
    assert math.hypot(*state.velocity) == pytest.approx(2.0)


def test_scan_endpoints_are_added_without_mutating_static_grid() -> None:
    static = OccupancyGrid(np.zeros((30, 30), dtype=np.bool_), 0.1)
    augmented = augment_grid_with_scan(
        static,
        Pose2D(1.0, 1.0, 0.0),
        [1.0],
        angle_min=0.0,
        angle_increment=0.1,
        minimum_range_m=0.05,
        maximum_range_m=5.0,
        inflation_m=0.2,
    )
    endpoint = augmented.world_to_grid(2.0, 1.0)
    assert not bool(static.occupied[endpoint])
    assert bool(augmented.occupied[endpoint])
    assert bool(augmented.occupied[endpoint[0] + 1, endpoint[1]])


def test_scan_ignores_max_range_returns() -> None:
    static = OccupancyGrid(np.zeros((30, 30), dtype=np.bool_), 0.1)
    augmented = augment_grid_with_scan(
        static,
        Pose2D(1.0, 1.0, 0.0),
        [5.0],
        angle_min=0.0,
        angle_increment=0.1,
        minimum_range_m=0.05,
        maximum_range_m=5.0,
    )
    assert not bool(augmented.occupied.any())


def test_directional_clearance_distinguishes_unobserved_rear_sector() -> None:
    ranges = np.full(271, 2.0, dtype=np.float32)
    clearance = directional_scan_clearance(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        direction=math.pi,
        half_width_rad=math.radians(12.0),
    )
    assert clearance is None


def test_directional_clearance_reads_observed_front_sector() -> None:
    ranges = np.full(271, 2.0, dtype=np.float32)
    ranges[135] = 0.7
    clearance = directional_scan_clearance(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        direction=0.0,
        half_width_rad=math.radians(2.0),
    )
    assert clearance == pytest.approx(0.7)


def test_swept_scan_mask_rejects_off_axis_footprint_collision() -> None:
    ranges = np.full(271, np.inf, dtype=np.float32)
    obstacle_angle = math.radians(37.0)
    obstacle_index = round((obstacle_angle + 3.0 * math.pi / 4.0) / math.radians(1.0))
    ranges[obstacle_index] = 0.5

    assert not scan_segment_is_free(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        target=(1.0, 0.0),
        clearance_m=0.4,
    )
    assert scan_segment_is_free(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        target=(1.0, 0.0),
        clearance_m=0.25,
    )


def test_emergency_translation_can_separate_from_initial_rear_overlap() -> None:
    ranges = np.full(271, np.inf, dtype=np.float32)
    rear_side_index = round((math.radians(125.0) + 3.0 * math.pi / 4.0) / math.radians(1.0))
    ranges[rear_side_index] = 0.31

    assert not scan_segment_is_free(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        target=(0.20, 0.0),
        clearance_m=0.36,
    )
    assert scan_segment_is_free(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        target=(0.20, 0.0),
        clearance_m=0.36,
        allow_initial_overlap_when_separating=True,
    )


def test_emergency_translation_cannot_escape_through_initial_front_overlap() -> None:
    ranges = np.full(271, np.inf, dtype=np.float32)
    ranges[135] = 0.31

    assert not scan_segment_is_free(
        ranges,
        angle_min=-3.0 * math.pi / 4.0,
        angle_increment=math.radians(1.0),
        target=(0.20, 0.0),
        clearance_m=0.36,
        allow_initial_overlap_when_separating=True,
    )


def test_swept_scan_mask_validates_inputs() -> None:
    with pytest.raises(ValueError, match="positive"):
        scan_segment_is_free(
            [1.0],
            angle_min=0.0,
            angle_increment=0.0,
            target=(1.0, 0.0),
            clearance_m=0.4,
        )


def test_endpoint_uncertainty_does_not_double_inflate_robot_footprint() -> None:
    static = OccupancyGrid(np.zeros((100, 100), dtype=np.bool_), 0.1)
    robot = Pose2D(5.0, 5.0, 0.0)
    augmented = augment_grid_with_scan(
        static,
        robot,
        [0.47, 0.47],
        angle_min=-math.pi / 2.0,
        angle_increment=math.pi,
        minimum_range_m=0.05,
        maximum_range_m=5.0,
        inflation_m=0.0,
    )
    mask = compute_action_mask(robot, augmented, replan_available=True)
    assert mask[BACKUP_ACTION_ID]


def test_privileged_trigger_predicts_approaching_but_not_receding_human() -> None:
    robot = Pose2D(0.0, 0.0, 0.0)
    velocity = Velocity2D(0.3, 0.0)
    approaching = HumanState(position=(2.0, 0.0), velocity=(-0.5, 0.0), radius=0.35)
    receding = HumanState(position=(2.0, 0.0), velocity=(0.8, 0.0), radius=0.35)
    assert privileged_collision_risk(robot, velocity, (approaching,))
    assert not privileged_collision_risk(robot, velocity, (receding,))


def test_privileged_trigger_respects_planner_turning_trajectory() -> None:
    robot = Pose2D(0.0, 0.0, 0.0)
    human = HumanState(position=(1.2, 0.0), velocity=(0.0, 0.0), radius=0.2)
    straight = Velocity2D(0.5, 0.0)
    turning = Velocity2D(0.5, 1.0)
    assert privileged_collision_risk(
        robot,
        straight,
        (human,),
        prediction_margin_m=0.15,
    )
    assert not privileged_collision_risk(
        robot,
        turning,
        (human,),
        prediction_margin_m=0.15,
    )


def test_privileged_trigger_reports_first_collision_time() -> None:
    robot = Pose2D(0.0, 0.0, 0.0)
    human = HumanState(position=(2.0, 0.0), velocity=(-0.5, 0.0), radius=0.35)
    collision_time = privileged_time_to_collision(
        robot,
        Velocity2D(0.5, 0.0),
        (human,),
        prediction_margin_m=0.0,
        prediction_step_s=0.05,
    )
    assert collision_time == pytest.approx(1.3)
