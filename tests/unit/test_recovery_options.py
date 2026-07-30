from __future__ import annotations

import pytest
from ramp_core.action_space import CONTINUE_ACTION_ID, WAIT_ACTION_ID
from ramp_core.recovery.options import should_continue_recovery_option


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
