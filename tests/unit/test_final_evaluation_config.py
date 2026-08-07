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
    scenarios = split["scenarios"]
    families = {row["family"] for row in scenarios}
    densities = {row["density"] for row in scenarios}

    assert split["split"] == "test"
    assert config["benchmark"]["id"] == "moderate_social_navigation_v6"
    assert split["benchmark_id"] == "moderate_social_navigation_v6"
    assert len(scenarios) == 120
    assert set(primary["families"]) == families
    assert set(primary["densities"]) == densities == {"low", "medium", "high"}
    assert primary["methods"] == ["base", "standard", "heuristic", "bc_uniform", "pgrr"]
    assert primary["repetitions_per_family_density_cell"] == 5
    assert primary["expected_conditions_per_method"] == len(scenarios)
    assert primary["expected_episodes"] == len(scenarios) * len(primary["methods"])
    assert config["analysis"]["exclusions"] == ["SIMULATOR_FAILURE", "INVALID_RESET"]
    assert _sha256(split_path) == config["runtime"]["split_manifest_sha256"]

    assert config["runtime"]["episode_timeout_s"] == 240.0
    assert config["runtime"]["parallel_jobs"] == 6
    assert config["learned_method"]["source_policy"] == "pgrr"
    assert config["learned_baseline"]["source_policy"] == "bc_uniform"
    for model in ("learned_baseline", "learned_method"):
        checkpoint = ROOT / config[model]["checkpoint"]
        assert checkpoint.is_file()
        assert _sha256(checkpoint) == config[model]["checkpoint_sha256"]
    assert config["learned_method"]["margin_weighting_enabled"] is False
    assert config["learned_method"]["ppo_enabled"] is False

    catalog = ROOT / config["benchmark"]["catalog"]
    assert _sha256(catalog) == config["benchmark"]["catalog_sha256"]
    calibration_split = ROOT / config["benchmark"]["calibration_split"]
    assert _sha256(calibration_split) == config["benchmark"]["calibration_split_sha256"]
    assert config["benchmark"]["calibration_report"] == (
        "outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json"
    )
    assert config["benchmark"]["calibration_report_sha256"] == (
        "0fbf8a159a1e1b96e940bec0efb31e5952ba5b0333439992f370a9a9fb41e15f"
    )
    assert config["benchmark"]["calibration_policy"] == "validation_only_before_test"

    frozen_paths = {
        "arena_profile_sha256": "configs/platform/arena_profile.yaml",
        "planner_profiles_sha256": "configs/planner/baselines.yaml",
        "failure_rules_sha256": "configs/failure/rules.yaml",
        "state_machine_sha256": "configs/failure/recovery_state_machine.yaml",
        "recovery_actions_sha256": "configs/planner/recovery_actions.yaml",
    }
    for key, relative in frozen_paths.items():
        assert _sha256(ROOT / relative) == config["frozen_inputs"][key]
