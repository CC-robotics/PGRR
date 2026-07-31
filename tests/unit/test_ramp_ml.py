from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
import torch
from ramp_core.observations import RecoveryObservation
from ramp_core.types import FailurePrediction, PlannerStatus
from ramp_ml.datasets import RecoveryHDF5Dataset
from ramp_ml.inference import ONNXRecoveryPolicy, encode_observation
from ramp_ml.losses import cost_sensitive_behavior_cloning, margin_weighted_cross_entropy
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


def test_hdf5_dataset_does_not_stack_across_episode_boundary(tmp_path: Path) -> None:
    path = tmp_path / "data.h5"
    _dataset(path)
    with h5py.File(path, "a") as handle:
        handle["observations/lidar"][:] = np.arange(6, dtype=np.float32)[:, None]
        handle["observations"].create_dataset(
            "episode_start_index", data=np.asarray([0, 0, 0, 0, 0, 5], dtype=np.int32)
        )
    dataset = RecoveryHDF5Dataset(path, lidar_max_m=10.0)
    assert torch.all(dataset[1]["lidar"] == 0.5)


def test_mirror_augmentation_maps_observation_action_mask_and_cost(tmp_path: Path) -> None:
    path = tmp_path / "data.h5"
    _dataset(path)
    with h5py.File(path, "a") as handle:
        handle["observations/goal_polar"][0] = [2.0, 0.4]
        handle["observations/path_waypoints"][0, :, 1] = 0.3
        handle["observations/robot_velocity"][0, 1] = 0.2
        handle["labels/expert_action"][0] = 2
        handle["labels/action_mask"][0] = False
        handle["labels/action_mask"][0, 2] = True
        handle["labels/expert_costs"][0] = np.arange(25)
    dataset = RecoveryHDF5Dataset(path, mirror_augmentation=True)
    mirrored = dataset[len(dataset) // 2]
    assert int(mirrored["action"]) == 4
    assert bool(mirrored["mask"][4])
    assert float(mirrored["state"][1]) == pytest.approx(-0.4)
    assert float(mirrored["state"][3]) == pytest.approx(-0.3)
    assert float(mirrored["state"][19]) == pytest.approx(-0.2)
    assert float(mirrored["costs"][4]) == pytest.approx(2.0)


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


def test_cost_sensitive_loss_penalizes_probability_on_catastrophic_action() -> None:
    actions = torch.tensor([0])
    mask = torch.ones((1, 3), dtype=torch.bool)
    costs = torch.tensor([[0.0, 0.1, 1.0e6]])
    safe_logits = torch.tensor([[4.0, 1.0, -2.0]])
    unsafe_logits = torch.tensor([[1.0, -2.0, 4.0]])
    safe = cost_sensitive_behavior_cloning(safe_logits, actions, costs, mask)
    unsafe = cost_sensitive_behavior_cloning(unsafe_logits, actions, costs, mask)
    assert unsafe > safe


class _Input:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSession:
    def __init__(self) -> None:
        self.feed: dict[str, np.ndarray] = {}

    def get_inputs(self) -> list[_Input]:
        return [_Input("lidar"), _Input("state"), _Input("mask")]

    def run(
        self, output_names: list[str] | None, input_feed: dict[str, np.ndarray]
    ) -> list[np.ndarray]:
        assert output_names is None
        self.feed = input_feed
        logits = np.full((1, 25), -1.0e9, dtype=np.float32)
        logits[0, 7] = 3.0
        return [logits]


def _observation() -> RecoveryObservation:
    return RecoveryObservation(
        lidar=np.full((5, 180), 3.0, dtype=np.float32),
        goal_polar=np.asarray([2.0, 0.2], dtype=np.float32),
        path_waypoints=np.zeros((8, 2), dtype=np.float32),
        robot_velocity=np.asarray([0.2, 0.1], dtype=np.float32),
        base_action=np.asarray([0.3, -0.1], dtype=np.float32),
        progress_history=np.linspace(3.0, 2.0, 10, dtype=np.float32),
        angular_velocity_history=np.zeros(10, dtype=np.float32),
        planner_status=PlannerStatus.ACTIVE,
        failure_prediction=FailurePrediction(0.8, 0.1, 0.0, 0.0),
    )


def test_online_encoder_matches_training_shapes_and_scaling() -> None:
    lidar, state = encode_observation(_observation())
    assert lidar.shape == (5, 180)
    assert state.shape == (53,)
    assert float(lidar[0, 0]) == pytest.approx(0.5)
    assert state[42 + int(PlannerStatus.ACTIVE)] == 1.0
    assert state[-4:].tolist() == pytest.approx([0.8, 0.1, 0.0, 0.0])


def test_onnx_policy_selects_only_legal_action_with_fake_session() -> None:
    session = _FakeSession()
    policy = ONNXRecoveryPolicy("unused.onnx", session=session)
    mask = np.zeros(25, dtype=np.bool_)
    mask[7] = True
    decision = policy.select_action(_observation(), mask)
    assert decision.action_id == 7
    assert decision.confidence == pytest.approx(1.0)
    assert session.feed["lidar"].shape == (1, 5, 180)
    assert session.feed["state"].shape == (1, 53)
    assert session.feed["mask"].shape == (1, 25)
