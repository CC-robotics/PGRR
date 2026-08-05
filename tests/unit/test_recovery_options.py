from __future__ import annotations

import math

import numpy as np
import pytest
from ramp_core.action_mask import (
    apply_observable_scan_mask,
    apply_path_corridor_mask,
    compute_action_mask,
)
from ramp_core.action_space import (
    ACTION_COUNT,
    ACTIONS,
    BACKUP_ACTION_ID,
    CONTINUE_ACTION_ID,
    REPLAN_ACTION_ID,
    WAIT_ACTION_ID,
)
from ramp_core.observations import HumanState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.recovery.options import (
    BoundedBackupOption,
    BoundedSubgoalOption,
    ObservableClosingSideLatch,
    ObservableDirectionalYieldLatch,
    ObservableGoalProgressBudget,
    ObservableNetRetreatGuard,
    ObservableSubgoalStallGuard,
    PrivilegedYieldOption,
    TemporalClosingSideConfig,
    TemporalClosingSideResult,
    constrain_ambiguous_yield_motion,
    constrain_directional_yield_motion,
    constrain_near_field_subgoal_radius,
    constrain_net_retreat,
    constrain_recurrent_yield_escape,
    constrain_rejoin_actions,
    constrain_repeated_backup,
    constrain_repeated_replan,
    constrain_stalled_rejoin,
    constrain_stalled_subgoals,
    constrain_stalled_wait,
    constrain_task_lateral_sides,
    constrain_temporal_closing_side,
    effective_recovery_path_deviation,
    ensure_safe_wait_fallback,
    orient_subgoal_for_rejoin,
    should_continue_recovery_option,
)
from ramp_core.types import Pose2D


def _temporal_closing_stack(
    *,
    right_beams: int,
    left_beams: int,
    pose_yaw_rad: float = 0.0,
    path_heading_rad: float = 0.0,
    closing_delta_m: float = 0.30,
    current_range_m: float = 2.0,
) -> np.ndarray:
    """Construct exact task-frame closing evidence for option regressions."""

    stack = np.full((5, 180), 6.0, dtype=np.float64)
    beam_angles = np.linspace(-math.pi, math.pi, 180)
    relative = np.arctan2(
        np.sin(pose_yaw_rad + beam_angles - path_heading_rad),
        np.cos(pose_yaw_rad + beam_angles - path_heading_rad),
    )
    right_indices = np.flatnonzero(
        (relative >= -math.radians(60.0)) & (relative <= -math.radians(5.0))
    )[:right_beams]
    left_indices = np.flatnonzero(
        (relative >= math.radians(5.0)) & (relative <= math.radians(60.0))
    )[:left_beams]
    assert len(right_indices) == right_beams
    assert len(left_indices) == left_beams
    for frame_index, fraction in enumerate(np.linspace(1.0, 0.0, 5)):
        stack[frame_index, right_indices] = current_range_m + closing_delta_m * fraction
        stack[frame_index, left_indices] = current_range_m + closing_delta_m * fraction
    return stack


def _apply_closing_side_latch(
    latch: ObservableClosingSideLatch,
    mask: np.ndarray,
    *,
    pose: Pose2D,
    path_heading_rad: float,
    right_beams: int,
    left_beams: int,
    angular_speed_radps: float = 0.0,
) -> tuple[TemporalClosingSideResult, np.ndarray]:
    raw = constrain_temporal_closing_side(
        mask,
        _temporal_closing_stack(
            right_beams=right_beams,
            left_beams=left_beams,
            pose_yaw_rad=pose.yaw,
            path_heading_rad=path_heading_rad,
        ),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=pose,
        path_heading_rad=path_heading_rad,
        angular_speed_radps=angular_speed_radps,
        minimum_lateral_displacement_m=0.25,
    )
    right_occupied, left_occupied = latch.update(
        yield_active=True,
        right_occupied=raw.right_occupied,
        left_occupied=raw.left_occupied,
        rotation_gated=raw.rotation_gated,
    )
    effective = constrain_task_lateral_sides(
        raw.mask,
        pose=pose,
        path_heading_rad=path_heading_rad,
        minimum_lateral_displacement_m=0.25,
        right_occupied=right_occupied,
        left_occupied=left_occupied,
    )
    return raw, effective


def _path_deviation(*, policy_type: str, latched: bool, recoveries: int) -> float:
    return effective_recovery_path_deviation(
        policy_type=policy_type,
        directional_yield_latched=latched,
        consecutive_recoveries=recoveries,
        recurrent_escape_after_recoveries=1,
        normal_maximum_deviation_m=0.6,
        recurrent_maximum_deviation_m=1.5,
    )


@pytest.mark.parametrize(
    ("policy_type", "latched", "recoveries"),
    [
        ("bc", False, 1),
        ("bc", True, 0),
        ("heuristic", True, 1),
        ("expert", True, 1),
    ],
)
def test_recurrent_path_envelope_requires_latched_bc_recovery(
    policy_type: str,
    latched: bool,
    recoveries: int,
) -> None:
    assert _path_deviation(
        policy_type=policy_type,
        latched=latched,
        recoveries=recoveries,
    ) == pytest.approx(0.6)


def test_recurrent_path_envelope_makes_only_existing_lateral_action_eligible() -> None:
    pose = Pose2D(2.0, 0.8, 0.0)
    path = ((0.0, 0.0), (10.0, 0.0))
    planning_safe = np.ones(ACTION_COUNT, dtype=np.bool_)
    normal = apply_path_corridor_mask(
        planning_safe,
        pose,
        path,
        maximum_deviation_m=_path_deviation(policy_type="bc", latched=False, recoveries=1),
    )
    recurrent = apply_path_corridor_mask(
        planning_safe,
        pose,
        path,
        maximum_deviation_m=_path_deviation(policy_type="bc", latched=True, recoveries=1),
    )
    assert not normal[6]
    assert recurrent[6]


def test_recurrent_path_envelope_cannot_unmask_scan_or_map_invalid_action() -> None:
    pose = Pose2D(2.0, 0.8, 0.0)
    path = ((0.0, 0.0), (10.0, 0.0))
    occupied = np.zeros((40, 40), dtype=np.bool_)
    occupied[14, 20] = True  # action 6 endpoint at (2.0, 1.4)
    map_mask = compute_action_mask(
        pose,
        OccupancyGrid(occupied, resolution=0.1),
        replan_available=True,
    )
    assert not map_mask[6]

    ranges = np.full(180, 6.0, dtype=np.float64)
    angle_min = -3.0 * np.pi / 4.0
    angle_increment = 3.0 * np.pi / 2.0 / 179.0
    left = round((np.pi / 2.0 - angle_min) / angle_increment)
    ranges[left] = 0.4
    scan_mask = apply_observable_scan_mask(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        ranges,
        angle_min=angle_min,
        angle_increment=angle_increment,
    )
    assert not scan_mask[6]

    for safety_mask in (map_mask, scan_mask):
        still_invalid = apply_path_corridor_mask(
            safety_mask,
            pose,
            path,
            maximum_deviation_m=_path_deviation(policy_type="bc", latched=True, recoveries=1),
        )
        assert not still_invalid[6]
        assert not bool(np.any(still_invalid & ~safety_mask))


