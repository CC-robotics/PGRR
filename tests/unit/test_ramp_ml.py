from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
import torch
from ramp_ml.datasets import RecoveryHDF5Dataset
from ramp_ml.losses import margin_weighted_cross_entropy
from ramp_ml.recovery_policy import RecoveryPolicyNetwork, apply_action_mask


def _dataset(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.create_dataset("sample_index", data=[0, 5])
        observations = handle.create_group("observations")
        observations.create_dataset("lidar", data=np.ones((6, 180), dtype=np.float32))
        observations.create_dataset("goal_polar", data=np.zeros((6, 2), dtype=np.float32))
        observations.create_dataset("path_waypoints", data=np.zeros((6, 8, 2), dtype=np.float32))
        for name in ("robot_velocity", "base_action"):
            observations.create_dataset(name, data=np.zeros((6, 2), dtype=np.float32))
        for name in ("progress_history", "angular_velocity_history"):
            observations.create_dataset(name, data=np.zeros((6, 10), dtype=np.float32))
        observations.create_dataset("planner_status", data=np.zeros(6, dtype=np.int8))
        observations.create_dataset("failure_prediction", data=np.zeros((6, 4), dtype=np.float32))
        labels = handle.create_group("labels")
        labels.create_dataset("expert_action", data=[0, 1])
        labels.create_dataset("expert_margin", data=[0.1, 1.0])
        labels.create_dataset("action_mask", data=np.ones((2, 25), dtype=np.bool_))
        labels.create_dataset("expert_costs", data=np.zeros((2, 25), dtype=np.float32))


def test_hdf5_dataset_stacks_and_pads_lidar(tmp_path: Path) -> None:
    path = tmp_path / "data.h5"
    _dataset(path)
    dataset = RecoveryHDF5Dataset(path)
    assert dataset[0]["lidar"].shape == (5, 180)
    assert dataset[1]["state"].shape == (53,)


def test_masked_policy_never_selects_illegal_action() -> None:
    model = RecoveryPolicyNetwork()
    mask = torch.zeros((2, 25), dtype=torch.bool)
    mask[:, 7] = True
    logits = model(torch.ones(2, 5, 180), torch.zeros(2, 53), mask)
    assert logits.argmax(dim=-1).tolist() == [7, 7]
    with pytest.raises(ValueError, match="legal"):
        apply_action_mask(torch.zeros(1, 25), torch.zeros(1, 25, dtype=torch.bool))


def test_margin_weighting_increases_high_margin_penalty() -> None:
    logits = torch.zeros((2, 25))
    actions = torch.tensor([0, 0])
    low = margin_weighted_cross_entropy(logits, actions, torch.tensor([0.1, 0.1]))
    mixed = margin_weighted_cross_entropy(logits, actions, torch.tensor([0.1, 1.0]))
    assert mixed > low
