"""Behavior-cloning training and evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch.utils.data import DataLoader

from ramp_ml.losses import cost_sensitive_behavior_cloning, margin_weighted_cross_entropy
from ramp_ml.recovery_policy import RecoveryPolicyNetwork


@dataclass(frozen=True)
class BCMetrics:
    loss: float
    top1: float
    top3: float
    invalid_rate: float
    expert_cost_regret: float
    near_optimal_rate: float
    catastrophic_action_rate: float


def run_epoch(
    model: RecoveryPolicyNetwork,
    loader: DataLoader[dict[str, torch.Tensor]],
    *,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
    margin_lambda: float,
    cost_regret_lambda: float = 0.0,
) -> BCMetrics:
    training = optimizer is not None
    model.train(training)
    total_loss = total = correct1 = correct3 = invalid = 0.0
    near_optimal = catastrophic = 0.0
    regret = 0.0
    for batch in loader:
        lidar = batch["lidar"].to(device)
        state = batch["state"].to(device)
        mask = batch["mask"].to(device)
        action = batch["action"].to(device)
        margin = batch["margin"].to(device)
        costs = batch["costs"].to(device)
        logits = model(lidar, state, mask)
        if cost_regret_lambda > 0.0:
            loss = cost_sensitive_behavior_cloning(
                logits,
                action,
                costs,
                mask,
                regret_lambda=cost_regret_lambda,
            )
        else:
            loss = margin_weighted_cross_entropy(
                logits, action, margin, margin_lambda=margin_lambda
            )
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
        sample_regret = (selected_cost - expert_cost).clamp(min=0.0)
        regret += float(sample_regret.sum())
        near_optimal += float((sample_regret <= 0.1).sum())
        catastrophic += float(((selected_cost >= 1.0e5) & (expert_cost < 1.0e5)).sum())
    if total == 0:
        raise ValueError("empty data loader")
    return BCMetrics(
        total_loss / total,
        correct1 / total,
        correct3 / total,
        invalid / total,
        regret / total,
        near_optimal / total,
        catastrophic / total,
    )