def test_directional_yield_requires_consecutive_observable_clearance() -> None:
    latch = ObservableDirectionalYieldLatch(
        trigger_threshold=0.65,
        release_clearance_m=1.25,
        release_frames=3,
    )
    assert latch.update(collision_risk=0.8, forward_clearance_m=0.9)
    assert latch.update(collision_risk=0.0, forward_clearance_m=1.30)
    assert latch.clear_frames == 1
    assert latch.update(collision_risk=0.0, forward_clearance_m=None)
    assert latch.clear_frames == 0
    assert latch.update(collision_risk=0.0, forward_clearance_m=1.30)
    assert latch.update(collision_risk=0.0, forward_clearance_m=1.30)
    assert not latch.update(collision_risk=0.0, forward_clearance_m=1.30)
    assert latch.clear_frames == 0


def test_directional_yield_retrigger_resets_release_evidence() -> None:
    latch = ObservableDirectionalYieldLatch(release_frames=2)
    assert latch.update(collision_risk=0.9, forward_clearance_m=2.0)
    assert latch.update(collision_risk=0.0, forward_clearance_m=2.0)
    assert latch.clear_frames == 1
    assert latch.update(collision_risk=0.7, forward_clearance_m=2.0)
    assert latch.clear_frames == 0
    assert latch.update(collision_risk=0.0, forward_clearance_m=2.0)
    assert not latch.update(collision_risk=0.0, forward_clearance_m=2.0)


def test_directional_yield_uses_the_configured_recovery_threshold() -> None:
    latch = ObservableDirectionalYieldLatch(trigger_threshold=0.8)
    assert not latch.update(collision_risk=0.7, forward_clearance_m=0.5)
    assert latch.update(collision_risk=0.8, forward_clearance_m=0.5)


def test_directional_yield_does_not_count_a_stale_scan_twice() -> None:
    latch = ObservableDirectionalYieldLatch(release_frames=2)
    assert latch.update(collision_risk=0.9, forward_clearance_m=0.8, observation_id=10)
    assert latch.update(collision_risk=0.0, forward_clearance_m=2.0, observation_id=11)
    assert latch.clear_frames == 1
    assert latch.update(collision_risk=0.0, forward_clearance_m=2.0, observation_id=11)
    assert latch.clear_frames == 1
    assert not latch.update(collision_risk=0.0, forward_clearance_m=2.0, observation_id=12)


