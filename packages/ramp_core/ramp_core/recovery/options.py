"""Temporal composition rules for bounded recovery options."""

from __future__ import annotations

from ramp_core.action_space import CONTINUE_ACTION_ID, REPLAN_ACTION_ID


def should_continue_recovery_option(
    *,
    policy_type: str,
    action_id: int,
    action_complete: bool,
    failure_score: float,
    tau_off: float,
    option_elapsed_s: float,
    maximum_option_duration_s: float,
) -> bool:
    """Keep replanning within RECOVERY until an expert explicitly rejoins."""
    if not 0.0 <= failure_score <= 1.0 or not 0.0 <= tau_off <= 1.0:
        raise ValueError("failure score and tau_off must lie in [0, 1]")
    if option_elapsed_s < 0.0 or maximum_option_duration_s < 0.0:
        raise ValueError("option durations must be non-negative")
    if not action_complete or option_elapsed_s >= maximum_option_duration_s:
        return False
    if failure_score >= tau_off:
        return True
    return policy_type == "expert" and action_id not in {
        CONTINUE_ACTION_ID,
        REPLAN_ACTION_ID,
    }
