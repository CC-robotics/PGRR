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
