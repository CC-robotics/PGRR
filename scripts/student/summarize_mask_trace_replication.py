#!/usr/bin/env python3
"""Aggregate non-frozen mask-trace smoke reports without performance claims."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

STAGES = ("map_connectivity", "observable_scan", "path_corridor")


def _split(episode_id: str) -> str:
    return "validation" if "_validation_" in episode_id else "train"


def summarize(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise ValueError("at least one report is required")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if not all(report.get("diagnostic_only") is True for report in reports):
        raise ValueError("every input must be diagnostic-only")
    if not all(report.get("runtime_valid") is not False for report in reports):
        raise ValueError("runtime-invalid reports cannot enter replication summary")

    trace_status = Counter(str(report.get("trace_status", "complete")) for report in reports)
    outcomes = Counter(str(report.get("outcome")) for report in reports)
    split_status: Counter[str] = Counter()
    first_empty: Counter[str] = Counter()
    stage_removed = Counter()
    traced_decisions = 0
    rows: list[dict[str, Any]] = []
    for report in reports:
        episode_id = str(report["episode_id"])
        split = _split(episode_id)
        status = str(report.get("trace_status", "complete"))
        split_status[f"{split}:{status}"] += 1
        traced_decisions += int(report.get("trace_decision_row_count", 0))
        for stage, count in report.get("first_temporary_empty_stage_counts", {}).items():
            first_empty[stage] += int(count)
        for stage in STAGES:
            totals = report.get("temporary_subgoal_layer_totals", {}).get(stage, {})
            stage_removed[stage] += int(totals.get("temporary_removed_total", 0))
        rows.append(
            {
                "episode_id": episode_id,
                "split": split,
                "outcome": report.get("outcome"),
                "telemetry_rows": report.get("telemetry_row_count"),
                "trace_status": status,
                "traced_decisions": report.get("trace_decision_row_count", 0),
                "first_empty_stage_counts": report.get(
                    "first_temporary_empty_stage_counts", {}
                ),
            }
        )

    validation_complete = split_status["validation:complete"]
    validation_report_count = sum(
        count for key, count in split_status.items() if key.startswith("validation:")
    )
    if validation_complete > 0:
        claim_boundary = "At least one validation episode contains a complete trace."
    elif validation_report_count > 0:
        claim_boundary = (
            "Train-only trigger-positive replication exists; supplied validation "
            "episodes contain no complete trigger trace, so cross-split layer "
            "replication is not established."
        )
    else:
        claim_boundary = (
            "Train-only trigger-positive replication exists; no validation report was "
            "supplied, so cross-split layer replication is not established."
        )
    return {
        "diagnostic_only": True,
        "performance_claim": False,
        "episode_count": len(reports),
        "outcome_counts": dict(sorted(outcomes.items())),
        "trace_status_counts": dict(sorted(trace_status.items())),
        "split_trace_status_counts": dict(sorted(split_status.items())),
        "traced_decision_count": traced_decisions,
        "first_temporary_empty_stage_counts": {
            stage: first_empty[stage] for stage in (*STAGES, "none")
        },
        "temporary_removed_totals": {stage: stage_removed[stage] for stage in STAGES},
        "validation_layer_replication_established": validation_complete > 0,
        "claim_boundary": claim_boundary,
        "episodes": rows,
        "sources": [str(path) for path in paths],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
