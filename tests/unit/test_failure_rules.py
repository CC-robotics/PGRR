from __future__ import annotations

import math

import pytest
from ramp_core.failure.metrics import angular_sign_changes
from ramp_core.failure.rules import RuleFailureConfig, RuleFailureDetector, TimedNavigationSample
from ramp_core.types import PlannerStatus


def _sample(
    timestamp: float,
    *,
    x: float = 0.0,
    goal_distance: float = 5.0,
    linear: float = 0.0,
    angular: float = 0.0,
    base_linear: float = 0.2,
    lidar: float = 3.0,
    forward_lidar: float | None = None,
    collision_lidar: float | None = None,
    nearest_bearing: float | None = None,
    collision_bearing: float | None = None,
    status: PlannerStatus = PlannerStatus.ACTIVE,
    goal_reached: bool = False,
) -> TimedNavigationSample:
    return TimedNavigationSample(
        timestamp=timestamp,
        position=(x, 0.0),
        goal_distance=goal_distance,
        linear_velocity=linear,
        angular_velocity=angular,
        base_linear_command=base_linear,
        base_angular_command=angular,
        nearest_lidar_distance=lidar,
        forward_lidar_distance=forward_lidar,
        collision_lidar_distance=collision_lidar,
        nearest_lidar_bearing=nearest_bearing,
        collision_lidar_bearing=collision_bearing,
        planner_status=status,
        goal_reached=goal_reached,
    )


def test_normal_straight_motion_does_not_trigger_failure() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(9):
        timestamp = index * 0.5
        prediction = detector.update(
            _sample(
                timestamp,
                x=timestamp * 0.2,
                goal_distance=5.0 - timestamp * 0.2,
                linear=0.2,
            )
        )
    assert prediction is not None
    assert prediction.score == 0.0


def test_stationary_at_goal_is_not_freeze() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(7):
        prediction = detector.update(_sample(index * 0.5, goal_distance=0.1, goal_reached=True))
    assert prediction is not None
    assert prediction.freeze == 0.0
    assert prediction.deadlock == 0.0


def test_freeze_requires_full_time_window_boundary() -> None:
    detector = RuleFailureDetector()
    for index in range(6):
        prediction = detector.update(_sample(index * 0.5))
        assert prediction.freeze == 0.0
    prediction = detector.update(_sample(3.0))
    assert prediction.freeze == 1.0


def test_brief_startup_motion_request_is_not_freeze() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(7):
        prediction = detector.update(_sample(index * 0.5, base_linear=0.2 if index >= 5 else 0.0))
    assert prediction is not None
    assert prediction.freeze == 0.0


def test_transient_planner_abort_during_turn_is_not_freeze() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(7):
        prediction = detector.update(
            _sample(
                index * 0.5,
                angular=-0.8,
                base_linear=0.0,
                status=PlannerStatus.ABORTED if index == 2 else PlannerStatus.ACTIVE,
            )
        )
    assert prediction is not None
    assert prediction.freeze == 0.0


def test_sustained_planner_abort_triggers_freeze_without_linear_request() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(7):
        prediction = detector.update(
            _sample(
                index * 0.5,
                base_linear=0.0,
                status=PlannerStatus.ABORTED if index >= 3 else PlannerStatus.ACTIVE,
            )
        )
    assert prediction is not None
    assert prediction.freeze == 1.0


def test_single_turn_is_not_oscillation_and_deadband_removes_noise() -> None:
    assert angular_sign_changes([0.01, -0.01, 0.3, 0.4, 0.2], deadband=0.08) == 0
    detector = RuleFailureDetector()
    prediction = None
    for index in range(9):
        angular = 0.4 if index < 4 else -0.4
        prediction = detector.update(_sample(index * 0.5, angular=angular))
    assert prediction is not None
    assert prediction.oscillation == 0.0


def test_repeated_turn_reversals_with_no_progress_trigger_oscillation() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(9):
        prediction = detector.update(_sample(index * 0.5, angular=0.4 if index % 2 == 0 else -0.4))
    assert prediction is not None
    assert prediction.oscillation == 1.0


def test_short_stop_is_not_deadlock() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(6):
        prediction = detector.update(_sample(index * 0.5, base_linear=0.0, lidar=0.8))
    assert prediction is not None
    assert prediction.deadlock == 0.0


def test_blocked_low_speed_full_window_triggers_deadlock() -> None:
    detector = RuleFailureDetector()
    prediction = None
    for index in range(9):
        prediction = detector.update(_sample(index * 0.5, base_linear=0.0, lidar=0.8))
    assert prediction is not None
    assert prediction.deadlock == 1.0


