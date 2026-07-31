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
from torch.utils.data import DataLoader, Subset

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
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
    dataset = RecoveryHDF5Dataset(args.dataset)
    generator = np.random.default_rng(seed)
    order = generator.permutation(len(dataset))
    validation_count = max(1, round(len(dataset) * float(config["validation_fraction"])))
    validation_indices = order[:validation_count].tolist()
    train_indices = order[validation_count:].tolist()
    if not train_indices:
        raise ValueError("dataset is too small for a train/validation smoke split")
    train_loader = DataLoader(
        Subset(dataset, train_indices),
        batch_size=int(config["batch_size"]),
        shuffle=True,
        generator=torch.Generator().manual_seed(seed),
    )
    validation_loader = DataLoader(
        Subset(dataset, validation_indices),
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
        )
        with torch.no_grad():
            validation_metrics = run_epoch(
                model,
                validation_loader,
                device=device,
                optimizer=None,
                margin_lambda=float(config["margin_lambda"]),
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
    (args.output / "metrics.json").write_text(
        json.dumps(
            {
                "dataset": str(args.dataset),
                "device": str(device),
                "train_samples": len(train_indices),
                "validation_samples": len(validation_indices),
                "history": history,
                "warning": "single-episode random split is pipeline smoke only, not paper evidence",
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
