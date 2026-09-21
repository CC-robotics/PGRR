from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml
from ramp_core.scenario import TriggerMetric, event_spec_from_contract

ROOT = Path(__file__).resolve().parents[2]


def _config() -> dict:
    path = ROOT / "configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _probe_module():
    path = ROOT / "scripts/student/probe_event_control_contract.py"
    spec = importlib.util.spec_from_file_location("probe_event_control_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adapter_uses_split_specific_lead_stop_values() -> None:
    variant = _config()["variants"][0]
    train = event_spec_from_contract(variant, split="train")
    validation = event_spec_from_contract(variant, split="validation")
    assert train.trigger_metric is TriggerMetric.ROBOT_ACTOR_DISTANCE
    assert train.active_duration_s == pytest.approx(3.0)
    assert validation.active_duration_s == pytest.approx(3.5)
    assert validation.trigger_threshold_m == pytest.approx(3.2)


def test_adapter_uses_goal_trigger_without_enabling_occlusion() -> None:
    variant = _config()["variants"][1]
    spec = event_spec_from_contract(variant, split="validation")
    assert spec.trigger_metric is TriggerMetric.ROBOT_GOAL_DISTANCE
    assert spec.trigger_threshold_m == pytest.approx(5.5)
    assert variant["occlusion_claim_enabled"] is False


def test_probe_produces_four_valid_isolated_traces() -> None:
    path = ROOT / "configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml"
    report = _probe_module().analyze(path)
    assert report["trace_count"] == 4
    assert report["all_traces_valid"] is True
    assert report["policy_observation_isolation_check"] is True
    assert report["executable_scenarios_generated"] is False
    assert all(len(item["transitions"]) == 2 for item in report["traces"])


def test_adapter_rejects_test_split() -> None:
    with pytest.raises(ValueError, match="train or validation"):
        event_spec_from_contract(_config()["variants"][0], split="test")
