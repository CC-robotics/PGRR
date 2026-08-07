"""Regression coverage for bounded recovery-sequence lifecycle semantics."""

from ramp_core.state_machine import (
    RecoveryState,
    RecoveryStateMachine,
    RecoveryStateMachineConfig,
    StateMachineInput,
)


def _machine() -> RecoveryStateMachine:
    return RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_sequence_duration_s=45.0,
        )
    )


def test_restored_goal_with_continued_progress_survives_old_45_second_deadline() -> None:
    machine = _machine()
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(40.0, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    assert (
        machine.update(StateMachineInput(40.5, 0.0, True, original_goal_active=True)).current
        is RecoveryState.NORMAL
    )
    # A subsequent progress observation confirms sustained original-goal
    # navigation and retires the sequence before its old 45 s deadline.
    assert (
        machine.update(StateMachineInput(41.0, 0.0, True, original_goal_active=True)).current
        is RecoveryState.NORMAL
    )
    transition = machine.update(StateMachineInput(46.0, 0.0, True, original_goal_active=True))
    assert transition.current is RecoveryState.NORMAL
    assert transition.reason == "no_transition"


def test_persistent_emergency_stop_without_progress_still_fails_at_45_seconds() -> None:
    machine = _machine()
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(0.1, 1.0, False, emergency_stop=True)).current
        is RecoveryState.EMERGENCY_STOP
    )
    before_deadline = machine.update(StateMachineInput(44.9, 1.0, False, emergency_stop=True))
    assert before_deadline.current is RecoveryState.EMERGENCY_STOP
    at_deadline = machine.update(StateMachineInput(45.0, 1.0, False, emergency_stop=True))
    assert at_deadline.current is RecoveryState.FAILED
    assert at_deadline.reason == "recovery_sequence_timeout"
