#!/usr/bin/env python3
"""Summarize independent validation for goal-approach lateral v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analyze_recovery_trace import summarize_recovery
except ImportError:
    from analyze_recovery_trace import summarize_recovery


SEEDS = (98100, 98101, 98102)


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
        "scenario_events": outcome.get("scenario_events", []),
        "outcome_path": str(outcome_path),
        "jsonl_path": str(jsonl_path),
    }


def build_summary(runtime: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for replicate, seed in enumerate(SEEDS):
        prefix = f"pgrr_priority_goalapproach_v2_validation_r0{replicate}_s{seed}"
        base = _load_episode(runtime, f"{prefix}_base")
        pgrr = _load_episode(runtime, f"{prefix}_pgrr")
        recovery = summarize_recovery(Path(pgrr["jsonl_path"]))
        event_chain = [event["transition"] for event in pgrr["scenario_events"]]
        event_complete = event_chain == [
            "pre_event_to_active_event",
            "active_event_to_released",
        ]
        restored = recovery["original_goal_restored_event_count"] >= 1
        positive = base["outcome"] != "GOAL_REACHED" and pgrr["outcome"] == "GOAL_REACHED"
        rows.append(
            {
                "replicate": replicate,
                "seed": seed,
                "base": base,
                "pgrr": pgrr,
                "positive_pair": positive,
                "pgrr_event_chain_complete": event_complete,
                "pgrr_original_goal_restored": restored,
                "qualifying_pair": positive and event_complete and restored,
                "pgrr_recovery": {
                    "state_transitions": recovery["state_transitions"],
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
    qualifying = sum(row["qualifying_pair"] for row in rows)
    retry_artifacts = sorted(path.name for path in runtime.glob("*_retry*.outcome.json"))
    return {
        "schema_version": 1,
        "scope": "independent_validation_gate",
        "family": "goal_approach_lateral_interruption",
        "variant_id": "goal_approach_lateral_one_shot_v2",
        "route_distance_m": 15.0,
        "episode_timeout_s": 90,
        "promotion_rule": {"minimum_qualifying_pairs": 2, "total_pairs": 3},
        "selected_pairs": rows,
        "retry_artifacts": retry_artifacts,
        "qualifying_pair_count": qualifying,
        "total_pair_count": len(rows),
        "validation_gate_passed": qualifying >= 2,
        "validated_new_scenario_count": 1 if qualifying >= 2 else 0,
        "general_superiority_claim_authorized": False,
        "frozen_test_used": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 目标附近侧向干扰 v2 独立 validation 汇总",
        "",
        "| 重复 | seed | Base | PGRR | 事件链 | 原目标恢复 | 合格配对 |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for row in summary["selected_pairs"]:
        lines.append(
            f"| r{row['replicate']:02d} | {row['seed']} | {row['base']['outcome']} | "
            f"{row['pgrr']['outcome']} | "
            f"{'完整' if row['pgrr_event_chain_complete'] else '不完整'} | "
            f"{'是' if row['pgrr_original_goal_restored'] else '否'} | "
            f"{'是' if row['qualifying_pair'] else '否'} |"
        )
    lines.extend(
        [
            "",
            f"预声明门槛为至少 2/3 合格配对；实际为 "  # noqa: RUF001
            f"{summary['qualifying_pair_count']}/{summary['total_pair_count']}。",
            "",
            f"有效实验的基础设施重试数：{len(summary['retry_artifacts'])}。",  # noqa: RUF001
            "",
            "该结果确认一个新场景通过独立 validation，但不单独授权一般优越性或"  # noqa: RUF001
            "统计显著性结论。",
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
