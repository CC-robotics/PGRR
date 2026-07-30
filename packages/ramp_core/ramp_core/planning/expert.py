"""Privileged short-horizon expert over the fixed recovery action space."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ramp_core.action_space import ACTION_COUNT, ACTIONS, RecoveryActionKind
from ramp_core.observations import PrivilegedState
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.costs import ExpertCostWeights, RolloutCostTerms
from ramp_core.planning.rollout import RolloutConfig, RolloutResult, rollout_action


@dataclass(frozen=True, slots=True)
class ExpertLabel:
    action_id: int
    action_costs: npt.NDArray[np.float32]
    valid_mask: npt.NDArray[np.bool_]
    best_cost: float
    second_best_cost: float
    margin: float
    predicted_success: bool

    def __post_init__(self) -> None:
        costs = np.asarray(self.action_costs, dtype=np.float32)
        mask = np.asarray(self.valid_mask, dtype=np.bool_)
        if costs.shape != (ACTION_COUNT,) or mask.shape != (ACTION_COUNT,):
            raise ValueError("expert arrays must match the fixed action count")
        if not bool(mask[self.action_id]) or not math.isfinite(float(costs[self.action_id])):
            raise ValueError("expert action must be valid and finite")
        costs.setflags(write=False)
        mask.setflags(write=False)
        object.__setattr__(self, "action_costs", costs)
        object.__setattr__(self, "valid_mask", mask)


class PlanningRecoveryExpert:
    def __init__(
        self,
        grid: OccupancyGrid,
        *,
        rollout_config: RolloutConfig | None = None,
        cost_weights: ExpertCostWeights | None = None,
    ) -> None:
        self.grid = grid
        self.rollout_config = rollout_config if rollout_config is not None else RolloutConfig()
        self.cost_weights = cost_weights if cost_weights is not None else ExpertCostWeights()

    def _cost(
        self,
        action_id: int,
        rollout: RolloutResult,
        previous_side: int,
        repeated_waits: int,
    ) -> float:
        action = ACTIONS[action_id]
        side = 0
        if action.kind is RecoveryActionKind.SUBGOAL:
            assert action.angle_degrees is not None
            side = (action.angle_degrees > 0) - (action.angle_degrees < 0)
        switch = float(previous_side != 0 and side != 0 and side != previous_side)
        terms = RolloutCostTerms(
            collision=float(rollout.collision),
            progress=max(0.0, self.cost_weights.minimum_progress_m - rollout.goal_progress_m),
            social=rollout.social_violation_integral,
            rejoin=rollout.rejoin_distance_m,
            length=rollout.path_length_m,
            smooth=rollout.angular_smoothness,
            time=self.rollout_config.horizon_s,
            switch=switch,
            repeat_wait=float(repeated_waits if action.kind is RecoveryActionKind.WAIT else 0),
        )
        return terms.weighted(self.cost_weights)

    def label(
        self,
        privileged_state: PrivilegedState,
        valid_mask: npt.NDArray[np.bool_],
        *,
        previous_side: int = 0,
        repeated_waits: int = 0,
    ) -> ExpertLabel:
        if repeated_waits < 0:
            raise ValueError("repeated_waits must be non-negative")
        mask = np.asarray(valid_mask, dtype=np.bool_)
        if mask.shape != (ACTION_COUNT,) or not bool(mask.any()):
            raise ValueError("valid_mask must contain at least one of the 25 actions")
        costs = np.full(ACTION_COUNT, np.inf, dtype=np.float32)
        rollouts: dict[int, RolloutResult] = {}
        for action in ACTIONS:
            if not bool(mask[action.action_id]):
                continue
            rollout = rollout_action(
                privileged_state,
                action,
                self.grid,
                config=self.rollout_config,
                personal_space_m=self.cost_weights.personal_space_m,
            )
            rollouts[action.action_id] = rollout
            costs[action.action_id] = self._cost(
                action.action_id,
                rollout,
                previous_side,
                repeated_waits,
            )
        finite = np.flatnonzero(np.isfinite(costs))
        if finite.size == 0:
            raise ValueError("no valid action produced a finite expert rollout")
        ordered = finite[np.argsort(costs[finite], kind="stable")]
        best = int(ordered[0])
        second_cost = float(costs[ordered[1]]) if ordered.size > 1 else float(costs[best])
        best_cost = float(costs[best])
        best_rollout = rollouts[best]
        predicted_success = (
            not best_rollout.collision
            and best_rollout.rejoin_distance_m <= 1.0
            and (
                best_rollout.goal_progress_m >= self.cost_weights.minimum_progress_m
                or (
                    ACTIONS[best].kind is RecoveryActionKind.WAIT
                    and best_rollout.minimum_human_distance_m >= self.cost_weights.personal_space_m
                )
            )
        )
        return ExpertLabel(
            action_id=best,
            action_costs=costs,
            valid_mask=mask.copy(),
            best_cost=best_cost,
            second_best_cost=second_cost,
            margin=max(0.0, second_cost - best_cost),
            predicted_success=predicted_success,
        )
