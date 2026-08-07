"""Imitation losses."""

from __future__ import annotations

import torch
from torch.nn import functional as functional


def margin_weighted_cross_entropy(
    logits: torch.Tensor,
    actions: torch.Tensor,
    margins: torch.Tensor,
    *,
    margin_lambda: float = 1.0,
    margin_clip: float = 3.0,
) -> torch.Tensor:
    if margin_lambda < 0.0 or margin_clip <= 0.0:
        raise ValueError("margin settings are invalid")
    normalized = margins / torch.clamp(margins.median(), min=1.0e-3)
    weights = 1.0 + margin_lambda * torch.clamp(normalized, 0.0, margin_clip)
    return (weights * functional.cross_entropy(logits, actions, reduction="none")).mean()


def cost_sensitive_behavior_cloning(
    logits: torch.Tensor,
    actions: torch.Tensor,
    costs: torch.Tensor,
    action_mask: torch.Tensor,
    *,
    regret_lambda: float = 1.0,
    regret_clip: float = 10.0,
) -> torch.Tensor:
    """Combine hard expert labels with differentiable full-cost regret.

    The rollout expert already evaluates all 25 actions. Distilling only its
    argmin discards whether a mistake is nearly equivalent or catastrophic.
    This objective preserves cross-entropy while penalizing probability mass
    in proportion to clipped, scale-normalized expert regret.
    """
    if regret_lambda < 0.0 or regret_clip <= 0.0:
        raise ValueError("cost-sensitive loss settings are invalid")
    if logits.shape != costs.shape or logits.shape != action_mask.shape:
        raise ValueError("logits, costs, and action mask shapes must match")
    expert_cost = costs.gather(1, actions[:, None]).squeeze(1)
    regret = (costs - expert_cost[:, None]).clamp(min=0.0)
    normalized = regret / (1.0 + expert_cost.abs())[:, None]
    normalized = torch.clamp(normalized, 0.0, regret_clip)
    normalized = torch.where(action_mask, normalized, torch.zeros_like(normalized))
    expected_regret = (functional.softmax(logits, dim=-1) * normalized).sum(dim=-1).mean()
    return functional.cross_entropy(logits, actions) + regret_lambda * expected_regret
