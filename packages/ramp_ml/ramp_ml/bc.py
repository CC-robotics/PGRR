"""Behavior-cloning training and evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch.utils.data import DataLoader

from ramp_ml.losses import margin_weighted_cross_entropy
from ramp_ml.recovery_policy import RecoveryPolicyNetwork


@dataclass(frozen=True)
class BCMetrics:
    loss: float
    top1: float
    top3: float
    invalid_rate: float
    expert_cost_regret: float


def run_epoch(
    model: RecoveryPolicyNetwork,
    loader: DataLoader[dict[str, torch.Tensor]],
    *,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
    margin_lambda: float,
) -> BCMetrics:
    training = optimizer is not None
    model.train(training)
    total_loss = total = correct1 = correct3 = invalid = 0.0
    regret = 0.0
    for batch in loader:
        lidar = batch["lidar"].to(device)
        state = batch["state"].to(device)
        mask = batch["mask"].to(device)
        action = batch["action"].to(device)
        margin = batch["margin"].to(device)
        costs = batch["costs"].to(device)
        logits = model(lidar, state, mask)
        loss = margin_weighted_cross_entropy(logits, action, margin, margin_lambda=margin_lambda)
        if optimizer is not None:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()  # type: ignore[no-untyped-call]
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        predicted = logits.argmax(dim=-1)
        count = float(len(action))
        total += count
        total_loss += float(loss.detach()) * count
        correct1 += float((predicted == action).sum())
        correct3 += float((logits.topk(k=3, dim=-1).indices == action[:, None]).any(dim=-1).sum())
        invalid += float((~mask.gather(1, predicted[:, None]).squeeze(1)).sum())
        selected_cost = costs.gather(1, predicted[:, None]).squeeze(1)
        expert_cost = costs.gather(1, action[:, None]).squeeze(1)
        regret += float((selected_cost - expert_cost).clamp(min=0.0).sum())
    if total == 0:
        raise ValueError("empty data loader")
    return BCMetrics(
        total_loss / total,
        correct1 / total,
        correct3 / total,
        invalid / total,
        regret / total,
    )
