from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module(root: Path):
    path = root / "scripts/student/audit_anchor_scenario_semantics.py"
    spec = importlib.util.spec_from_file_location("audit_anchor_scenario_semantics", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scenario(family: str, cyclic: bool, limitations: list[str] | None = None) -> dict:
    return {
        "robots": [{"start": [0.0, 0.0, 0.0], "goal": [10.0, 0.0, 0.0]}],
        "obstacles": {
            "dynamic": [
                {
                    "cyclic_goals": cyclic,
                    "waypoints": [[4.0, -1.0, 0.0], [4.0, 1.0, 0.0]],
                }
            ],
            "static": [
                {"name": "south_00", "pos": [0.0, -1.5, 0.0]},
                {"name": "north_00", "pos": [0.0, 1.5, 0.0]},
            ],
        },
        "ramp_metadata": {
            "family": family,
            "scenario_id": "example",
            "split": "train",
            "prototype_status": "draft_geometry_not_frozen",
            "limitations": limitations or [],
        },
    }


def test_goal_crossing_is_not_misreported_as_one_shot(tmp_path: Path) -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    path = tmp_path / "goal.json"
    path.write_text(
        json.dumps(
            _scenario(
                "goal_approach_lateral_interruption",
                True,
                ["occlusion not implemented in this prototype"],
            )
        ),
        encoding="utf-8",
    )
    result = module.audit(path)
    assert result["semantic_checks"]["route_crosses_robot_path"] is True
    assert result["semantic_checks"]["one_shot_interruption"] is False
    assert result["semantic_checks"]["occlusion_implemented"] is False
    assert result["wall_centerline_spacing_m"] == pytest.approx(3.0)


def test_lead_stop_requires_one_actor(tmp_path: Path) -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    content = _scenario("lead_pedestrian_sudden_stop", False)
    content["obstacles"]["dynamic"] = []
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        module.audit(path)


def test_unsupported_family_is_rejected(tmp_path: Path) -> None:
    module = _load_module(Path(__file__).resolve().parents[2])
    path = tmp_path / "bad-family.json"
    path.write_text(json.dumps(_scenario("other", False)), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        module.audit(path)