def test_directional_yield_masks_forward_motion_without_unmasking() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    mask[6] = False
    constrained = constrain_directional_yield_motion(
        mask,
        pose=Pose2D(2.0, 1.0, 0.0),
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    for action in ACTIONS[:WAIT_ACTION_ID]:
        assert action.angle_degrees is not None
        assert bool(constrained[action.action_id]) == (
            abs(action.angle_degrees) == 90 and bool(mask[action.action_id])
        )
    assert constrained[BACKUP_ACTION_ID]
    assert constrained[WAIT_ACTION_ID]
    assert constrained[REPLAN_ACTION_ID]
    assert not constrained[CONTINUE_ACTION_ID]
    assert not bool(np.any(constrained & ~mask))


def test_ambiguous_yield_retains_only_existing_non_lateral_actions() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    mask[BACKUP_ACTION_ID] = False
    constrained = constrain_ambiguous_yield_motion(
        mask,
        side_evidence_available=False,
    )

    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[[WAIT_ACTION_ID, REPLAN_ACTION_ID]] = True
    assert np.array_equal(constrained, expected)
    assert not np.any(constrained & ~mask)


def test_ambiguous_yield_is_inactive_after_side_evidence() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[[0, WAIT_ACTION_ID, BACKUP_ACTION_ID, REPLAN_ACTION_ID]] = True
    constrained = constrain_ambiguous_yield_motion(
        mask,
        side_evidence_available=True,
    )
    assert np.array_equal(constrained, mask)
    assert constrained is not mask


def test_ambiguous_yield_rejects_invalid_mask_shape() -> None:
    with pytest.raises(ValueError, match="mask must have shape"):
        constrain_ambiguous_yield_motion(
            np.ones(ACTION_COUNT - 1, dtype=np.bool_),
            side_evidence_available=False,
        )


def test_near_field_radius_bound_only_removes_long_subgoals() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    mask[2] = False
    constrained = constrain_near_field_subgoal_radius(
        mask,
        nearest_clearance_m=0.82,
        activation_clearance_m=1.0,
        maximum_radius_m=0.6,
    )
    assert constrained[:7].tolist() == [True, True, False, True, True, True, True]
    assert not bool(constrained[7:WAIT_ACTION_ID].any())
    assert bool(np.all(constrained[WAIT_ACTION_ID:]))
    assert not constrained[2]


def test_near_field_radius_bound_is_inactive_at_clearance_boundary() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_near_field_subgoal_radius(
        mask,
        nearest_clearance_m=1.0,
        activation_clearance_m=1.0,
        maximum_radius_m=0.6,
    )
    assert np.array_equal(constrained, mask)


@pytest.mark.parametrize(
    ("nearest", "activation", "radius"),
    [(-0.1, 1.0, 0.6), (0.8, 0.0, 0.6), (0.8, 1.0, 0.0), (math.inf, 1.0, 0.6)],
)
def test_near_field_radius_bound_rejects_invalid_thresholds(
    nearest: float, activation: float, radius: float
) -> None:
    with pytest.raises(ValueError, match="near-field"):
        constrain_near_field_subgoal_radius(
            np.ones(ACTION_COUNT, dtype=np.bool_),
            nearest_clearance_m=nearest,
            activation_clearance_m=activation,
            maximum_radius_m=radius,
        )


def test_recovery_subgoal_retains_position_and_uses_wrapped_path_heading() -> None:
    target = Pose2D(2.5, -1.0, -math.pi / 2)
    oriented = orient_subgoal_for_rejoin(target, path_heading_rad=2.0 * math.pi + 0.25)
    assert (oriented.x, oriented.y) == (2.5, -1.0)
    assert oriented.yaw == pytest.approx(0.25)


def test_recovery_subgoal_heading_rejects_non_finite_geometry() -> None:
    with pytest.raises(ValueError, match="finite"):
        orient_subgoal_for_rejoin(Pose2D(0.0, 0.0, 0.0), path_heading_rad=math.inf)


def test_directional_yield_trace_retains_near_lateral_left_escape_only() -> None:
    """Reproduce the left-escape mask at the diagnosed failure heading."""

    pose = Pose2D(0.0, 0.0, -0.091962)
    planning_mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    planning_mask[[5, 6, 12, 13, WAIT_ACTION_ID, BACKUP_ACTION_ID]] = True

    constrained = constrain_directional_yield_motion(
        planning_mask,
        pose=pose,
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )

    assert np.flatnonzero(constrained).tolist() == [6, 13, WAIT_ACTION_ID, BACKUP_ACTION_ID]
    assert not constrained[5] and not constrained[12]
    assert not bool(np.any(constrained & ~planning_mask))


def test_right_occupied_trace_recurrent_escape_keeps_exact_left_pair() -> None:
    pose = Pose2D(0.0, 0.0, -0.091962)
    planning_mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    planning_mask[[5, 6, 12, 13, WAIT_ACTION_ID, BACKUP_ACTION_ID]] = True
    directional = constrain_directional_yield_motion(
        planning_mask,
        pose=pose,
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    closing_side = constrain_task_lateral_sides(
        directional,
        pose=pose,
        path_heading_rad=0.0,
        minimum_lateral_displacement_m=0.25,
        right_occupied=True,
        left_occupied=False,
    )
    recurrent = constrain_recurrent_yield_escape(
        closing_side,
        escape_required=True,
        pose=pose,
        path_heading_rad=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    assert np.flatnonzero(recurrent).tolist() == [6, 13]
    assert not bool(np.any(recurrent & ~planning_mask))


def test_directional_yield_trace_is_mirror_symmetric() -> None:
    def mirrored_escape(*, yaw: float, candidate_ids: list[int], left_occupied: bool) -> list[int]:
        pose = Pose2D(0.0, 0.0, yaw)
        planning_mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
        planning_mask[[*candidate_ids, WAIT_ACTION_ID, BACKUP_ACTION_ID]] = True
        directional = constrain_directional_yield_motion(
            planning_mask,
            pose=pose,
            path_heading_rad=0.0,
            backup_distance_m=0.45,
        )
        open_side = constrain_task_lateral_sides(
            directional,
            pose=pose,
            path_heading_rad=0.0,
            minimum_lateral_displacement_m=0.25,
            right_occupied=not left_occupied,
            left_occupied=left_occupied,
        )
        recurrent = constrain_recurrent_yield_escape(
            open_side,
            escape_required=True,
            pose=pose,
            path_heading_rad=0.0,
            minimum_lateral_displacement_m=0.25,
        )
        assert not bool(np.any(recurrent & ~planning_mask))
        return np.flatnonzero(recurrent).tolist()

    left_escape = mirrored_escape(
        yaw=-0.091962,
        candidate_ids=[5, 6, 12, 13],
        left_occupied=False,
    )
    right_escape = mirrored_escape(
        yaw=0.091962,
        candidate_ids=[0, 1, 7, 8],
        left_occupied=True,
    )

    assert left_escape == [6, 13]
    assert right_escape == [0, 7]
    assert [ACTIONS[action_id].radius for action_id in left_escape] == [
        ACTIONS[action_id].radius for action_id in right_escape
    ]


def test_directional_yield_uses_path_heading_not_robot_heading() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_directional_yield_motion(
        mask,
        pose=Pose2D(0.0, 0.0, math.pi / 2.0),
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    assert constrained[BACKUP_ACTION_ID]
    assert constrained[WAIT_ACTION_ID]
    # With the robot facing north, its -90-degree subgoals point east along
    # the blocked path and must be removed; +90 degrees point west and remain.
    assert not constrained[0]
    assert constrained[6]
    facing_backward = constrain_directional_yield_motion(
        mask,
        pose=Pose2D(0.0, 0.0, math.pi),
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    assert not facing_backward[BACKUP_ACTION_ID]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"trigger_threshold": -0.1}, "trigger threshold"),
        ({"release_clearance_m": float("inf")}, "release clearance"),
        ({"release_frames": 0}, "release frames"),
        ({"latched": False, "clear_frames": 1}, "cannot retain"),
    ],
)
def test_directional_yield_rejects_invalid_configuration(
    kwargs: dict[str, float | int | bool], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ObservableDirectionalYieldLatch(**kwargs)


def test_bounded_backup_holds_then_releases_on_observable_clearance_gain() -> None:
    option = BoundedBackupOption()
    assert not option.is_complete(
        elapsed_s=0.79,
        start_clearance_m=0.50,
        current_clearance_m=0.90,
    )
    assert option.is_complete(
        elapsed_s=0.80,
        start_clearance_m=0.50,
        current_clearance_m=0.75,
    )


def test_bounded_backup_runs_to_hard_limit_without_clearance_gain() -> None:
    option = BoundedBackupOption()
    assert not option.is_complete(
        elapsed_s=2.99,
        start_clearance_m=0.50,
        current_clearance_m=0.74,
    )
    assert option.is_complete(
        elapsed_s=3.0,
        start_clearance_m=0.50,
        current_clearance_m=0.50,
    )


def test_bounded_backup_missing_observation_cannot_release_early() -> None:
    option = BoundedBackupOption()
    assert not option.is_complete(
        elapsed_s=2.0,
        start_clearance_m=0.50,
        current_clearance_m=None,
    )
    assert option.is_complete(
        elapsed_s=3.0,
        start_clearance_m=None,
        current_clearance_m=None,
    )


def test_bounded_backup_maximum_matches_mask_validated_segment() -> None:
    option = BoundedBackupOption(
        speed_mps=0.15,
        maximum_duration_s=3.0,
        mask_validated_distance_m=0.45,
    )
    assert option.maximum_command_distance_m == pytest.approx(0.45)


def test_bounded_backup_rejects_motion_beyond_mask_validated_segment() -> None:
    with pytest.raises(ValueError, match="exceeds the action-mask"):
        BoundedBackupOption(
            speed_mps=0.15,
            maximum_duration_s=3.01,
            mask_validated_distance_m=0.45,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_duration_s": -0.1},
        {"minimum_duration_s": 1.0, "maximum_duration_s": 0.9},
        {"clearance_improvement_m": -0.1},
        {"speed_mps": float("nan")},
    ],
)
def test_bounded_backup_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        BoundedBackupOption(**kwargs)


def test_bounded_subgoal_requires_settle_plus_execution_before_success() -> None:
    option = BoundedSubgoalOption()
    assert option.earliest_completion_s == pytest.approx(3.0)
    assert not option.is_complete(elapsed_s=2.999, planner_succeeded=True)
    assert option.is_complete(elapsed_s=3.0, planner_succeeded=True)


def test_bounded_subgoal_uses_hard_limit_without_planner_success() -> None:
    option = BoundedSubgoalOption()
    assert not option.is_complete(elapsed_s=5.999, planner_succeeded=False)
    assert option.is_complete(elapsed_s=6.0, planner_succeeded=False)
    assert option.maximum_duration_s < option.recovery_limit_s


def test_legacy_bc_interval_can_only_lengthen_subgoal_lifecycle() -> None:
    ordinary = BoundedSubgoalOption(legacy_action_interval_s=0.5)
    extended = BoundedSubgoalOption(
        legacy_action_interval_s=4.0,
        maximum_duration_s=6.0,
    )
    assert ordinary.earliest_completion_s == pytest.approx(3.0)
    assert extended.earliest_completion_s == pytest.approx(4.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"settle_duration_s": -0.1},
        {"minimum_execution_duration_s": 0.0},
        {"legacy_action_interval_s": -0.1},
        {"maximum_duration_s": 2.99},
        {"maximum_duration_s": 8.0},
        {"maximum_duration_s": float("nan")},
    ],
)
def test_bounded_subgoal_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        BoundedSubgoalOption(**kwargs)