def test_imminent_collision_uses_speed_dependent_stopping_distance() -> None:
    prediction = RuleFailureDetector().update(_sample(0.0, linear=1.0, lidar=0.4))
    assert prediction.collision_risk == 1.0


def test_closing_obstacle_inside_proximity_window_triggers_early_warning() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            linear=0.2,
            lidar=1.30,
            nearest_bearing=0.0,
            collision_bearing=0.0,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            linear=0.2,
            lidar=1.05,
            nearest_bearing=0.0,
            collision_bearing=0.0,
        )
    )
    assert prediction.collision_risk == pytest.approx(0.75)


def test_planner_abort_is_not_mislabeled_as_collision_risk() -> None:
    prediction = RuleFailureDetector().update(_sample(0.0, lidar=3.0, status=PlannerStatus.ABORTED))
    assert prediction.collision_risk == 0.0


def test_wall_range_change_while_spinning_is_not_collision_trend() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            linear=0.2,
            angular=0.9,
            lidar=1.40,
            nearest_bearing=0.0,
            collision_bearing=0.0,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            linear=0.2,
            angular=0.9,
            lidar=1.20,
            nearest_bearing=0.0,
            collision_bearing=0.0,
        )
    )
    assert prediction.collision_risk == 0.0


def test_fixed_side_wall_is_not_immediate_collision_risk() -> None:
    prediction = RuleFailureDetector().update(
        _sample(0.0, lidar=0.8, forward_lidar=3.0, linear=0.0, angular=0.0)
    )
    assert prediction.collision_risk == 0.0


def test_open_map_omnidirectional_clearance_triggers_dynamic_risk() -> None:
    detector = RuleFailureDetector(
        RuleFailureConfig(collision_omnidirectional_absolute_distance_m=0.70)
    )
    prediction = detector.update(
        _sample(
            0.0,
            lidar=0.69,
            forward_lidar=3.0,
            collision_lidar=3.0,
            linear=0.0,
        )
    )
    assert prediction.collision_risk == 1.0


def test_open_map_omnidirectional_clearance_rejects_negative_threshold() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        RuleFailureConfig(collision_omnidirectional_absolute_distance_m=-0.1)


def test_forward_near_field_risk_triggers_immediately() -> None:
    prediction = RuleFailureDetector().update(
        _sample(0.0, lidar=0.8, forward_lidar=0.8, linear=0.0, angular=0.0)
    )
    assert prediction.collision_risk == 1.0


def test_wide_near_field_risk_catches_obstacle_outside_narrow_front_sector() -> None:
    prediction = RuleFailureDetector().update(
        _sample(
            0.0,
            lidar=0.65,
            forward_lidar=3.0,
            collision_lidar=0.65,
            linear=0.0,
            angular=0.0,
        )
    )
    assert prediction.collision_risk == 1.0


def test_wide_near_field_stops_before_combined_human_radius_overlap() -> None:
    prediction = RuleFailureDetector().update(
        _sample(
            0.0,
            lidar=0.84,
            forward_lidar=3.0,
            collision_lidar=0.84,
            linear=0.26,
            angular=-0.37,
        )
    )
    assert prediction.collision_risk == 1.0


def test_collision_warning_requires_time_and_clearance_before_release() -> None:
    detector = RuleFailureDetector()
    initial = detector.update(_sample(0.0, lidar=0.8, forward_lidar=0.8, collision_lidar=0.8))
    clear_inside_hold = detector.update(
        _sample(1.0, lidar=2.0, forward_lidar=3.0, collision_lidar=2.0)
    )
    close_after_hold = detector.update(
        _sample(2.1, lidar=1.1, forward_lidar=3.0, collision_lidar=1.1)
    )
    released = detector.update(_sample(4.2, lidar=2.0, forward_lidar=3.0, collision_lidar=2.0))
    assert initial.collision_risk == 1.0
    assert close_after_hold.collision_risk == pytest.approx(0.75)
    assert clear_inside_hold.collision_risk == pytest.approx(0.75)
    assert released.collision_risk == 0.0


def test_collision_latch_reset_clears_previous_warning() -> None:
    detector = RuleFailureDetector()
    detector.update(_sample(0.0, lidar=0.8, forward_lidar=0.8, collision_lidar=0.8))
    detector.reset()
    prediction = detector.update(_sample(0.1, lidar=2.0, forward_lidar=3.0, collision_lidar=2.0))
    assert prediction.collision_risk == 0.0


def test_recovery_motion_is_excluded_from_freeze_history() -> None:
    detector = RuleFailureDetector()
    for index in range(7):
        prediction = detector.update(_sample(index * 0.5))
    assert prediction.freeze == 1.0

    for index in range(7, 11):
        prediction = detector.update(
            _sample(index * 0.5),
            motion_rules_enabled=False,
        )
        assert prediction.freeze == 0.0

    for index in range(11, 17):
        prediction = detector.update(_sample(index * 0.5))
        assert prediction.freeze == 0.0
    prediction = detector.update(_sample(8.5))
    assert prediction.freeze == 1.0


