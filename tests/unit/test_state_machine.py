from ramp_core.state_machine import (
    RecoveryState,
    RecoveryStateMachine,
    RecoveryStateMachineConfig,
    StateMachineInput,
)


def test_hysteresis_enters_and_exits_recovery() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=2,
            frames_off=2,
            cooldown_s=0.0,
            minimum_action_hold_s=0.5,
        )
    )
    machine.update(StateMachineInput(0.0, 0.8, False))
    transition = machine.update(StateMachineInput(0.1, 0.8, False))
    assert transition.current is RecoveryState.RECOVERY
    machine.update(StateMachineInput(0.7, 0.2, True))
    transition = machine.update(StateMachineInput(0.8, 0.2, True))
    assert transition.current is RecoveryState.REJOIN
    transition = machine.update(
        StateMachineInput(
            0.9,
            0.2,
            True,
            meaningful_progress=True,
            original_goal_active=True,
        )
    )
    assert transition.current is RecoveryState.NORMAL
    assert machine.consecutive_recoveries == 0


def test_small_rejoin_progress_does_not_replenish_recovery_budget() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_consecutive_recoveries=2,
        )
    )
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert machine.update(StateMachineInput(0.1, 0.0, True)).current is RecoveryState.REJOIN
    assert (
        machine.update(StateMachineInput(0.2, 0.0, True, original_goal_active=True)).current
        is RecoveryState.NORMAL
    )
    assert machine.consecutive_recoveries == 1
    assert machine.update(StateMachineInput(0.3, 1.0, False)).current is RecoveryState.RECOVERY
    assert machine.update(StateMachineInput(0.4, 0.0, True)).current is RecoveryState.REJOIN
    assert (
        machine.update(StateMachineInput(0.5, 0.0, True, original_goal_active=True)).current
        is RecoveryState.NORMAL
    )
    failed = machine.update(StateMachineInput(0.6, 1.0, False))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_limit"


def test_meaningful_progress_replenishes_recovery_budget_while_normal() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_consecutive_recoveries=1,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    machine.update(StateMachineInput(0.1, 0.0, True))
    machine.update(StateMachineInput(0.2, 0.0, True, original_goal_active=True))
    assert machine.consecutive_recoveries == 1
    transition = machine.update(
        StateMachineInput(
            0.3,
            0.0,
            True,
            meaningful_progress=True,
            original_goal_active=True,
        )
    )
    assert transition.current is RecoveryState.NORMAL
    assert machine.consecutive_recoveries == 0
    assert machine.update(StateMachineInput(0.4, 1.0, False)).current is RecoveryState.RECOVERY


def test_emergency_stop_has_priority() -> None:
    machine = RecoveryStateMachine()
    transition = machine.update(
        StateMachineInput(
            now_s=1.0,
            failure_score=0.0,
            valid_progress=True,
            emergency_stop=True,
        )
    )
    assert transition.current is RecoveryState.EMERGENCY_STOP


def test_emergency_release_with_failure_remains_protective_pending() -> None:
    machine = RecoveryStateMachine()
    machine.update(StateMachineInput(1.0, 0.8, False, emergency_stop=True))
    transition = machine.update(StateMachineInput(1.1, 0.8, False, emergency_stop=False))
    assert transition.current is RecoveryState.PENDING_RECOVERY
    assert transition.reason == "safety_clear_failure_pending"


def test_emergency_interruptions_resume_same_recovery_sequence() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            cooldown_s=0.0,
            maximum_consecutive_recoveries=2,
        )
    )
    assert machine.update(StateMachineInput(0.0, 0.8, False)).current is RecoveryState.RECOVERY
    assert machine.consecutive_recoveries == 1
    for start in (0.1, 0.3, 0.5):
        assert (
            machine.update(StateMachineInput(start, 1.0, False, emergency_stop=True)).current
            is RecoveryState.EMERGENCY_STOP
        )
        resumed = machine.update(StateMachineInput(start + 0.1, 1.0, False, emergency_stop=False))
        assert resumed.current is RecoveryState.RECOVERY
        assert resumed.reason == "safety_clear_resume_recovery"
        assert machine.consecutive_recoveries == 1


def test_single_frame_configuration_enters_recovery_immediately() -> None:
    machine = RecoveryStateMachine(RecoveryStateMachineConfig(frames_on=1, cooldown_s=0.0))
    transition = machine.update(StateMachineInput(1.0, 0.8, False))
    assert transition.current is RecoveryState.RECOVERY
    assert transition.reason == "failure_confirmed"
    assert machine.state_since_s == 1.0


def test_active_long_option_uses_separate_bounded_duration() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_duration_s=1.0,
            maximum_extended_recovery_duration_s=3.0,
        )
    )
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(1.1, 1.0, False, recovery_option_active=True)).current
        is RecoveryState.RECOVERY
    )
    transition = machine.update(StateMachineInput(3.0, 1.0, False, recovery_option_active=True))
    assert transition.current is RecoveryState.REJOIN
    assert transition.reason == "recovery_timeout"


