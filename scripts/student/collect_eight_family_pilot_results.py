"""Collect completed Base/PGRR pilot pairs without replacing raw outcomes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

if __package__:
    from .analyze_recovery_trace import summarize_recovery
else:
    from analyze_recovery_trace import summarize_recovery


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifacts(data_root: Path, episode_id: str) -> dict[str, Path]:
    return {
        "raw_jsonl": data_root / f"{episode_id}.jsonl",
        "metadata": data_root / f"{episode_id}.metadata.json",
        "outcome": data_root / f"{episode_id}.outcome.json",
    }


def _load_attempt(episode_id: str, data_root: Path) -> dict[str, Any] | None:
    paths = _artifacts(data_root, episode_id)
    if not paths["outcome"].is_file():
        return None
    outcome = json.loads(paths["outcome"].read_text(encoding="utf-8"))
    available = {name: path for name, path in paths.items() if path.is_file()}
    infrastructure = outcome["outcome"] in {"SIMULATOR_FAILURE", "INVALID_RESET"}
    if not infrastructure and len(available) != len(paths):
        missing = sorted(set(paths) - set(available))
        raise FileNotFoundError(f"incomplete algorithm episode {episode_id}: missing {missing}")
    result: dict[str, Any] = {
        "episode_id": episode_id,
        "outcome": outcome["outcome"],
        "outcome_detail": outcome["detail"],
        "sample_count": outcome["sample_count"],
        "infrastructure_attempt": infrastructure,
        "artifact_sha256": {name: _sha256(path) for name, path in available.items()},
    }
    for key in ("physical_goal_distance_m", "localized_goal_distance_m"):
        if key in outcome:
            result[key] = outcome[key]
    return result


def _load_run(row: dict[str, str], data_root: Path) -> dict[str, Any] | None:
    episode_id = row["episode_id"]
    retry_outcomes = sorted(data_root.glob(f"{episode_id}_retry[0-9][0-9].outcome.json"))
    retry_ids = [path.name.removesuffix(".outcome.json") for path in retry_outcomes]
    candidate_ids = [episode_id, *retry_ids]
    attempts = [
        attempt
        for candidate in candidate_ids
        if (attempt := _load_attempt(candidate, data_root))
    ]
    if not attempts:
        return None
    selected = next(
        (attempt for attempt in attempts if not attempt["infrastructure_attempt"]),
        None,
    )
    if selected is None:
        return None
    result = dict(selected)
    result["planned_episode_id"] = episode_id
    result["selected_attempt_id"] = selected["episode_id"]
    result["attempt_history"] = attempts
    if row["method"] == "pgrr":
        trace_path = _artifacts(data_root, selected["episode_id"])["raw_jsonl"]
        trace = summarize_recovery(trace_path)
        result["recovery_trace"] = {
            "state_transitions": trace["state_transitions"],
            "decision_event_count": trace["decision_event_count"],
            "decision_action_counts": trace["decision_action_counts"],
            "decision_reason_counts": trace["decision_reason_counts"],
            "temporary_subgoal_decision_count": trace["temporary_subgoal_decision_count"],
            "original_goal_restored_event_count": trace["original_goal_restored_event_count"],
        }
    return result


def _interpret(base: dict[str, Any], pgrr: dict[str, Any]) -> dict[str, Any]:
    base_outcome, pgrr_outcome = base["outcome"], pgrr["outcome"]
    trace = pgrr["recovery_trace"]
    triggered = any(item["recovery_state"] != 0 for item in trace["state_transitions"])
    return {
        "pgrr_recovery_triggered": triggered,
        "base_collision_avoided": base_outcome == "COLLISION" and pgrr_outcome != "COLLISION",
        "pgrr_completion_gain": base_outcome != "GOAL_REACHED" and pgrr_outcome == "GOAL_REACHED",
        "both_goal_reached": base_outcome == pgrr_outcome == "GOAL_REACHED",
        "both_same_failure": base_outcome == pgrr_outcome and base_outcome != "GOAL_REACHED",
        "superiority_claim_supported": False,
    }


def collect(plan_path: Path, data_root: Path) -> dict[str, Any]:
    with plan_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    grouped: dict[int, dict[str, dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(int(row["family_index"]), {})[row["method"]] = row

    pairs = []
    incomplete = []
    for family_index in sorted(grouped):
        method_rows = grouped[family_index]
        runs = {method: _load_run(method_rows[method], data_root) for method in ("base", "pgrr")}
        if not all(runs.values()):
            incomplete.append(
                {
                    "family_index": family_index,
                    "family": method_rows["base"]["family"],
                    "missing_methods": [method for method, run in runs.items() if run is None],
                }
            )
            continue
        base, pgrr = runs["base"], runs["pgrr"]
        assert base is not None and pgrr is not None
        row = method_rows["base"]
        pairs.append(
            {
                "benchmark_id": "pgrr_extension_v1_eight_family_pilot",
                "claim_boundary": "development_pair_only",
                "family_index": family_index,
                "family": row["family"],
                "scenario_id": row["scenario_id"],
                "scenario_sha256": row["scenario_sha256"],
                "seed": int(row["seed"]),
                "runs": {"base": base, "pgrr": pgrr},
                "paired_interpretation": _interpret(base, pgrr),
            }
        )

    outcome_counts = {
        method: dict(Counter(pair["runs"][method]["outcome"] for pair in pairs))
        for method in ("base", "pgrr")
    }
    return {
        "benchmark_id": "pgrr_extension_v1_eight_family_pilot",
        "claim_boundary": "incomplete_development_pilot_no_superiority_claim",
        "complete_pair_count": len(pairs),
        "planned_pair_count": len(grouped),
        "outcome_counts": outcome_counts,
        "pairs": pairs,
        "incomplete": incomplete,
    }


def write_results(report: dict[str, Any], output_root: Path) -> None:
    pair_root = output_root / "pair_results"
    pair_root.mkdir(parents=True, exist_ok=True)
    for pair in report["pairs"]:
        path = pair_root / f"f{pair['family_index']:02d}_{pair['family']}.json"
        text = json.dumps(pair, indent=2, sort_keys=True) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise FileExistsError(f"refusing to replace a different pair result: {path}")
        path.write_bytes(text.encode("utf-8"))
    summary_path = output_root / "minimal_pair_progress.json"
    summary_path.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.plan, args.data_root)
    write_results(report, args.output_root)
    keys = ("complete_pair_count", "planned_pair_count", "outcome_counts")
    print(json.dumps({key: report[key] for key in keys}, indent=2))


if __name__ == "__main__":
    main()
