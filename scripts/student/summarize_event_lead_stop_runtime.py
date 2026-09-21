#!/usr/bin/env python3
"""Summarize the first fixed-seed event lead-stop runtime gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(evidence_dir: Path, output: Path) -> dict[str, Any]:
    base_outcome_path = evidence_dir / "pgrr_event_leadstop_s92500_base.outcome.json"
    pgrr_outcome_path = evidence_dir / "pgrr_event_leadstop_s92500_pgrr.outcome.json"
    base_log = evidence_dir / "pgrr_event_leadstop_s92500_base_runtime.log"
    pgrr_log = evidence_dir / "pgrr_event_leadstop_s92500_pgrr_runtime.log"
    retry_log = evidence_dir / "pgrr_event_leadstop_s92500_pgrr_retry01_runtime.log"
    paths = [base_outcome_path, pgrr_outcome_path, base_log, pgrr_log, retry_log]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    base = json.loads(base_outcome_path.read_text(encoding="utf-8"))
    pgrr = json.loads(pgrr_outcome_path.read_text(encoding="utf-8"))
    retry_text = retry_log.read_text(encoding="utf-8", errors="replace")
    events = base.get("scenario_events", [])
    transitions = [event.get("transition") for event in events]
    report = {
        "candidate_id": "lead_stop_bounded_release_v1_train_r00_s92500",
        "split": "train",
        "seed": 92500,
        "base": {
            "outcome": base.get("outcome"),
            "sample_count": base.get("sample_count"),
            "physical_goal_distance_m": base.get("physical_goal_distance_m"),
            "scenario_event_count": len(events),
            "scenario_event_transitions": transitions,
            "event_trigger_sim_time_s": events[0].get("sim_time_s") if events else None,
            "event_release_sim_time_s": events[1].get("sim_time_s")
            if len(events) > 1
            else None,
        },
        "pgrr_attempt_1": {
            "outcome": pgrr.get("outcome"),
            "detail": pgrr.get("detail"),
            "sample_count": pgrr.get("sample_count"),
            "physical_goal_distance_m": pgrr.get("physical_goal_distance_m"),
            "scenario_event_count": len(pgrr.get("scenario_events", [])),
            "valid_comparative_episode": False,
        },
        "pgrr_retry_1": {
            "outcome_artifact_created": False,
            "startup_topic_timeout": "timed out waiting for required baseline topics"
            in retry_text,
            "valid_comparative_episode": False,
        },
        "event_runtime_semantics_observed_on_base": transitions
        == ["pre_event_to_active_event", "active_event_to_released"],
        "paired_method_claim_authorized": False,
        "core_case_promotion_authorized": False,
        "gate_result": "inconclusive_pgrr_runtime_invalid",
        "raw_sha256": {path.name: _sha256(path) for path in paths},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.evidence_dir, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