def test_completed_action_waits_for_configured_low_score_hysteresis() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=3,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    for now_s in (0.1, 0.2):
        transition = machine.update(
            StateMachineInput(now_s, 0.0, False, recovery_action_complete=True)
        )
        assert transition.current is RecoveryState.RECOVERY
    transition = machine.update(StateMachineInput(0.3, 0.0, False, recovery_action_complete=True))
    assert transition.current is RecoveryState.REJOIN
    assert transition.reason == "recovery_action_complete"


def test_completed_action_cannot_rejoin_while_failure_persists() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    transition = machine.update(StateMachineInput(0.1, 1.0, False, recovery_action_complete=True))
    assert transition.current is RecoveryState.RECOVERY


def test_threshold_order_is_validated() -> None:
    try:
        RecoveryStateMachineConfig(tau_on=0.3, tau_off=0.4)
    except ValueError:
        return
    raise AssertionError("invalid threshold order was accepted")


def test_terminal_states_are_sticky_even_if_emergency_signal_changes() -> None:
    machine = RecoveryStateMachine()
    machine.update(StateMachineInput(1.0, 0.0, True, goal_reached=True))
    transition = machine.update(StateMachineInput(1.1, 1.0, False, emergency_stop=True))
    assert transition.current is RecoveryState.SUCCEEDED
    assert not transition.changed

    failed = RecoveryStateMachine()
    failed.update(StateMachineInput(1.0, 0.0, False, unrecoverable_failure=True))
    transition = failed.update(StateMachineInput(1.1, 1.0, False, emergency_stop=True))
    assert transition.current is RecoveryState.FAILED
    assert not transition.changed


def test_goal_reached_from_emergency_preserves_terminal_reason() -> None:
    machine = RecoveryStateMachine()
    assert (
        machine.update(StateMachineInput(1.0, 0.0, False, emergency_stop=True)).current
        is RecoveryState.EMERGENCY_STOP
    )
    transition = machine.update(
        StateMachineInput(1.1, 0.0, False, emergency_stop=True, goal_reached=True)
    )
    assert transition.previous is RecoveryState.EMERGENCY_STOP
    assert transition.current is RecoveryState.SUCCEEDED
    assert transition.changed
    assert transition.reason == "goal_reached"


