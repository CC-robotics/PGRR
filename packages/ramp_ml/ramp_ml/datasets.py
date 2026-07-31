"""HDF5 recovery dataset with on-demand temporal LiDAR stacking."""

from __future__ import annotations

from pathlib import Path

import h5py  # type: ignore[import-untyped]
import numpy as np
import torch
from torch.utils.data import Dataset


class RecoveryHDF5Dataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(self, path: str | Path, lidar_stack: int = 5, lidar_max_m: float = 6.0) -> None:
        if lidar_stack <= 0 or lidar_max_m <= 0.0:
            raise ValueError("lidar stack and range must be positive")
        self.path = Path(path)
        self.lidar_stack = lidar_stack
        self.lidar_max_m = lidar_max_m
        with h5py.File(self.path, "r") as handle:
            self.sample_index = handle["sample_index"][:].astype(np.int64)
            self.observations = {
                name: dataset[:] for name, dataset in handle["observations"].items()
            }
            self.actions = handle["labels/expert_action"][:].astype(np.int64)
            self.margins = handle["labels/expert_margin"][:].astype(np.float32)
            self.masks = handle["labels/action_mask"][:].astype(np.bool_)
            self.costs = handle["labels/expert_costs"][:].astype(np.float32)
        if not (len(self.sample_index) == len(self.actions) == len(self.margins)):
            raise ValueError("sample and label lengths differ")

    def __len__(self) -> int:
        return len(self.sample_index)

    def __getitem__(self, item: int) -> dict[str, torch.Tensor]:
        index = int(self.sample_index[item])
        start = max(0, index - self.lidar_stack + 1)
        scan = self.observations["lidar"][start : index + 1]
        if len(scan) < self.lidar_stack:
            scan = np.concatenate(
                [np.repeat(scan[:1], self.lidar_stack - len(scan), axis=0), scan], axis=0
            )
        planner = np.zeros(7, dtype=np.float32)
        status = int(self.observations["planner_status"][index])
        if 0 <= status < len(planner):
            planner[status] = 1.0
        state = np.concatenate(
            [
                self.observations["goal_polar"][index],
                self.observations["path_waypoints"][index].reshape(-1),
                self.observations["robot_velocity"][index],
                self.observations["base_action"][index],
                self.observations["progress_history"][index],
                self.observations["angular_velocity_history"][index],
                planner,
                self.observations["failure_prediction"][index],
            ]
        ).astype(np.float32)
        return {
            "lidar": torch.from_numpy(np.clip(scan, 0.0, self.lidar_max_m) / self.lidar_max_m),
            "state": torch.from_numpy(state),
            "action": torch.tensor(self.actions[item], dtype=torch.long),
            "margin": torch.tensor(self.margins[item], dtype=torch.float32),
            "mask": torch.from_numpy(self.masks[item]),
            "costs": torch.from_numpy(self.costs[item]),
        }
