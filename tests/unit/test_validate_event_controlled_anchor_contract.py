from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    path = ROOT / "scripts/student/validate_event_controlled_anchor_contract.py"
    spec = importlib.util.spec_from_file_location("validate_event_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> dict:
    path = ROOT / "configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_checked_in_contract_is_valid_and_non_executable() -> None:
    report = _load_module().validate(_config())
    assert report["valid"] is True
    assert report["runtime_implementation_present"] is False
    assert report["executable_scenarios_generated"] is False
    assert report["held_out_test_materialized"] is False


def test_contract_rejects_test_split() -> None:
    config = copy.deepcopy(_config())
    config["claim_boundary"]["allowed_splits"].append("test")
    report = _load_module().validate(config)
    assert report["valid"] is False
    assert "only ordered train/validation splits are allowed" in report["errors"]


def test_contract_rejects_path_blocking_release() -> None:
    config = copy.deepcopy(_config())
    config["variants"][0]["release"]["terminal_waypoint_off_robot_centerline"] = False
    report = _load_module().validate(config)
    assert report["valid"] is False
    assert any("release must clear" in error for error in report["errors"])


def test_contract_rejects_duplicate_seeds() -> None:
    config = copy.deepcopy(_config())
    config["variants"][1]["train"]["seed"] = config["variants"][0]["train"]["seed"]
    report = _load_module().validate(config)
    assert report["valid"] is False
    assert "train/validation seeds must be globally distinct" in report["errors"]
