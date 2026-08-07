#!/usr/bin/env python3
"""Train a compact action-masked margin-weighted BC recovery policy."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
import yaml
from ramp_ml.bc import run_epoch
from ramp_ml.datasets import RecoveryHDF5Dataset
from ramp_ml.recovery_policy import RecoveryPolicyNetwork
from torch.utils.data import DataLoader, Subset, WeightedRandomSampler

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--validation-dataset", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/imitation/bc_smoke.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "checkpoints/bc/smoke")
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    seed = int(config["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device_name = str(config["device"])
    device = torch.device(
        "cuda"
        if device_name == "auto" and torch.cuda.is_available()
        else "cpu"
        if device_name == "auto"
        else device_name
    )
    dataset = RecoveryHDF5Dataset(
        args.dataset,
        mirror_augmentation=bool(config.get("mirror_augmentation", False)),
    )
    validation_dataset = (
        RecoveryHDF5Dataset(args.validation_dataset)
        if args.validation_dataset is not None
        else dataset
    )
    if args.validation_dataset is None:
        generator = np.random.default_rng(seed)
        order = generator.permutation(len(dataset))
        validation_count = max(1, round(len(dataset) * float(config["validation_fraction"])))
        validation_indices = order[:validation_count].tolist()
        train_indices = order[validation_count:].tolist()
        warning = "single-dataset random split is pipeline smoke only, not paper evidence"
    else:
        train_indices = list(range(len(dataset)))
        validation_indices = list(range(len(validation_dataset)))
        warning = ""
    if not train_indices or not validation_indices:
        raise ValueError("train and validation datasets must be non-empty")
    train_subset = Subset(dataset, train_indices)
    sampler: WeightedRandomSampler | None = None
    if bool(config.get("class_balanced_sampling", False)):
        actions = np.asarray(
            [int(dataset[index]["action"]) for index in train_indices], dtype=np.int64
        )
        counts = np.bincount(actions, minlength=25)
        weights = np.asarray([1.0 / counts[action] for action in actions], dtype=np.float64)
        sampler = WeightedRandomSampler(
            torch.from_numpy(weights),
            num_samples=len(weights),
            replacement=True,
            generator=torch.Generator().manual_seed(seed),
        )
    train_loader = DataLoader(
        train_subset,
        batch_size=int(config["batch_size"]),
        shuffle=sampler is None,
        sampler=sampler,
        generator=torch.Generator().manual_seed(seed),
    )
    validation_loader = DataLoader(
        Subset(validation_dataset, validation_indices),
        batch_size=int(config["batch_size"]),
        shuffle=False,
    )
    model = RecoveryPolicyNetwork().to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config["learning_rate"]),
        weight_decay=float(config["weight_decay"]),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    best_loss = float("inf")
    patience = 0
    history: list[dict[str, object]] = []
    for epoch in range(int(config["epochs"])):
        train_metrics = run_epoch(
            model,
            train_loader,
            device=device,
            optimizer=optimizer,
            margin_lambda=float(config["margin_lambda"]),
            cost_regret_lambda=float(config.get("cost_regret_lambda", 0.0)),
        )
        with torch.no_grad():
            validation_metrics = run_epoch(
                model,
                validation_loader,
                device=device,
                optimizer=None,
                margin_lambda=float(config["margin_lambda"]),
                cost_regret_lambda=float(config.get("cost_regret_lambda", 0.0)),
            )
        history.append(
            {
                "epoch": epoch,
                "train": asdict(train_metrics),
                "validation": asdict(validation_metrics),
            }
        )
        if validation_metrics.loss < best_loss:
            best_loss = validation_metrics.loss
            patience = 0
            torch.save(
                {"model_state_dict": model.state_dict(), "config": config},
                args.output / "best.pt",
            )
        else:
            patience += 1
            if patience >= int(config["early_stopping_patience"]):
                break
    checkpoint = torch.load(args.output / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to("cpu").eval()
    example = dataset[0]
    traced = torch.jit.trace(
        model,
        (
            example["lidar"][None],
            example["state"][None],
            example["mask"][None],
        ),
    )
    traced.save(str(args.output / "best.ts"))
    torch.onnx.export(
        model,
        (
            example["lidar"][None],
            example["state"][None],
            example["mask"][None],
        ),
        args.output / "best.onnx",
        input_names=("lidar", "state", "mask"),
        output_names=("masked_logits",),
        dynamic_axes={
            "lidar": {0: "batch"},
            "state": {0: "batch"},
            "mask": {0: "batch"},
            "masked_logits": {0: "batch"},
        },
        opset_version=17,
        dynamo=False,
    )
    (args.output / "metrics.json").write_text(
        json.dumps(
            {
                "dataset": str(args.dataset),
                "validation_dataset": (
                    None if args.validation_dataset is None else str(args.validation_dataset)
                ),
                "device": str(device),
                "train_samples": len(train_indices),
                "validation_samples": len(validation_indices),
                "history": history,
                "warning": warning,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(history[-1], sort_keys=True))


if __name__ == "__main__":
    main()
