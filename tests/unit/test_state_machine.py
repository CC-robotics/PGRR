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
    transition = machine.update(StateMachineInput(0.9, 0.2, True))
    assert transition.current is RecoveryState.NORMAL
    assert machine.consecutive_recoveries == 0


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


def test_single_frame_configuration_enters_recovery_immediately() -> None:
    machine = RecoveryStateMachine(RecoveryStateMachineConfig(frames_on=1, cooldown_s=0.0))
    transition = machine.update(StateMachineInput(1.0, 0.8, False))
    assert transition.current is RecoveryState.RECOVERY
    assert transition.reason == "failure_confirmed"


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
