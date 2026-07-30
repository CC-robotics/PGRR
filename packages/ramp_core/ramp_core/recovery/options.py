"""Temporal composition rules for bounded recovery options."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from ramp_core.action_space import ACTION_COUNT, CONTINUE_ACTION_ID, REPLAN_ACTION_ID


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


def constrain_rejoin_actions(
    mask: npt.NDArray[np.bool_],
    *,
    collision_risk: float,
    release_threshold: float,
) -> npt.NDArray[np.bool_]:
    """Disable task-goal rejoin actions while collision risk remains latched."""
    constrained = np.asarray(mask, dtype=np.bool_).copy()
    if constrained.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    if not 0.0 <= collision_risk <= 1.0 or not 0.0 <= release_threshold <= 1.0:
        raise ValueError("collision risk and release threshold must lie in [0, 1]")
    if collision_risk >= release_threshold:
        constrained[CONTINUE_ACTION_ID] = False
        constrained[REPLAN_ACTION_ID] = False
    return constrained
