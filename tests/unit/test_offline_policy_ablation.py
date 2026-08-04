from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/evaluate/offline_policy_ablation.py"
SPEC = importlib.util.spec_from_file_location("offline_policy_ablation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_evaluate_predictions_reports_mask_and_imitation_metrics() -> None:
    logits = np.zeros((2, 25), dtype=np.float32)
    logits[0, 1] = 2.0
    logits[1, 4] = 2.0
    predictions = np.asarray([1, 4])
    experts = np.asarray([1, 3])
    masks = np.ones((2, 25), dtype=np.bool_)
    masks[1, 4] = False
    costs = np.ones((2, 25), dtype=np.float32)
    costs[0, 1] = 0.0
    costs[1, 3] = 0.0
    costs[1, 4] = np.inf

    metrics = MODULE.evaluate_predictions(predictions, logits, experts, masks, costs)

    assert metrics["sample_count"] == 2.0
    assert metrics["top1_accuracy"] == 0.5
    assert metrics["invalid_action_rate"] == 0.5
    assert metrics["expert_cost_regret"] == 500000.0
    assert metrics["near_optimal_rate"] == 0.5
    assert metrics["catastrophic_action_rate"] == 0.5
