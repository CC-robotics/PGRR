"""HDF5 recovery dataset with on-demand temporal LiDAR stacking."""

from __future__ import annotations

from pathlib import Path

import h5py  # type: ignore[import-untyped]
import numpy as np
import torch
from torch.utils.data import Dataset


class RecoveryHDF5Dataset(Dataset[dict[str, torch.Tensor]]):
    _mirror_actions = np.asarray(
        [6, 5, 4, 3, 2, 1, 0, 13, 12, 11, 10, 9, 8, 7, 20, 19, 18, 17, 16, 15, 14, 21, 22, 23, 24],
        dtype=np.int64,
    )

    def __init__(
        self,
        path: str | Path,
        lidar_stack: int = 5,
        lidar_max_m: float = 6.0,
        *,
        mirror_augmentation: bool = False,
    ) -> None:
        if lidar_stack <= 0 or lidar_max_m <= 0.0:
            raise ValueError("lidar stack and range must be positive")
        self.path = Path(path)
        self.lidar_stack = lidar_stack
        self.lidar_max_m = lidar_max_m
        self.mirror_augmentation = mirror_augmentation
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
        multiplier = 2 if self.mirror_augmentation else 1
        return multiplier * len(self.sample_index)

    def __getitem__(self, item: int) -> dict[str, torch.Tensor]:
        mirrored = item >= len(self.sample_index)
        item %= len(self.sample_index)
        index = int(self.sample_index[item])
        episode_start_values = self.observations.get("episode_start_index")
        episode_start = 0 if episode_start_values is None else int(episode_start_values[index])
        start = max(episode_start, index - self.lidar_stack + 1)
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
        action = int(self.actions[item])
        mask = self.masks[item].copy()
        costs = self.costs[item].copy()
        if mirrored:
            scan = scan[:, ::-1].copy()
            state[1] *= -1.0
            state[np.arange(3, 18, 2)] *= -1.0
            state[19] *= -1.0
            state[21] *= -1.0
            state[32:42] *= -1.0
            action = int(self._mirror_actions[action])
            mask = mask[self._mirror_actions]
            costs = costs[self._mirror_actions]
        return {
            "lidar": torch.from_numpy(np.clip(scan, 0.0, self.lidar_max_m) / self.lidar_max_m),
            "state": torch.from_numpy(state),
            "action": torch.tensor(action, dtype=torch.long),
            "margin": torch.tensor(self.margins[item], dtype=torch.float32),
            "mask": torch.from_numpy(mask),
            "costs": torch.from_numpy(costs),
        }
