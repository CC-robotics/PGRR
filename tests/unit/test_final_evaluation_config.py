from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_evaluation_covers_full_test_split_and_locked_checkpoint() -> None:
    config = yaml.safe_load((ROOT / "configs/final/ei_gazebo.yaml").read_text())
    split_path = ROOT / config["runtime"]["split_manifest"]
    split = yaml.safe_load(split_path.read_text())

    primary = config["primary_comparison"]
    extra = config["high_density_mechanism_comparison"]
    scenarios = split["scenarios"]
    families = {row["family"] for row in scenarios}
    densities = {row["density"] for row in scenarios}

    assert split["split"] == "test"
    assert len(scenarios) == 24
    assert set(primary["families"]) == families
    assert set(primary["densities"]) == densities == {"low", "medium", "high"}
    assert primary["methods"] == ["base", "bc"]
    assert primary["expected_episodes"] == len(scenarios) * len(primary["methods"])
    assert extra["methods"] == ["standard", "heuristic"]
    assert extra["densities"] == ["high"]
    assert extra["expected_episodes"] == len(families) * len(extra["methods"])
    assert config["analysis"]["exclusions"] == ["SIMULATOR_FAILURE", "INVALID_RESET"]
    assert _sha256(split_path) == config["runtime"]["split_manifest_sha256"]

    checkpoint = ROOT / config["learned_method"]["checkpoint"]
    assert checkpoint.is_file()
    assert _sha256(checkpoint) == config["learned_method"]["checkpoint_sha256"]
    assert config["learned_method"]["margin_weighting_enabled"] is False
    assert config["learned_method"]["ppo_enabled"] is False
