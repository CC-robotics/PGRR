"""Compact action-masked recovery policy."""

from __future__ import annotations

import torch
from torch import nn


def apply_action_mask(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    tracing = torch.jit.is_tracing()  # type: ignore[attr-defined,no-untyped-call]
    scripting = torch.jit.is_scripting()  # type: ignore[attr-defined]
    if not tracing and not scripting:
        if logits.shape != mask.shape:
            raise ValueError("logits and action mask shapes differ")
        if not bool(torch.all(mask.any(dim=-1))):
            raise ValueError("every sample must contain a legal action")
    return logits.masked_fill(~mask, torch.finfo(logits.dtype).min)


class RecoveryPolicyNetwork(nn.Module):
    def __init__(self, state_dim: int = 53, action_count: int = 25) -> None:
        super().__init__()
        self.lidar_encoder = nn.Sequential(
            nn.Conv1d(5, 16, kernel_size=7, stride=3, padding=3),
            nn.ReLU(),
            nn.Conv1d(16, 32, kernel_size=5, stride=2, padding=2),
            nn.ReLU(),
            nn.AvgPool1d(kernel_size=4, stride=4),
            nn.Flatten(),
            nn.LayerNorm(224),
        )
        self.state_encoder = nn.Sequential(nn.Linear(state_dim, 128), nn.ReLU(), nn.LayerNorm(128))
        self.head = nn.Sequential(nn.Linear(352, 128), nn.ReLU(), nn.Linear(128, action_count))

    def forward(self, lidar: torch.Tensor, state: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        features = torch.cat((self.lidar_encoder(lidar), self.state_encoder(state)), dim=-1)
        return apply_action_mask(self.head(features), mask)
