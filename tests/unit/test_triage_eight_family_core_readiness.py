from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(root: Path):
    path = root / "scripts/student/triage_eight_family_core_readiness.py"
    spec = importlib.util.spec_from_file_location("triage_eight_family", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _family(limitation: str | None = None) -> dict:
    row = {
        "family_index": 0,
        "id": "family",
        "scenario_id": "scenario",
        "scenario_path": "scenario.json",
        "sha256": "placeholder",
        "actual_motion_verified": True,
    }
    if limitation:
        row["limitation"] = limitation
    return row


def _pair(trigger: bool, pgrr_outcome: str) -> dict:
    return {
        "family": "family",
        "scenario_sha256": "placeholder",
        "runs": {
            "base": {"outcome": "COLLISION"},
            "pgrr": {
                "outcome": pgrr_outcome,
                "recovery_trace": {"temporary_subgoal_decision_count": 1},
            },
        },
        "paired_interpretation": {"pgrr_recovery_triggered": trigger},
    }


def test_trigger_failure_has_priority(tmp_path: Path) -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    scenario = tmp_path / "scenario.json"
    scenario.write_text("{}", encoding="utf-8")
    family = _family("semantic limitation")
    family["sha256"] = module._sha256(scenario)
    pair = _pair(False, "TIMEOUT")
    pair["scenario_sha256"] = family["sha256"]
    row = module.classify(family, pair, tmp_path)
    assert row["next_gate"] == "trigger_or_scenario_activation_audit"
    assert row["core_comparative_ready"] is False


def test_goal_reached_semantic_family_advances_to_validation(tmp_path: Path) -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    scenario = tmp_path / "scenario.json"
    scenario.write_text("{}", encoding="utf-8")
    family = _family()
    family["sha256"] = module._sha256(scenario)
    pair = _pair(True, "GOAL_REACHED")
    pair["scenario_sha256"] = family["sha256"]
    row = module.classify(family, pair, tmp_path)
    assert row["next_gate"] == "validation_replication"
    assert row["core_comparative_ready"] is True


def test_semantic_limitation_blocks_promotion(tmp_path: Path) -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    scenario = tmp_path / "scenario.json"
    scenario.write_text("{}", encoding="utf-8")
    family = _family("not independently controlled")
    family["sha256"] = module._sha256(scenario)
    pair = _pair(True, "TIMEOUT")
    pair["scenario_sha256"] = family["sha256"]
    row = module.classify(family, pair, tmp_path)
    assert row["next_gate"] == "event_semantics_and_task_feasibility"
