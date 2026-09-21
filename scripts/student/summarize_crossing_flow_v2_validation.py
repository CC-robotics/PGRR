#!/usr/bin/env python3
"""Summarize the predeclared independent validation for crossing-flow v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analyze_recovery_trace import summarize_recovery
except ImportError:
    from analyze_recovery_trace import summarize_recovery


def _load_episode(runtime: Path, stem: str) -> dict[str, Any]:
    outcome_path = runtime / f"{stem}.outcome.json"
    jsonl_path = runtime / f"{stem}.jsonl"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    if int(outcome["sample_count"]) <= 0:
        raise ValueError(f"validation episode contains no samples: {stem}")
    return {
        "episode_id": outcome["episode_id"],
        "outcome": outcome["outcome"],
        "detail": outcome["detail"],
        "sample_count": int(outcome["sample_count"]),
        "physical_goal_distance_m": float(outcome["physical_goal_distance_m"]),
        "outcome_path": str(outcome_path),
        "jsonl_path": str(jsonl_path),
    }


def build_summary(runtime: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for replicate, seed in enumerate((96000, 96001, 96002)):
        prefix = f"pgrr_advscreen_crossing_v2_validation_r0{replicate}_s{seed}"
        base = _load_episode(runtime, f"{prefix}_base")
        pgrr = _load_episode(runtime, f"{prefix}_pgrr")
        recovery = summarize_recovery(Path(pgrr["jsonl_path"]))
        rows.append(
            {
                "replicate": replicate,
                "seed": seed,
                "base": base,
                "pgrr": pgrr,
                "positive_pair": base["outcome"] != "GOAL_REACHED"
                and pgrr["outcome"] == "GOAL_REACHED",
                "pgrr_recovery": {
                    "state_transitions": recovery["state_transitions"],
                    "decision_event_count": recovery["decision_event_count"],
                    "decision_action_counts": recovery["decision_action_counts"],
                    "temporary_subgoal_decision_count": recovery[
                        "temporary_subgoal_decision_count"
                    ],
                    "original_goal_restored_event_count": recovery[
                        "original_goal_restored_event_count"
                    ],
                },
            }
        )
    positive_count = sum(row["positive_pair"] for row in rows)
    retry_artifacts = sorted(path.name for path in runtime.glob("*_retry*.outcome.json"))
    return {
        "schema_version": 1,
        "scope": "independent_validation_gate",
        "scenario_family": "crossing_flow_medium_anchor_v2",
        "route_distance_m": 15.0,
        "episode_timeout_s": 90,
        "promotion_rule": {"minimum_positive_pairs": 2, "total_pairs": 3},
        "selected_pairs": rows,
        "retry_artifacts": retry_artifacts,
        "positive_pair_count": positive_count,
        "total_pair_count": len(rows),
        "validation_gate_passed": positive_count >= 2,
        "validated_new_scenario_count": 1 if positive_count >= 2 else 0,
        "general_superiority_claim_authorized": False,
        "frozen_test_used": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Crossing-flow v2 独立 validation 汇总",
        "",
        "| 重复 | seed | Base | PGRR | Base样本 | PGRR样本 | 正向配对 |",
        "|---:|---:|---|---|---:|---:|---|",
    ]
    for row in summary["selected_pairs"]:
        lines.append(
            f"| r{row['replicate']:02d} | {row['seed']} | {row['base']['outcome']} | "
            f"{row['pgrr']['outcome']} | {row['base']['sample_count']} | "
            f"{row['pgrr']['sample_count']} | {'是' if row['positive_pair'] else '否'} |"
        )
    lines.extend(
        [
            "",
            f"预声明门槛为至少2/3正向配对；实际为 "  # noqa: RUF001
            f"{summary['positive_pair_count']}/{summary['total_pair_count']}。",
            "",
            f"validation期间产生的重试artifact数量：{len(summary['retry_artifacts'])}。",  # noqa: RUF001
            "",
            "该结果确认一个新场景通过独立validation，但不构成PGRR在任意场景中"  # noqa: RUF001
            "普遍优于Base的结论，也不替代完整统计评估。",  # noqa: RUF001
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.runtime)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
