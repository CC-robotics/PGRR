from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def _module():  # type: ignore[no-untyped-def]
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "evaluate" / "summarize_failure_mining.py"
    spec = importlib.util.spec_from_file_location("summarize_failure_mining", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_separates_invalid_resets_from_algorithm_rows(tmp_path: Path) -> None:
    module = _module()
    module.ROOT = tmp_path
    results = tmp_path / "outputs" / "pilot" / "results.csv"
    results.parent.mkdir(parents=True)
    fieldnames = ("episode_id", "family", "outcome", "sample_count", "raw_sha256")
    with results.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            [
                {
                    "episode_id": "a",
                    "family": "crossing_flow",
                    "outcome": "COLLISION",
                    "sample_count": 10,
                    "raw_sha256": "one",
                },
                {
                    "episode_id": "b",
                    "family": "crossing_flow",
                    "outcome": "GOAL_REACHED",
                    "sample_count": 12,
                    "raw_sha256": "two",
                },
            ]
        )
    reset = tmp_path / "outputs" / "logs" / "baseline" / "invalid_reset" / "reset.json"
    reset.parent.mkdir(parents=True)
    reset.write_text(json.dumps({"outcome": "INVALID_RESET"}), encoding="utf-8")
    payload = module.summarize(results, tmp_path / "outputs" / "pilot" / "summary.json")
    assert payload["algorithm_episode_count"] == 2
    assert payload["total_sample_count"] == 22
    assert payload["excluded_invalid_reset_count"] == 1
    assert payload["families"]["crossing_flow"]["failure_rate"] == 0.5
