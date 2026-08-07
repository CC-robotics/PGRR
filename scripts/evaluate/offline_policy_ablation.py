#!/usr/bin/env python3
"""Evaluate BC variants and the selected DAgger policy on one locked dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from ramp_ml.datasets import RecoveryHDF5Dataset
from ramp_ml.recovery_policy import RecoveryPolicyNetwork
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS = {
    "Uniform BC": ROOT / "checkpoints/bc/uniform_scenario/best.pt",
    "Margin-weighted BC": ROOT / "checkpoints/bc/mwbc_scenario/best.pt",
    "Triggered DAgger": ROOT / "checkpoints/dagger/coverage_safety_aligned/best.pt",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_predictions(
    predictions: np.ndarray,
    logits: np.ndarray,
    expert_actions: np.ndarray,
    original_masks: np.ndarray,
    expert_costs: np.ndarray,
) -> dict[str, float]:
    """Compute transparent offline imitation and safety metrics."""

    sample_count = len(predictions)
    expected_shapes = {
        "predictions": (sample_count,),
        "logits": (sample_count, 25),
        "expert_actions": (sample_count,),
        "original_masks": (sample_count, 25),
        "expert_costs": (sample_count, 25),
    }
    values = {
        "predictions": predictions,
        "logits": logits,
        "expert_actions": expert_actions,
        "original_masks": original_masks,
        "expert_costs": expert_costs,
    }
    for name, value in values.items():
        if value.shape != expected_shapes[name]:
            raise ValueError(f"{name} has shape {value.shape}, expected {expected_shapes[name]}")
    if sample_count == 0 or not original_masks.any(axis=1).all():
        raise ValueError(
            "a non-empty dataset with at least one legal action per sample is required"
        )

    indices = np.arange(sample_count)
    invalid = ~original_masks[indices, predictions]
    selected_costs = expert_costs[indices, predictions]
    best_costs = expert_costs[indices, expert_actions]
    finite_regret = np.maximum(selected_costs - best_costs, 0.0)
    finite_regret = np.where(np.isfinite(finite_regret), finite_regret, 1.0e6)
    top3 = np.argpartition(logits, -3, axis=1)[:, -3:]
    return {
        "sample_count": float(sample_count),
        "top1_accuracy": float(np.mean(predictions == expert_actions)),
        "top3_accuracy": float(np.mean(np.any(top3 == expert_actions[:, None], axis=1))),
        "invalid_action_rate": float(np.mean(invalid)),
        "expert_cost_regret": float(np.mean(finite_regret)),
        "near_optimal_rate": float(np.mean(finite_regret <= 0.1)),
        "catastrophic_action_rate": float(
            np.mean(invalid | ((selected_costs >= 1.0e5) & (best_costs < 1.0e5)))
        ),
    }


def load_model(path: Path) -> RecoveryPolicyNetwork:
    if not path.is_file():
        raise FileNotFoundError(path)
    checkpoint: dict[str, Any] = torch.load(path, map_location="cpu", weights_only=False)
    state = checkpoint.get("model_state_dict")
    if not isinstance(state, dict):
        raise ValueError(f"checkpoint has no model_state_dict: {path}")
    model = RecoveryPolicyNetwork()
    model.load_state_dict(state)
    model.eval()
    return model


def evaluate_model(
    model: RecoveryPolicyNetwork,
    loader: DataLoader[dict[str, torch.Tensor]],
    *,
    mask_enabled: bool,
) -> dict[str, float]:
    predictions: list[np.ndarray] = []
    logits_parts: list[np.ndarray] = []
    experts: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    costs: list[np.ndarray] = []
    with torch.no_grad():
        for batch in loader:
            original_mask = batch["mask"].bool()
            inference_mask = original_mask if mask_enabled else torch.ones_like(original_mask)
            logits = model(batch["lidar"], batch["state"], inference_mask)
            logits_parts.append(logits.cpu().numpy())
            predictions.append(logits.argmax(dim=-1).cpu().numpy())
            experts.append(batch["action"].cpu().numpy())
            masks.append(original_mask.cpu().numpy())
            costs.append(batch["costs"].cpu().numpy())
    return evaluate_predictions(
        np.concatenate(predictions),
        np.concatenate(logits_parts),
        np.concatenate(experts),
        np.concatenate(masks),
        np.concatenate(costs),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "data/interim/multiscenario_safety_aligned_validation.h5",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/final/offline_policy_ablation.csv",
    )
    parser.add_argument("--batch-size", type=int, default=128)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    dataset_path = args.dataset.resolve()
    dataset = RecoveryHDF5Dataset(dataset_path, mirror_augmentation=False)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    rows: list[dict[str, Any]] = []
    for model_name, model_path in DEFAULT_MODELS.items():
        model = load_model(model_path)
        parameter_count = sum(parameter.numel() for parameter in model.parameters())
        for mask_enabled in (True, False):
            metrics = evaluate_model(model, loader, mask_enabled=mask_enabled)
            rows.append(
                {
                    "model": model_name,
                    "action_mask": "enabled" if mask_enabled else "disabled_offline",
                    "checkpoint": str(model_path.relative_to(ROOT)),
                    "checkpoint_sha256": sha256_file(model_path),
                    "dataset": str(dataset_path.relative_to(ROOT)),
                    "dataset_sha256": sha256_file(dataset_path),
                    "parameter_count": parameter_count,
                    **metrics,
                }
            )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)
    manifest = {
        "schema_version": 1,
        "output": str(output.relative_to(ROOT)),
        "output_sha256": sha256_file(output),
        "dataset": str(dataset_path.relative_to(ROOT)),
        "dataset_sha256": sha256_file(dataset_path),
        "sample_count": len(dataset),
        "models": [str(path.relative_to(ROOT)) for path in DEFAULT_MODELS.values()],
        "note": "Mask-disabled rows are offline proposals and were never executed on the robot.",
    }
    output.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Offline ablation PASS: samples={len(dataset)} rows={len(rows)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