def test_recovery_motion_suppression_preserves_collision_detection() -> None:
    prediction = RuleFailureDetector().update(
        _sample(0.0, lidar=0.4, forward_lidar=0.4, collision_lidar=0.4),
        motion_rules_enabled=False,
    )
    assert prediction.collision_risk == 1.0
    assert prediction.freeze == 0.0


def test_collision_release_distance_must_exceed_wide_trigger_distance() -> None:
    with pytest.raises(ValueError, match="release_distance"):
        RuleFailureConfig(
            collision_wide_absolute_distance_m=0.8,
            collision_release_distance_m=0.8,
        )


def test_side_obstacle_closing_on_stationary_robot_triggers_trend() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.30,
            collision_bearing=0.2,
            linear=0.0,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.00,
            collision_bearing=0.2,
            linear=0.0,
        )
    )
    assert prediction.collision_risk == pytest.approx(0.75)


def test_collision_trend_rejects_minimum_return_identity_jump() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.30,
            collision_bearing=-0.30,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.00,
            collision_bearing=0.30,
        )
    )
    assert prediction.collision_risk == 0.0


def test_rotation_compensated_wall_return_drift_does_not_trigger_trend() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.30,
            collision_bearing=-0.50,
            angular=-0.24,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.00,
            collision_bearing=-0.40,
            angular=-0.24,
        )
    )
    assert prediction.collision_risk == 0.0


def test_bearing_consistency_is_circular_across_pi() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.30,
            collision_bearing=math.pi - 0.02,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=1.00,
            collision_bearing=-math.pi + 0.02,
        )
    )
    assert prediction.collision_risk == pytest.approx(0.75)


def test_immediate_collision_threshold_does_not_require_bearing_identity() -> None:
    prediction = RuleFailureDetector().update(
        _sample(
            0.0,
            lidar=3.0,
            forward_lidar=3.0,
            collision_lidar=0.84,
        )
    )
    assert prediction.collision_risk == 1.0


def test_side_wall_range_change_explained_by_robot_motion_is_not_dynamic_risk() -> None:
    detector = RuleFailureDetector()
    detector.update(_sample(0.0, lidar=1.10, forward_lidar=3.0, collision_lidar=1.10, linear=0.2))
    prediction = detector.update(
        _sample(0.5, lidar=1.00, forward_lidar=3.0, collision_lidar=1.00, linear=0.2)
    )
    assert prediction.collision_risk == 0.0


def test_off_axis_obstacle_closing_while_robot_moves_forward_triggers_trend() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=1.60,
            forward_lidar=3.0,
            collision_lidar=3.0,
            nearest_bearing=1.0,
            linear=0.25,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=1.20,
            forward_lidar=3.0,
            collision_lidar=3.0,
            nearest_bearing=1.0,
            linear=0.25,
        )
    )
    assert prediction.collision_risk == pytest.approx(0.75)


def test_off_axis_static_wall_change_explained_by_ego_motion_does_not_trigger() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=1.71,
            forward_lidar=6.0,
            collision_lidar=2.25,
            linear=0.22,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=1.57,
            forward_lidar=6.0,
            collision_lidar=2.17,
            linear=0.22,
        )
    )
    assert prediction.collision_risk == 0.0


def test_off_axis_range_jitter_below_closing_threshold_does_not_trigger() -> None:
    detector = RuleFailureDetector()
    detector.update(_sample(0.0, lidar=1.20, forward_lidar=3.0, collision_lidar=3.0, linear=0.25))
    prediction = detector.update(
        _sample(0.5, lidar=1.16, forward_lidar=3.0, collision_lidar=3.0, linear=0.25)
    )
    assert prediction.collision_risk == 0.0


def test_close_side_obstacle_closing_while_turning_is_not_suppressed() -> None:
    detector = RuleFailureDetector()
    detector.update(
        _sample(
            0.0,
            lidar=1.05,
            forward_lidar=3.0,
            collision_lidar=1.05,
            linear=0.0,
            angular=0.9,
        )
    )
    prediction = detector.update(
        _sample(
            0.5,
            lidar=0.85,
            forward_lidar=3.0,
            collision_lidar=0.85,
            linear=0.0,
            angular=0.9,
        )
    )
    assert prediction.collision_risk == 1.0


def test_history_rejects_nonmonotonic_timestamps() -> None:
    detector = RuleFailureDetector()
    detector.update(_sample(1.0))
    with pytest.raises(ValueError, match="monotonic"):
        detector.update(_sample(0.9))