@pytest.mark.parametrize("elapsed_s", [-0.1, float("nan"), float("inf")])
def test_bounded_subgoal_rejects_invalid_elapsed_time(elapsed_s: float) -> None:
    with pytest.raises(ValueError):
        BoundedSubgoalOption().is_complete(
            elapsed_s=elapsed_s,
            planner_succeeded=False,
        )


def test_goal_progress_budget_ignores_retreat_and_return_to_high_water_mark() -> None:
    budget = ObservableGoalProgressBudget(reset_progress_m=0.25)
    assert not budget.progress_reached(10.0)
    assert not budget.progress_reached(10.4)
    assert not budget.progress_reached(9.80)
    assert budget.progress_reached(9.75)
    assert budget.reference_distance_m == pytest.approx(10.0)
    # An unconfirmed recovery excursion remains unconsumed and can disappear
    # again if the robot retreats before a successful rejoin.
    assert not budget.progress_reached(10.0)
    assert budget.progress_reached(9.75)
    budget.acknowledge(9.75)
    assert not budget.progress_reached(10.0)
    assert not budget.progress_reached(9.51)
    assert budget.progress_reached(9.50)


@pytest.mark.parametrize("value", [0.0, -0.1, float("nan"), float("inf")])
def test_goal_progress_budget_rejects_invalid_threshold(value: float) -> None:
    with pytest.raises(ValueError):
        ObservableGoalProgressBudget(reset_progress_m=value)


def test_observable_retreat_guard_uses_task_progress_high_water_mark() -> None:
    guard = ObservableNetRetreatGuard(task_heading_rad=0.0, maximum_net_retreat_m=1.4)
    assert guard.backup_permitted(Pose2D(5.0, 12.0, 0.0), backup_distance_m=0.45)
    assert guard.observe(Pose2D(8.0, 12.0, 0.0)) == pytest.approx(0.0)
    assert guard.backup_permitted(Pose2D(7.1, 12.0, 0.0), backup_distance_m=0.45)
    assert not guard.backup_permitted(Pose2D(7.0, 12.0, 0.0), backup_distance_m=0.45)


def test_observable_retreat_guard_allows_backup_that_advances_task_progress() -> None:
    guard = ObservableNetRetreatGuard(task_heading_rad=0.0, maximum_net_retreat_m=1.4)
    guard.observe(Pose2D(8.0, 12.0, 0.0))
    # When facing opposite the task heading, reverse motion increases the task
    # coordinate and therefore cannot violate a net-retreat cap.
    assert guard.backup_permitted(Pose2D(6.5, 12.0, np.pi), backup_distance_m=0.45)


def test_net_retreat_constraint_only_removes_backup() -> None:
    guard = ObservableNetRetreatGuard(
        task_heading_rad=0.0,
        maximum_net_retreat_m=1.4,
        best_task_coordinate_m=8.0,
    )
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_net_retreat(
        mask,
        guard=guard,
        pose=Pose2D(7.0, 12.0, 0.0),
        backup_distance_m=0.45,
    )
    expected = mask.copy()
    expected[BACKUP_ACTION_ID] = False
    assert np.array_equal(constrained, expected)


def test_net_retreat_constraint_blocks_backward_facing_subgoals() -> None:
    guard = ObservableNetRetreatGuard(
        task_heading_rad=0.0,
        maximum_net_retreat_m=1.4,
        best_task_coordinate_m=8.0,
    )
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_net_retreat(
        mask,
        guard=guard,
        pose=Pose2D(7.0, 12.0, np.pi),
        backup_distance_m=0.45,
    )
    assert not bool(constrained[3])
    assert bool(constrained[0])
    assert bool(constrained[6])
    assert constrained[WAIT_ACTION_ID]


def test_retreat_guard_can_bound_optional_emergency_backup_pulse() -> None:
    guard = ObservableNetRetreatGuard(
        task_heading_rad=0.0,
        maximum_net_retreat_m=1.4,
        best_task_coordinate_m=8.0,
    )
    assert guard.backup_permitted(Pose2D(6.8, 12.0, 0.0), backup_distance_m=0.12)
    assert not guard.backup_permitted(Pose2D(6.7, 12.0, 0.0), backup_distance_m=0.12)


def test_stationary_subgoal_retries_require_non_subgoal_escape() -> None:
    guard = ObservableSubgoalStallGuard(retry_budget=3, minimum_displacement_m=0.08)
    pose = Pose2D(2.0, 1.0, 0.0)
    for _ in range(3):
        guard.observe_decision(6, pose)
    assert guard.escape_required
    mask = constrain_stalled_subgoals(np.ones(ACTION_COUNT, dtype=np.bool_), escape_required=True)
    assert not mask[:WAIT_ACTION_ID].any()
    assert mask[WAIT_ACTION_ID]
    assert mask[BACKUP_ACTION_ID]
    guard.observe_decision(BACKUP_ACTION_ID, pose)
    assert not guard.escape_required


def test_subgoal_motion_resets_stationary_retry_count() -> None:
    guard = ObservableSubgoalStallGuard(retry_budget=3, minimum_displacement_m=0.08)
    guard.observe_decision(6, Pose2D(2.0, 1.0, 0.0))
    guard.observe_decision(6, Pose2D(2.1, 1.0, 0.0))
    guard.observe_decision(6, Pose2D(2.1, 1.0, 0.0))
    assert not guard.escape_required


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retry_budget": 0},
        {"minimum_displacement_m": -0.1},
        {"minimum_displacement_m": float("nan")},
    ],
)
def test_subgoal_stall_guard_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ObservableSubgoalStallGuard(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_heading_rad": float("nan")},
        {"task_heading_rad": 0.0, "maximum_net_retreat_m": 0.0},
        {"task_heading_rad": 0.0, "maximum_net_retreat_m": float("inf")},
    ],
)
def test_observable_retreat_guard_rejects_invalid_configuration(
    kwargs: dict[str, float],
) -> None:
    with pytest.raises(ValueError):
        ObservableNetRetreatGuard(**kwargs)


