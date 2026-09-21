"""Shared non-runtime utilities for isolated eight-family geometry smokes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_draft(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("status") != "draft_train_validation_only_not_executable":
        raise ValueError("only the non-executable eight-family draft is accepted")
    return config


def base_compiler() -> ModuleType:
    path = ROOT / "scripts" / "data" / "compile_scenarios.py"
    spec = importlib.util.spec_from_file_location("pgrr_base_scenario_compiler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_smoke(
    config: dict[str, Any], payload: dict[str, Any], output_root: Path, family: str
) -> dict[str, Any]:
    """Validate and write a train-only JSON, preview, and manifest."""
    metadata = payload["ramp_metadata"]
    if metadata.get("split") not in {"train", "validation"}:
        raise ValueError("geometry smoke must never materialize test")
    base = base_compiler()
    base._validate_scenario(payload, [float(x) for x in config["map"]["bounds_m"]])
    scenario_id = str(metadata["scenario_id"])
    output = output_root / "generated" / "arena" / str(config["map"]["id"]) / f"{scenario_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output.write_text(text, encoding="utf-8")
    preview = output_root / "previews" / f"{scenario_id}.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    base._render_preview(payload, [float(x) for x in config["map"]["bounds_m"]], float(config["map"]["preview_resolution_m"]), preview)
    return {"status": "geometry_smoke_only", "family": family, "scenario_id": scenario_id, "split": metadata["split"], "held_out_test_materialized": False, "json": str(output), "preview": str(preview), "sha256": hashlib.sha256(text.encode()).hexdigest()}
