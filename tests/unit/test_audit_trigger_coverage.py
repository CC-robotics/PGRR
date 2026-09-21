from scripts.student.audit_trigger_coverage import audit_rows


def _row(score=0.0, state=0, robot=(0.0, 0.0), human=(5.0, 0.0)):
    return {
        "failure_score": score,
        "failure_prediction": [score, 0.0, 0.0, 0.0],
        "recovery_state": state,
        "robot_pose": robot,
        "privileged": {"human_positions": [human]},
        "nearest_obstacle_distance": 2.0,
        "distance_to_goal": 5.0,
    }


def test_triggered_episode_is_reported():
    result = audit_rows([_row(0.7, 2)], tau_on=0.65, privileged_close_m=0.9)
    assert result["diagnosis"] == "selector_recovery_triggered"
    assert result["threshold_crossing_rows"] == 1


def test_privileged_close_without_trigger_is_diagnostic_not_policy_input():
    result = audit_rows([_row(human=(0.5, 0.0))], tau_on=0.65, privileged_close_m=0.9)
    assert result["diagnosis"] == "privileged_close_without_threshold_crossing"
    assert result["min_privileged_robot_human_distance_m"] == 0.5


def test_no_signal_is_distinguished_from_close_proxy():
    result = audit_rows([_row(), _row(robot=(1.0, 0.0))], tau_on=0.65, privileged_close_m=0.9)
    assert result["diagnosis"] == "no_recorded_failure_signal"
    assert result["robot_path_length_m"] == 1.0


def test_emergency_only_is_not_mistaken_for_selector_recovery():
    result = audit_rows([_row(1.0, 4)], tau_on=0.65, privileged_close_m=0.9)
    assert result["diagnosis"] == "emergency_stop_only"
    assert result["recovery_triggered"] is True
    assert result["selector_recovery_active"] is False