def _continue(**overrides: object) -> bool:
    values: dict[str, object] = {
        "policy_type": "expert",
        "action_id": WAIT_ACTION_ID,
        "action_complete": True,
        "failure_score": 0.0,
        "tau_off": 0.35,
        "option_elapsed_s": 2.0,
        "maximum_option_duration_s": 8.0,
    }
    values.update(overrides)
    return should_continue_recovery_option(**values)  # type: ignore[arg-type]


def test_expert_composes_completed_escape_actions_before_rejoin() -> None:
    assert _continue(action_id=WAIT_ACTION_ID)


def test_expert_continue_action_explicitly_requests_rejoin() -> None:
    assert not _continue(action_id=CONTINUE_ACTION_ID)


def test_observable_failure_keeps_any_policy_in_recovery() -> None:
    assert _continue(policy_type="heuristic", failure_score=0.8)


def test_option_duration_is_a_hard_bound() -> None:
    assert not _continue(option_elapsed_s=8.0)


def test_option_rejects_invalid_probability() -> None:
    with pytest.raises(ValueError, match="lie in"):
        _continue(failure_score=1.1)


def test_collision_latch_masks_rejoin_but_preserves_wait() -> None:
    mask = constrain_rejoin_actions(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        collision_risk=0.75,
        release_threshold=0.35,
    )
    assert not mask[CONTINUE_ACTION_ID]
    assert not mask[REPLAN_ACTION_ID]
    assert mask[WAIT_ACTION_ID]


def test_cleared_collision_latch_restores_rejoin_actions() -> None:
    mask = constrain_rejoin_actions(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        collision_risk=0.0,
        release_threshold=0.35,
    )
    assert mask[CONTINUE_ACTION_ID]
    assert mask[REPLAN_ACTION_ID]


def test_stalled_rejoin_masks_continue_when_planned_escape_exists() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[3] = True
    mask[WAIT_ACTION_ID] = True
    mask[CONTINUE_ACTION_ID] = True
    constrained = constrain_stalled_rejoin(mask, escape_required=True)
    assert constrained[3]
    assert constrained[WAIT_ACTION_ID]
    assert not constrained[CONTINUE_ACTION_ID]


def test_stalled_rejoin_keeps_continue_when_wait_is_only_alternative() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[CONTINUE_ACTION_ID] = True
    constrained = constrain_stalled_rejoin(mask, escape_required=True)
    assert constrained[WAIT_ACTION_ID]
    assert constrained[CONTINUE_ACTION_ID]


def test_wait_budget_forces_available_escape_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[BACKUP_ACTION_ID] = True
    constrained = constrain_stalled_wait(mask, consecutive_waits=3, wait_budget=3)
    assert not constrained[WAIT_ACTION_ID]
    assert constrained[BACKUP_ACTION_ID]


def test_wait_budget_treats_replan_as_an_escape() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True
    constrained = constrain_stalled_wait(mask, consecutive_waits=3, wait_budget=3)
    assert not constrained[WAIT_ACTION_ID]
    assert constrained[REPLAN_ACTION_ID]


def test_replan_budget_forces_an_available_alternative() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True
    constrained = constrain_repeated_replan(mask, replan_count=1, replan_budget=1)
    assert constrained[WAIT_ACTION_ID]
    assert not constrained[REPLAN_ACTION_ID]


def test_replan_remains_when_it_is_the_only_legal_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[REPLAN_ACTION_ID] = True
    constrained = constrain_repeated_replan(mask, replan_count=1, replan_budget=1)
    assert constrained[REPLAN_ACTION_ID]


def test_backup_budget_forces_planning_valid_subgoal() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[3] = True
    mask[BACKUP_ACTION_ID] = True
    mask[WAIT_ACTION_ID] = True
    constrained = constrain_repeated_backup(mask, backup_count=2, backup_budget=2)
    assert constrained[3]
    assert not constrained[BACKUP_ACTION_ID]
    assert constrained[WAIT_ACTION_ID]


def test_backup_remains_when_no_planned_escape_is_safe() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[BACKUP_ACTION_ID] = True
    mask[WAIT_ACTION_ID] = True
    constrained = constrain_repeated_backup(mask, backup_count=2, backup_budget=2)
    assert constrained[BACKUP_ACTION_ID]


def test_wait_remains_valid_before_budget_is_exhausted() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    constrained = constrain_stalled_wait(mask, consecutive_waits=2, wait_budget=3)
    assert constrained[WAIT_ACTION_ID]


def test_wait_remains_valid_when_no_escape_is_safe() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    mask[CONTINUE_ACTION_ID] = True
    constrained = constrain_stalled_wait(mask, consecutive_waits=3, wait_budget=3)
    assert constrained[WAIT_ACTION_ID]


def test_empty_action_mask_fails_closed_to_wait_only() -> None:
    constrained = ensure_safe_wait_fallback(np.zeros(ACTION_COUNT, dtype=np.bool_))
    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[WAIT_ACTION_ID] = True
    assert np.array_equal(constrained, expected)


def test_safe_wait_fallback_does_not_weaken_nonempty_mask() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[REPLAN_ACTION_ID] = True
    constrained = ensure_safe_wait_fallback(mask)
    assert np.array_equal(constrained, mask)
    assert constrained is not mask


def test_composed_budgets_preserve_wait_when_later_bounds_remove_escape() -> None:
    """Regression for the runtime empty-mask failure seen in timeout v10."""
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[3] = True
    mask[WAIT_ACTION_ID] = True
    mask[BACKUP_ACTION_ID] = True
    mask[REPLAN_ACTION_ID] = True

    # Repetition budgets first remove REPLAN and BACKUP because the subgoal
    # still appears executable.  The net-retreat guard then rejects that last
    # translational escape.  WAIT must be evaluated only after those bounds.
    constrained = constrain_repeated_replan(mask, replan_count=1, replan_budget=1)
    constrained = constrain_repeated_backup(constrained, backup_count=2, backup_budget=2)
    constrained = constrain_net_retreat(
        constrained,
        guard=ObservableNetRetreatGuard(
            task_heading_rad=0.0,
            maximum_net_retreat_m=1.4,
            best_task_coordinate_m=8.0,
        ),
        pose=Pose2D(7.0, 12.0, np.pi),
        backup_distance_m=0.45,
    )
    constrained = constrain_stalled_wait(
        constrained,
        consecutive_waits=3,
        wait_budget=3,
    )
    constrained = ensure_safe_wait_fallback(constrained)

    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[WAIT_ACTION_ID] = True
    assert np.array_equal(constrained, expected)