def test_stalled_rejoin_retries_then_respects_recovery_limit() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_rejoin_duration_s=2.0,
            maximum_rejoin_retries_per_sequence=1,
            maximum_consecutive_recoveries=2,
        )
    )
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(0.1, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    retry = machine.update(StateMachineInput(2.1, 0.2, False))
    assert retry.current is RecoveryState.RECOVERY
    assert retry.reason == "rejoin_failure_retry"
    assert machine.consecutive_recoveries == 1
    assert (
        machine.update(StateMachineInput(2.2, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    exhausted = machine.update(StateMachineInput(4.2, 0.2, False))
    assert exhausted.current is RecoveryState.NORMAL
    assert exhausted.reason == "rejoin_retry_exhausted"
    assert machine.update(StateMachineInput(4.3, 0.8, False)).current is RecoveryState.RECOVERY
    assert machine.consecutive_recoveries == 2
    assert (
        machine.update(StateMachineInput(4.4, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    assert machine.update(StateMachineInput(6.4, 0.2, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(6.5, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    assert machine.update(StateMachineInput(8.5, 0.2, False)).current is RecoveryState.NORMAL
    failed = machine.update(StateMachineInput(8.6, 0.8, False))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_limit"


def test_recovery_sequence_timeout_spans_emergency_and_rejoin_cycles() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_sequence_duration_s=2.0,
            maximum_rejoin_duration_s=0.5,
            maximum_rejoin_retries_per_sequence=4,
        )
    )
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(0.1, 1.0, False, emergency_stop=True)).current
        is RecoveryState.EMERGENCY_STOP
    )
    resumed = machine.update(StateMachineInput(0.2, 1.0, False))
    assert resumed.current is RecoveryState.RECOVERY
    assert resumed.reason == "safety_clear_resume_recovery"
    assert (
        machine.update(StateMachineInput(0.3, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    retry = machine.update(StateMachineInput(0.9, 1.0, False))
    assert retry.current is RecoveryState.RECOVERY
    assert retry.reason == "rejoin_failure_retry"
    assert (
        machine.update(StateMachineInput(1.0, 1.0, False, emergency_stop=True)).current
        is RecoveryState.EMERGENCY_STOP
    )
    failed = machine.update(StateMachineInput(2.0, 1.0, False, emergency_stop=True))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_sequence_timeout"


def test_weak_rejoin_progress_does_not_clear_recovery_sequence_timeout() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_sequence_duration_s=1.0,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    machine.update(StateMachineInput(0.1, 0.0, False, recovery_action_complete=True))
    restored = machine.update(StateMachineInput(0.2, 0.0, True, original_goal_active=True))
    assert restored.current is RecoveryState.NORMAL
    assert restored.reason == "original_goal_restored"
    failed = machine.update(StateMachineInput(1.0, 0.0, False))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_sequence_timeout"


def test_meaningful_original_goal_progress_starts_fresh_sequence_budget() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_sequence_duration_s=1.0,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    machine.update(StateMachineInput(0.1, 0.0, False, recovery_action_complete=True))
    restored = machine.update(
        StateMachineInput(
            0.2,
            0.0,
            True,
            meaningful_progress=True,
            original_goal_active=True,
        )
    )
    assert restored.current is RecoveryState.NORMAL
    assert machine.update(StateMachineInput(1.1, 0.0, True)).current is RecoveryState.NORMAL

    assert machine.update(StateMachineInput(1.2, 1.0, False)).current is RecoveryState.RECOVERY
    failed = machine.update(StateMachineInput(2.2, 1.0, False))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_sequence_timeout"


def test_sustained_progress_after_original_goal_rejoin_retires_old_deadline() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_sequence_duration_s=1.0,
        )
    )
    assert machine.update(StateMachineInput(0.0, 1.0, False)).current is RecoveryState.RECOVERY
    assert (
        machine.update(StateMachineInput(0.1, 0.0, False, recovery_action_complete=True)).current
        is RecoveryState.REJOIN
    )
    restored = machine.update(StateMachineInput(0.2, 0.0, True, original_goal_active=True))
    assert restored.current is RecoveryState.NORMAL
    assert restored.reason == "original_goal_restored"

    # A second progress-bearing decision in NORMAL confirms that Nav2 has
    # resumed the original task, even if cumulative progress has not yet
    # crossed the separate 0.25 m meaningful-progress threshold.
    assert (
        machine.update(StateMachineInput(0.7, 0.0, True, original_goal_active=True)).current
        is RecoveryState.NORMAL
    )
    beyond_old_deadline = machine.update(
        StateMachineInput(1.1, 0.0, True, original_goal_active=True)
    )
    assert beyond_old_deadline.current is RecoveryState.NORMAL
    assert beyond_old_deadline.reason == "no_transition"

    # A later failure receives a fresh bounded sequence rather than inheriting
    # the completed sequence's deadline.
    assert machine.update(StateMachineInput(1.2, 1.0, False)).current is RecoveryState.RECOVERY
    failed = machine.update(StateMachineInput(2.2, 1.0, False))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_sequence_timeout"


def test_rejoin_progress_cannot_complete_sequence_before_original_goal_is_active() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            frames_off=1,
            cooldown_s=0.0,
            minimum_action_hold_s=0.0,
            maximum_recovery_sequence_duration_s=1.0,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    machine.update(StateMachineInput(0.1, 0.0, False, recovery_action_complete=True))
    waiting = machine.update(StateMachineInput(0.2, 0.0, True, original_goal_active=False))
    assert waiting.current is RecoveryState.REJOIN
    failed = machine.update(StateMachineInput(1.0, 0.0, True, original_goal_active=False))
    assert failed.current is RecoveryState.FAILED
    assert failed.reason == "recovery_sequence_timeout"


def test_goal_and_unrecoverable_failure_precede_recovery_sequence_timeout() -> None:
    config = RecoveryStateMachineConfig(
        frames_on=1,
        cooldown_s=0.0,
        maximum_recovery_sequence_duration_s=1.0,
    )
    reached = RecoveryStateMachine(config)
    reached.update(StateMachineInput(0.0, 1.0, False))
    transition = reached.update(StateMachineInput(1.0, 1.0, False, goal_reached=True))
    assert transition.current is RecoveryState.SUCCEEDED
    assert transition.reason == "goal_reached"

    unrecoverable = RecoveryStateMachine(config)
    unrecoverable.update(StateMachineInput(0.0, 1.0, False))
    transition = unrecoverable.update(
        StateMachineInput(1.0, 1.0, False, unrecoverable_failure=True)
    )
    assert transition.current is RecoveryState.FAILED
    assert transition.reason == "unrecoverable_failure"


def test_reset_clears_recovery_sequence_timeout() -> None:
    machine = RecoveryStateMachine(
        RecoveryStateMachineConfig(
            frames_on=1,
            cooldown_s=0.0,
            maximum_recovery_sequence_duration_s=1.0,
        )
    )
    machine.update(StateMachineInput(0.0, 1.0, False))
    machine.reset(now_s=10.0)
    transition = machine.update(StateMachineInput(20.0, 0.0, True))
    assert transition.current is RecoveryState.NORMAL
    assert transition.reason == "no_transition"


def test_recovery_sequence_timeout_must_be_finite_and_positive() -> None:
    for value in (0.0, -0.1, float("nan"), float("inf")):
        try:
            RecoveryStateMachineConfig(maximum_recovery_sequence_duration_s=value)
        except ValueError:
            continue
        raise AssertionError(f"invalid recovery sequence duration was accepted: {value}")
