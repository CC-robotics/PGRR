#!/usr/bin/env python3
"""Diagnose motion and original-goal progress in the eight-family PGRR pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any

STATE_NAMES = {
    0: "NORMAL",
    1: "PENDING_RECOVERY",
    2: "RECOVERY",
    3: "REJOIN",
    4: "EMERGENCY_STOP",
    5: "FAILED",
    6: "SUCCEEDED",
}
FAILURE_NAMES = ("COLLISION_RISK", "FREEZE", "OSCILLATION", "DEADLOCK")
ACTION_NAMES = {
    **{index: f"SUBGOAL_{index}" for index in range(21)},
    21: "WAIT",
    22: "BACKUP",
    23: "REPLAN",
    24: "CONTINUE",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _original_goal_distance(row: dict[str, Any], goal_xy: tuple[float, float]) -> float:
    pose = row["robot_pose"]
    return math.hypot(float(pose[0]) - goal_xy[0], float(pose[1]) - goal_xy[1])


def _path_length(rows: list[dict[str, Any]]) -> float:
    poses = [row["robot_pose"] for row in rows]
    return sum(
        math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
        for a, b in pairwise(poses)
    )


def _state_durations(rows: list[dict[str, Any]]) -> dict[str, float]:
    durations: defaultdict[str, float] = defaultdict(float)
    for current, following in pairwise(rows):
        state = int(current.get("recovery_state", 0))
        delta = max(0.0, float(following["timestamp"]) - float(current["timestamp"]))
        durations[STATE_NAMES.get(state, f"UNKNOWN_{state}")] += delta
    return {name: round(value, 3) for name, value in sorted(durations.items())}


def _recovery_cycles(
    rows: list[dict[str, Any]], distances: list[float]
) -> list[dict[str, Any]]:
    cycles: list[dict[str, Any]] = []
    start: int | None = None
    for index, row in enumerate(rows):
        state = int(row.get("recovery_state", 0))
        previous_state = int(rows[index - 1].get("recovery_state", 0)) if index else 0
        if state != 0 and previous_state == 0:
            start = index
        if state == 0 and previous_state != 0 and start is not None:
            end = index
            cycles.append(_cycle_summary(rows, distances, start, end, completed=True))
            start = None
    if start is not None:
        cycles.append(_cycle_summary(rows, distances, start, len(rows) - 1, completed=False))
    return cycles


def _cycle_summary(
    rows: list[dict[str, Any]],
    distances: list[float],
    start: int,
    end: int,
    *,
    completed: bool,
) -> dict[str, Any]:
    progress = distances[start] - distances[end]
    action_sequence: list[str] = []
    reason_sequence: list[str] = []
    decision_events: list[dict[str, str]] = []
    previous_action: int | None = None
    previous_reason: str | None = None
    previous_signature: tuple[int, str] | None = None
    for row in rows[start : end + 1]:
        action = int(row.get("recovery_action", 24))
        reason = str(row.get("recovery_reason", "")) or "empty"
        signature = (action, reason)
        if signature != previous_signature:
            if "bc_onnx confidence=" in reason:
                origin = "LEARNED_POLICY"
            elif reason.startswith("emergency_"):
                origin = "EMERGENCY_GUARD"
            elif reason.startswith("safety_clear_"):
                origin = "SAFETY_CLEAR"
            elif reason in {"original_goal_restored", "recovery_action_complete"}:
                origin = "RECOVERY_LIFECYCLE"
            else:
                origin = "OTHER"
            decision_events.append(
                {
                    "action": ACTION_NAMES.get(action, f"UNKNOWN_{action}"),
                    "origin": origin,
                }
            )
            previous_signature = signature
        if action != previous_action:
            action_sequence.append(ACTION_NAMES.get(action, f"UNKNOWN_{action}"))
            previous_action = action
        if reason != previous_reason:
            reason_sequence.append(reason)
            previous_reason = reason
    failure = [float(value) for value in rows[start].get("failure_prediction", [])]
    if failure and max(failure) > 0.0:
        dominant_failure = FAILURE_NAMES[max(range(len(failure)), key=failure.__getitem__)]
    else:
        dominant_failure = "NO_POSITIVE_FAILURE_SCORE"
    return {
        "start_sample": start,
        "end_sample": end,
        "duration_s": round(float(rows[end]["timestamp"]) - float(rows[start]["timestamp"]), 3),
        "original_goal_progress_m": round(progress, 6),
        "completed_rejoin": completed,
        "dominant_failure_at_trigger": dominant_failure,
        "failure_prediction_at_trigger": failure,
        "action_sequence": action_sequence,
        "action_signature": ">".join(action_sequence),
        "reason_sequence": reason_sequence,
        "decision_events": decision_events,
        "learned_decision_count": sum(
            event["origin"] == "LEARNED_POLICY" for event in decision_events
        ),
    }


def diagnose_episode(path: Path, expected_sha256: str) -> dict[str, Any]:
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"raw log hash mismatch: {path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) < 2:
        raise ValueError(f"episode has fewer than two samples: {path}")
    goal = rows[0]["goal"]
    goal_xy = (float(goal[0]), float(goal[1]))
    distances = [_original_goal_distance(row, goal_xy) for row in rows]
    durations = _state_durations(rows)
    cycles = _recovery_cycles(rows, distances)
    elapsed = float(rows[-1]["timestamp"]) - float(rows[0]["timestamp"])
    recovery_time = sum(value for name, value in durations.items() if name != "NORMAL")
    stalled_intervals = 0
    for row in rows[:-1]:
        velocity = row.get("robot_velocity") or [0.0, 0.0]
        if abs(float(velocity[0])) < 0.05:
            stalled_intervals += 1
    return {
        "raw_jsonl": str(path),
        "raw_sha256_verified": True,
        "sample_count": len(rows),
        "elapsed_s": round(elapsed, 3),
        "initial_original_goal_distance_m": round(distances[0], 6),
        "final_original_goal_distance_m": round(distances[-1], 6),
        "minimum_original_goal_distance_m": round(min(distances), 6),
        "net_original_goal_progress_m": round(distances[0] - distances[-1], 6),
        "path_length_m": round(_path_length(rows), 6),
        "state_duration_s": durations,
        "recovery_time_s": round(recovery_time, 3),
        "recovery_time_fraction": round(recovery_time / elapsed, 6) if elapsed > 0 else 0.0,
        "low_linear_speed_sample_fraction": round(stalled_intervals / (len(rows) - 1), 6),
        "recovery_cycle_count": len(cycles),
        "completed_rejoin_count": sum(cycle["completed_rejoin"] for cycle in cycles),
        "positive_progress_cycle_count": sum(
            cycle["original_goal_progress_m"] > 0 for cycle in cycles
        ),
        "nonpositive_progress_cycle_count": sum(
            cycle["original_goal_progress_m"] <= 0 for cycle in cycles
        ),
        "recovery_cycles": cycles,
    }


def diagnose_pilot(progress_path: Path, data_root: Path) -> dict[str, Any]:
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    episodes = []
    for pair in progress["pairs"]:
        run = pair["runs"]["pgrr"]
        episode_id = run["selected_attempt_id"]
        path = data_root / f"{episode_id}.jsonl"
        diagnosis = diagnose_episode(path, run["artifact_sha256"]["raw_jsonl"])
        diagnosis.update(
            {
                "family_index": pair["family_index"],
                "family": pair["family"],
                "episode_id": episode_id,
                "outcome": run["outcome"],
            }
        )
        episodes.append(diagnosis)

    total_elapsed = sum(item["elapsed_s"] for item in episodes)
    all_cycles = [
        {"family": item["family"], **cycle}
        for item in episodes
        for cycle in item["recovery_cycles"]
    ]
    positive_cycles = [cycle for cycle in all_cycles if cycle["original_goal_progress_m"] > 0]
    nonpositive_cycles = [cycle for cycle in all_cycles if cycle["original_goal_progress_m"] <= 0]

    def action_counts(cycles: list[dict[str, Any]]) -> dict[str, int]:
        return dict(
            sorted(
                Counter(
                    action for cycle in cycles for action in cycle["action_sequence"]
                ).items()
            )
        )

    def origin_action_counts(
        cycles: list[dict[str, Any]], origin: str
    ) -> dict[str, int]:
        return dict(
            sorted(
                Counter(
                    event["action"]
                    for cycle in cycles
                    for event in cycle["decision_events"]
                    if event["origin"] == origin
                ).items()
            )
        )

    positive_learned_actions = origin_action_counts(positive_cycles, "LEARNED_POLICY")
    nonpositive_learned_actions = origin_action_counts(
        nonpositive_cycles, "LEARNED_POLICY"
    )
    all_learned_action_count = sum(positive_learned_actions.values()) + sum(
        nonpositive_learned_actions.values()
    )
    wait_backup_learned_count = sum(
        positive_learned_actions.get(action, 0)
        + nonpositive_learned_actions.get(action, 0)
        for action in ("WAIT", "BACKUP")
    )

    aggregate = {
        "episode_count": len(episodes),
        "raw_hashes_verified": all(item["raw_sha256_verified"] for item in episodes),
        "positive_net_progress_episode_count": sum(
            item["net_original_goal_progress_m"] > 0 for item in episodes
        ),
        "nonpositive_net_progress_episode_count": sum(
            item["net_original_goal_progress_m"] <= 0 for item in episodes
        ),
        "total_recovery_cycle_count": sum(item["recovery_cycle_count"] for item in episodes),
        "completed_rejoin_count": sum(item["completed_rejoin_count"] for item in episodes),
        "positive_progress_cycle_count": sum(
            item["positive_progress_cycle_count"] for item in episodes
        ),
        "nonpositive_progress_cycle_count": sum(
            item["nonpositive_progress_cycle_count"] for item in episodes
        ),
        "time_weighted_recovery_fraction": round(
            sum(item["recovery_time_s"] for item in episodes) / total_elapsed, 6
        ),
        "mean_low_linear_speed_sample_fraction": round(
            sum(item["low_linear_speed_sample_fraction"] for item in episodes) / len(episodes),
            6,
        ),
        "outcome_counts": dict(sorted(Counter(item["outcome"] for item in episodes).items())),
        "cycle_trigger_failure_counts": dict(
            sorted(Counter(cycle["dominant_failure_at_trigger"] for cycle in all_cycles).items())
        ),
        "positive_cycle_action_event_counts": action_counts(positive_cycles),
        "nonpositive_cycle_action_event_counts": action_counts(nonpositive_cycles),
        "nonpositive_cycle_signature_counts": dict(
            sorted(Counter(cycle["action_signature"] for cycle in nonpositive_cycles).items())
        ),
        "trigger_progress_counts": dict(
            sorted(
                Counter(
                    f"{cycle['dominant_failure_at_trigger']}|"
                    f"{'positive' if cycle['original_goal_progress_m'] > 0 else 'nonpositive'}"
                    for cycle in all_cycles
                ).items()
            )
        ),
        "cycles_with_learned_decision": sum(
            cycle["learned_decision_count"] > 0 for cycle in all_cycles
        ),
        "cycles_without_learned_decision": sum(
            cycle["learned_decision_count"] == 0 for cycle in all_cycles
        ),
        "positive_cycle_learned_action_counts": positive_learned_actions,
        "nonpositive_cycle_learned_action_counts": nonpositive_learned_actions,
        "learned_action_event_count": all_learned_action_count,
        "learned_wait_backup_event_count": wait_backup_learned_count,
        "learned_wait_backup_event_fraction": round(
            wait_backup_learned_count / all_learned_action_count, 6
        ),
        "learned_presence_progress_counts": dict(
            sorted(
                Counter(
                    f"{'with' if cycle['learned_decision_count'] > 0 else 'without'}_learned|"
                    f"{'positive' if cycle['original_goal_progress_m'] > 0 else 'nonpositive'}"
                    for cycle in all_cycles
                ).items()
            )
        ),
        "positive_cycle_emergency_action_counts": origin_action_counts(
            positive_cycles, "EMERGENCY_GUARD"
        ),
        "nonpositive_cycle_emergency_action_counts": origin_action_counts(
            nonpositive_cycles, "EMERGENCY_GUARD"
        ),
    }
    return {
        "benchmark_id": progress["benchmark_id"],
        "claim_boundary": "development_diagnostic_only_no_superiority_claim",
        "aggregate": aggregate,
        "episodes": episodes,
    }


def write_outputs(
    report: dict[str, Any],
    json_path: Path,
    csv_path: Path,
    cycle_csv_path: Path,
    md_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = [
        "family_index",
        "family",
        "episode_id",
        "outcome",
        "initial_original_goal_distance_m",
        "final_original_goal_distance_m",
        "minimum_original_goal_distance_m",
        "net_original_goal_progress_m",
        "path_length_m",
        "recovery_time_s",
        "recovery_time_fraction",
        "low_linear_speed_sample_fraction",
        "recovery_cycle_count",
        "completed_rejoin_count",
        "positive_progress_cycle_count",
        "nonpositive_progress_cycle_count",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["episodes"])

    cycle_fields = [
        "family",
        "cycle_index",
        "dominant_failure_at_trigger",
        "duration_s",
        "original_goal_progress_m",
        "progress_class",
        "completed_rejoin",
        "action_signature",
        "reason_signature",
        "learned_decision_count",
    ]
    with cycle_csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=cycle_fields)
        writer.writeheader()
        for episode in report["episodes"]:
            for cycle_index, cycle in enumerate(episode["recovery_cycles"], start=1):
                writer.writerow(
                    {
                        "family": episode["family"],
                        "cycle_index": cycle_index,
                        "dominant_failure_at_trigger": cycle[
                            "dominant_failure_at_trigger"
                        ],
                        "duration_s": cycle["duration_s"],
                        "original_goal_progress_m": cycle["original_goal_progress_m"],
                        "progress_class": (
                            "positive" if cycle["original_goal_progress_m"] > 0 else "nonpositive"
                        ),
                        "completed_rejoin": cycle["completed_rejoin"],
                        "action_signature": cycle["action_signature"],
                        "reason_signature": ">".join(cycle["reason_sequence"]),
                        "learned_decision_count": cycle["learned_decision_count"],
                    }
                )

    aggregate = report["aggregate"]
    lines = [
        "# Eight-family PGRR recovery-progress diagnostic",
        "",
        "Development diagnostic only; this is not final evaluation evidence.",
        "",
        "| Family | Outcome | Net goal progress (m) | Recovery time | Cycles | Rejoins |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["episodes"]:
        lines.append(
            f"| {item['family']} | {item['outcome']} | "
            f"{item['net_original_goal_progress_m']:.3f} | "
            f"{item['recovery_time_fraction']:.1%} | {item['recovery_cycle_count']} | "
            f"{item['completed_rejoin_count']} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            f"- Raw hashes verified: {aggregate['raw_hashes_verified']}",
            "- Episodes with positive/nonpositive net progress: "
            f"{aggregate['positive_net_progress_episode_count']}/"
            f"{aggregate['nonpositive_net_progress_episode_count']}",
            f"- Recovery cycles: {aggregate['total_recovery_cycle_count']}",
            f"- Completed rejoins: {aggregate['completed_rejoin_count']}",
            "- Cycles with positive/nonpositive goal progress: "
            f"{aggregate['positive_progress_cycle_count']}/"
            f"{aggregate['nonpositive_progress_cycle_count']}",
            "- Time-weighted recovery-state fraction: "
            f"{aggregate['time_weighted_recovery_fraction']:.1%}",
            "- Mean low-linear-speed sample fraction: "
            f"{aggregate['mean_low_linear_speed_sample_fraction']:.1%}",
            "- Trigger failure counts: "
            f"{json.dumps(aggregate['cycle_trigger_failure_counts'], sort_keys=True)}",
            "- Positive-cycle action events: "
            f"{json.dumps(aggregate['positive_cycle_action_event_counts'], sort_keys=True)}",
            "- Nonpositive-cycle action events: "
            f"{json.dumps(aggregate['nonpositive_cycle_action_event_counts'], sort_keys=True)}",
            "- Trigger/progress counts: "
            f"{json.dumps(aggregate['trigger_progress_counts'], sort_keys=True)}",
            "- Cycles with/without a learned-policy decision: "
            f"{aggregate['cycles_with_learned_decision']}/"
            f"{aggregate['cycles_without_learned_decision']}",
            "- Learned actions in positive cycles: "
            f"{json.dumps(aggregate['positive_cycle_learned_action_counts'], sort_keys=True)}",
            "- Learned actions in nonpositive cycles: "
            f"{json.dumps(aggregate['nonpositive_cycle_learned_action_counts'], sort_keys=True)}",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--cycle-csv-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose_pilot(args.progress, args.data_root)
    write_outputs(
        report,
        args.json_output,
        args.csv_output,
        args.cycle_csv_output,
        args.markdown_output,
    )
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