def test_safe_wait_fallback_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError, match="mask must have shape"):
        ensure_safe_wait_fallback(np.zeros(ACTION_COUNT - 1, dtype=np.bool_))


def test_privileged_yield_commits_until_threat_passes_longitudinally() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0, passed_margin_m=0.5)
    approaching = HumanState((1.5, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    assert option.backup_required
    stopped_ahead = HumanState((0.4, 0.0), (0.0, 0.0), 0.35)
    assert option.update(Pose2D(-0.5, 0.0, 0.0), (stopped_ahead,), collision_risk=False)
    assert option.backup_required
    assert option.update(Pose2D(-1.5, 0.0, 0.0), (stopped_ahead,), collision_risk=False)
    assert not option.backup_required
    assert option.require_escape_if_retreat_unavailable(retreat_is_safe=True)
    assert option.escape_reason == "retreat_distance_exhausted"
    passed = HumanState((-1.1, 0.0), (-0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (passed,), collision_risk=False)
    assert not option.escape_required
    assert option.escape_reason is None


def test_privileged_yield_escalates_when_planning_mask_rejects_retreat() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    approaching = HumanState((1.5, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    assert option.backup_required
    assert not option.require_escape_if_retreat_unavailable(retreat_is_safe=True)
    assert option.require_escape_if_retreat_unavailable(retreat_is_safe=False)
    assert option.escape_reason == "retreat_planning_masked"


def test_privileged_yield_escape_state_resets_for_progress_and_new_episode() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0, recurrence_progress_m=0.75)
    approaching = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    assert option.require_escape_if_retreat_unavailable(retreat_is_safe=False)

    farther_ahead = HumanState((3.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(1.0, 0.0, 0.0), (farther_ahead,), collision_risk=True)
    assert not option.escape_required
    assert option.escape_reason is None
    assert option.backup_required

    assert option.require_escape_if_retreat_unavailable(retreat_is_safe=False)
    option.reset()
    assert not option.active
    assert not option.backup_required
    assert not option.escape_required
    assert option.escape_reason is None
    assert option.recurrence_count == 0
    assert option.previous_activation_coordinate_m is None


def test_privileged_yield_ignores_nonapproaching_human() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    receding = HumanState((1.0, 0.0), (0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (receding,), collision_risk=True)


def test_privileged_yield_releases_when_all_threats_reverse_away() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    approaching = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    reversed_route = HumanState((1.5, 0.0), (0.5, 0.0), 0.35)
    assert not option.update(
        Pose2D(-1.0, 0.0, 0.0),
        (reversed_route,),
        collision_risk=False,
    )


def test_privileged_yield_escalates_when_flow_recurs_without_progress() -> None:
    option = PrivilegedYieldOption(
        task_heading_rad=0.0,
        recurrence_progress_m=0.75,
        maximum_recurrences_without_progress=1,
    )
    approaching = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    reversed_route = HumanState((1.5, 0.0), (0.5, 0.0), 0.35)
    assert not option.update(
        Pose2D(-1.0, 0.0, 0.0),
        (reversed_route,),
        collision_risk=False,
    )
    returning = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(-0.8, 0.0, 0.0), (returning,), collision_risk=True)
    assert option.escape_required
    assert option.escape_reason == "recurrent_flow_without_progress"
    assert option.recurrence_count == 1


def test_privileged_yield_escalates_when_passed_human_cycles_back() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0)
    approaching = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    passed = HumanState((-0.6, 0.0), (-0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (passed,), collision_risk=False)
    returning = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.2, 0.0, 0.0), (returning,), collision_risk=True)
    assert option.escape_required


def test_privileged_yield_does_not_escalate_after_robot_clears_window() -> None:
    option = PrivilegedYieldOption(task_heading_rad=0.0, recurrence_progress_m=0.75)
    approaching = HumanState((1.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(0.0, 0.0, 0.0), (approaching,), collision_risk=True)
    passed = HumanState((-0.6, 0.0), (-0.5, 0.0), 0.35)
    assert not option.update(Pose2D(0.0, 0.0, 0.0), (passed,), collision_risk=False)
    next_flow = HumanState((2.0, 0.0), (-0.5, 0.0), 0.35)
    assert option.update(Pose2D(1.0, 0.0, 0.0), (next_flow,), collision_risk=True)
    assert not option.escape_required


def test_recurrent_yield_escape_preserves_only_lateral_and_replan_actions() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    pose = Pose2D(2.0, 1.0, 0.0)
    constrained = constrain_recurrent_yield_escape(
        mask,
        escape_required=True,
        pose=pose,
        path_heading_rad=0.0,
        minimum_lateral_displacement_m=0.25,
    )
    for action in ACTIONS:
        target = action.target_pose(pose)
        expected = (
            target is not None and abs(target.y - pose.y) >= 0.25 - 1.0e-9
        ) or action.action_id == REPLAN_ACTION_ID
        assert bool(constrained[action.action_id]) is expected


def test_recurrent_yield_escape_uses_path_frame_after_robot_turns() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    pose = Pose2D(0.0, 0.0, math.pi / 2.0)
    constrained = constrain_recurrent_yield_escape(
        mask,
        escape_required=True,
        pose=pose,
        path_heading_rad=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    # Facing north on an eastbound path, robot-frame straight actions are
    # genuinely path-lateral and must remain available.
    assert constrained[3]
    assert constrained[10]
    assert constrained[17]
    # Robot-frame +/-90-degree actions point east/west along the task path and
    # must not be misclassified as lateral merely because their angle is nonzero.
    assert not constrained[0]
    assert not constrained[6]
    assert constrained[REPLAN_ACTION_ID]
    assert not constrained[WAIT_ACTION_ID]
    assert not constrained[BACKUP_ACTION_ID]


def test_recurrent_yield_escape_keeps_safe_fallback_without_escape_action() -> None:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[WAIT_ACTION_ID] = True
    assert np.array_equal(
        constrain_recurrent_yield_escape(
            mask,
            escape_required=True,
            pose=Pose2D(0.0, 0.0, 0.0),
            path_heading_rad=0.0,
            minimum_lateral_displacement_m=0.25,
        ),
        mask,
    )


@pytest.mark.parametrize("minimum", [0.0, -0.1, float("inf"), float("nan")])
def test_recurrent_yield_escape_rejects_invalid_lateral_threshold(minimum: float) -> None:
    with pytest.raises(ValueError, match="minimum lateral displacement"):
        constrain_recurrent_yield_escape(
            np.ones(ACTION_COUNT, dtype=np.bool_),
            escape_required=True,
            pose=Pose2D(0.0, 0.0, 0.0),
            path_heading_rad=0.0,
            minimum_lateral_displacement_m=minimum,
        )


def test_temporal_closing_side_low_trace_masks_only_task_right() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    mask[4] = False
    mask[REPLAN_ACTION_ID] = False
    result = constrain_temporal_closing_side(
        mask,
        _temporal_closing_stack(right_beams=10, left_beams=1),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    assert result.right_closing_beams == 10
    assert result.left_closing_beams == 1
    assert result.right_occupied and not result.left_occupied
    assert not result.rotation_gated
    assert not result.mask[[0, 1, 2, 7, 8, 9, 14, 15, 16]].any()
    assert result.mask[[5, 6, 11, 12, 13, 18, 19, 20]].all()
    assert not result.mask[4]
    assert not result.mask[REPLAN_ACTION_ID]
    assert result.mask[WAIT_ACTION_ID] == mask[WAIT_ACTION_ID]
    assert result.mask[BACKUP_ACTION_ID] == mask[BACKUP_ACTION_ID]
    assert not np.any(result.mask & ~mask)


def test_temporal_closing_side_three_beam_boundary_is_conservative() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    three = constrain_temporal_closing_side(
        mask,
        _temporal_closing_stack(right_beams=3, left_beams=0),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    )
    two = constrain_temporal_closing_side(
        mask,
        _temporal_closing_stack(right_beams=2, left_beams=0),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    assert three.right_occupied and not three.left_occupied
    assert not two.right_occupied and not two.left_occupied
    assert np.array_equal(two.mask, mask)


@pytest.mark.parametrize(("right_beams", "left_beams"), [(6, 12), (5, 9)])
def test_temporal_closing_side_medium_and_high_traces_mask_both_sides(
    right_beams: int,
    left_beams: int,
) -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    result = constrain_temporal_closing_side(
        mask,
        _temporal_closing_stack(right_beams=right_beams, left_beams=left_beams),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    assert (result.right_closing_beams, result.left_closing_beams) == (
        right_beams,
        left_beams,
    )
    assert result.right_occupied and result.left_occupied
    lateral_ids = [
        action.action_id
        for action in ACTIONS[:WAIT_ACTION_ID]
        if action.action_id not in {3, 10, 17}
    ]
    assert not result.mask[lateral_ids].any()
    assert result.mask[[3, 10, 17, WAIT_ACTION_ID, BACKUP_ACTION_ID, REPLAN_ACTION_ID]].all()
    assert result.mask[CONTINUE_ACTION_ID]


def test_temporal_closing_side_static_forward_motion_below_delta_is_unchanged() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    stack = _temporal_closing_stack(
        right_beams=12,
        left_beams=12,
        closing_delta_m=0.19,
    )
    result = constrain_temporal_closing_side(
        mask,
        stack,
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    assert (result.right_closing_beams, result.left_closing_beams) == (0, 0)
    assert np.array_equal(result.mask, mask)


def test_temporal_closing_side_rotation_gate_is_closed_at_boundary() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    stack = _temporal_closing_stack(right_beams=5, left_beams=0)
    active = constrain_temporal_closing_side(
        mask,
        stack,
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=-0.20,
        minimum_lateral_displacement_m=0.25,
    )
    gated = constrain_temporal_closing_side(
        mask,
        stack,
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        angular_speed_radps=0.2001,
        minimum_lateral_displacement_m=0.25,
    )

    assert active.right_occupied and not active.rotation_gated
    assert gated.rotation_gated
    assert (gated.right_closing_beams, gated.left_closing_beams) == (0, 0)
    assert np.array_equal(gated.mask, mask)


def test_temporal_closing_side_uses_task_frame_after_robot_turn() -> None:
    pose = Pose2D(0.0, 0.0, math.pi / 2.0)
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    result = constrain_temporal_closing_side(
        mask,
        _temporal_closing_stack(
            right_beams=0,
            left_beams=7,
            pose_yaw_rad=pose.yaw,
            path_heading_rad=0.0,
        ),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=pose,
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    assert result.left_occupied and not result.right_occupied
    assert not result.mask[[3, 10, 17]].any()
    assert result.mask[0] and result.mask[6]


def test_temporal_closing_side_preserves_recurrent_safe_fallback() -> None:
    pose = Pose2D(0.0, 0.0, 0.0)
    high_risk_mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    high_risk_mask[REPLAN_ACTION_ID] = False
    directional = constrain_directional_yield_motion(
        high_risk_mask,
        pose=pose,
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    closing = constrain_temporal_closing_side(
        directional,
        _temporal_closing_stack(right_beams=5, left_beams=9),
        angle_min_rad=-math.pi,
        angle_max_rad=math.pi,
        pose=pose,
        path_heading_rad=0.0,
        angular_speed_radps=0.0,
        minimum_lateral_displacement_m=0.25,
    ).mask
    recurrent = constrain_recurrent_yield_escape(
        closing,
        escape_required=True,
        pose=pose,
        path_heading_rad=0.0,
        minimum_lateral_displacement_m=0.25,
    )

    expected = np.zeros(ACTION_COUNT, dtype=np.bool_)
    expected[[WAIT_ACTION_ID, BACKUP_ACTION_ID]] = True
    assert np.array_equal(closing, expected)
    assert np.array_equal(recurrent, expected)


@pytest.mark.parametrize("shape", [(180,), (4, 180), (5, 179)])
def test_temporal_closing_side_rejects_invalid_stack_shape(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="lidar stack"):
        constrain_temporal_closing_side(
            np.ones(ACTION_COUNT, dtype=np.bool_),
            np.ones(shape),
            angle_min_rad=-math.pi,
            angle_max_rad=math.pi,
            pose=Pose2D(0.0, 0.0, 0.0),
            path_heading_rad=0.0,
            angular_speed_radps=0.0,
            minimum_lateral_displacement_m=0.25,
        )


@pytest.mark.parametrize(
    ("angle_min", "angle_max", "pose", "path_heading", "angular_speed"),
    [
        (0.0, 0.0, Pose2D(0.0, 0.0, 0.0), 0.0, 0.0),
        (float("nan"), 1.0, Pose2D(0.0, 0.0, 0.0), 0.0, 0.0),
        (-1.0, 1.0, Pose2D(float("nan"), 0.0, 0.0), 0.0, 0.0),
        (-1.0, 1.0, Pose2D(0.0, 0.0, 0.0), float("inf"), 0.0),
        (-1.0, 1.0, Pose2D(0.0, 0.0, 0.0), 0.0, float("nan")),
    ],
)
def test_temporal_closing_side_rejects_invalid_geometry(
    angle_min: float,
    angle_max: float,
    pose: Pose2D,
    path_heading: float,
    angular_speed: float,
) -> None:
    with pytest.raises(ValueError, match=r"scan geometry|angle_max"):
        constrain_temporal_closing_side(
            np.ones(ACTION_COUNT, dtype=np.bool_),
            np.ones((5, 180)),
            angle_min_rad=angle_min,
            angle_max_rad=angle_max,
            pose=pose,
            path_heading_rad=path_heading,
            angular_speed_radps=angular_speed,
            minimum_lateral_displacement_m=0.25,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sector_min_degrees": -1.0},
        {"sector_min_degrees": 60.0, "sector_max_degrees": 5.0},
        {"sector_max_degrees": 91.0},
        {"closing_delta_m": 0.0},
        {"maximum_current_range_m": -1.0},
        {"minimum_closing_beams": 0},
        {"minimum_closing_beams": 1.5},
        {"maximum_angular_speed_radps": -0.1},
    ],
)
def test_temporal_closing_side_rejects_invalid_config(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        TemporalClosingSideConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("initial_right", "initial_left", "follow_right", "follow_left"),
    [(11, 11, 2, 2), (5, 8, 2, 1)],
)
def test_closing_side_latch_retains_both_v3_trace_sides_after_backup(
    initial_right: int,
    initial_left: int,
    follow_right: int,
    follow_left: int,
) -> None:
    pose = Pose2D(0.0, 0.0, 0.0)
    directional = constrain_directional_yield_motion(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        pose=pose,
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    latch = ObservableClosingSideLatch()
    initial, initial_mask = _apply_closing_side_latch(
        latch,
        directional,
        pose=pose,
        path_heading_rad=0.0,
        right_beams=initial_right,
        left_beams=initial_left,
    )
    follow, follow_mask = _apply_closing_side_latch(
        latch,
        directional,
        pose=pose,
        path_heading_rad=0.0,
        right_beams=follow_right,
        left_beams=follow_left,
    )

    assert initial.right_occupied and initial.left_occupied
    assert not follow.right_occupied and not follow.left_occupied
    assert latch.right_occupied and latch.left_occupied
    safe_fallback = np.zeros(ACTION_COUNT, dtype=np.bool_)
    safe_fallback[[WAIT_ACTION_ID, BACKUP_ACTION_ID, REPLAN_ACTION_ID]] = True
    assert np.array_equal(initial_mask, safe_fallback)
    assert np.array_equal(follow_mask, safe_fallback)


def test_closing_side_latch_retains_unilateral_low_trace_without_masking_open_side() -> None:
    pose = Pose2D(0.0, 0.0, 0.0)
    directional = constrain_directional_yield_motion(
        np.ones(ACTION_COUNT, dtype=np.bool_),
        pose=pose,
        path_heading_rad=0.0,
        backup_distance_m=0.45,
    )
    latch = ObservableClosingSideLatch()
    initial, initial_mask = _apply_closing_side_latch(
        latch,
        directional,
        pose=pose,
        path_heading_rad=0.0,
        right_beams=9,
        left_beams=0,
    )
    follow, follow_mask = _apply_closing_side_latch(
        latch,
        directional,
        pose=pose,
        path_heading_rad=0.0,
        right_beams=0,
        left_beams=0,
    )

    assert initial.right_occupied and not initial.left_occupied
    assert not follow.right_occupied and not follow.left_occupied
    assert latch.right_occupied and not latch.left_occupied
    assert not initial_mask[0] and initial_mask[6]
    assert not follow_mask[0] and follow_mask[6]


def test_closing_side_latch_unions_new_reliable_side_evidence() -> None:
    latch = ObservableClosingSideLatch()
    assert latch.update(
        yield_active=True,
        right_occupied=True,
        left_occupied=False,
        rotation_gated=False,
    ) == (True, False)
    assert latch.update(
        yield_active=True,
        right_occupied=False,
        left_occupied=True,
        rotation_gated=False,
    ) == (True, True)


def test_closing_side_latch_rotation_gate_neither_sets_nor_clears() -> None:
    latch = ObservableClosingSideLatch(right_occupied=True)
    assert latch.update(
        yield_active=True,
        right_occupied=False,
        left_occupied=True,
        rotation_gated=True,
    ) == (True, False)
    assert latch.active


def test_closing_side_latch_survives_recovery_lifecycle_while_parent_active() -> None:
    latch = ObservableClosingSideLatch(right_occupied=True, left_occupied=True)
    observations = {
        phase: latch.update(
            yield_active=True,
            right_occupied=False,
            left_occupied=False,
            rotation_gated=False,
        )
        for phase in ("BACKUP", "EMERGENCY_STOP", "RECOVERY")
    }
    assert observations == {
        "BACKUP": (True, True),
        "EMERGENCY_STOP": (True, True),
        "RECOVERY": (True, True),
    }


def test_closing_side_latch_releases_with_parent_directional_clearance() -> None:
    parent = ObservableDirectionalYieldLatch(release_frames=3)
    side = ObservableClosingSideLatch()
    active = parent.update(collision_risk=0.8, forward_clearance_m=0.5, observation_id=1)
    assert side.update(
        yield_active=active,
        right_occupied=True,
        left_occupied=True,
        rotation_gated=False,
    ) == (True, True)

    for observation_id in (2, 3):
        active = parent.update(
            collision_risk=0.0,
            forward_clearance_m=2.0,
            observation_id=observation_id,
        )
        assert active
        assert side.update(
            yield_active=active,
            right_occupied=False,
            left_occupied=False,
            rotation_gated=False,
        ) == (True, True)
    # A duplicate scan cannot advance the parent's release evidence.
    assert parent.update(collision_risk=0.0, forward_clearance_m=2.0, observation_id=3)
    assert side.active
    active = parent.update(collision_risk=0.0, forward_clearance_m=2.0, observation_id=4)
    assert not active
    assert side.update(
        yield_active=active,
        right_occupied=False,
        left_occupied=False,
        rotation_gated=False,
    ) == (False, False)
    assert not side.active


def test_task_lateral_side_constraint_never_unmasks_or_changes_special_actions() -> None:
    mask = np.ones(ACTION_COUNT, dtype=np.bool_)
    mask[[4, REPLAN_ACTION_ID, CONTINUE_ACTION_ID]] = False
    constrained = constrain_task_lateral_sides(
        mask,
        pose=Pose2D(0.0, 0.0, 0.0),
        path_heading_rad=0.0,
        minimum_lateral_displacement_m=0.25,
        right_occupied=True,
        left_occupied=True,
    )

    assert not np.any(constrained & ~mask)
    assert constrained[WAIT_ACTION_ID] == mask[WAIT_ACTION_ID]
    assert constrained[BACKUP_ACTION_ID] == mask[BACKUP_ACTION_ID]
    assert constrained[REPLAN_ACTION_ID] == mask[REPLAN_ACTION_ID]
    assert constrained[CONTINUE_ACTION_ID] == mask[CONTINUE_ACTION_ID]
