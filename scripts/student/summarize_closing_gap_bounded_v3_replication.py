#!/usr/bin/env python3
"""Summarize the predeclared bounded closing-gap v3 train replication gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analyze_recovery_trace import summarize_recovery
except ImportError:
    from analyze_recovery_trace import summarize_recovery


RUNS = (
    {
        "replicate": 0,
        "seed": 98200,
        "base_stem": "pgrr_priority_closinggap_v3_train_s98200_base",
        "pgrr_stem": "pgrr_priority_closinggap_v3_train_s98200_pgrr",
        "source": "screen",
    },
    {
        "replicate": 1,
        "seed": 98201,
        "base_stem": "pgrr_priority_closinggap_v3_train_r01_s98201_base",
        "pgrr_stem": "pgrr_priority_closinggap_v3_train_r01_s98201_pgrr",
        "source": "replication",
    },
    {
        "replicate": 2,
        "seed": 98202,
        "base_stem": "pgrr_priority_closinggap_v3_train_r02_s98202_base",
        "pgrr_stem": "pgrr_priority_closinggap_v3_train_r02_s98202_pgrr",
        "source": "replication",
    },
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _episode(runtime: Path, stem: str) -> dict[str, Any]:
    outcome_path = runtime / f"{stem}.outcome.json"
    jsonl_path = runtime / f"{stem}.jsonl"
    outcome = _load(outcome_path)
    return {
        "episode_id": outcome["episode_id"],
        "outcome": outcome["outcome"],
        "detail": outcome["detail"],
        "sample_count": int(outcome["sample_count"]),
        "physical_goal_distance_m": outcome.get("physical_goal_distance_m"),
        "scenario_events": outcome.get("scenario_events", []),
        "outcome_path": str(outcome_path),
        "jsonl_path": str(jsonl_path),
    }


def _complete_two_actor_event_chain(events: list[dict[str, Any]]) -> bool:
    by_actor: dict[str, list[str]] = {}
    for event in events:
        by_actor.setdefault(str(event["actor_name"]), []).append(str(event["transition"]))
    expected = ["pre_event_to_active_event", "active_event_to_released"]
    return len(by_actor) == 2 and all(chain == expected for chain in by_actor.values())


def build_summary(screen_runtime: Path, replication_runtime: Path) -> dict[str, Any]:
    rows = []
    for run in RUNS:
        runtime = screen_runtime if run["source"] == "screen" else replication_runtime
        base = _episode(runtime, run["base_stem"])
        pgrr = _episode(runtime, run["pgrr_stem"])
        recovery = summarize_recovery(Path(pgrr["jsonl_path"]))
        event_complete = _complete_two_actor_event_chain(pgrr["scenario_events"])
        restored = recovery["original_goal_restored_event_count"] >= 1
        positive = base["outcome"] != "GOAL_REACHED" and pgrr["outcome"] == "GOAL_REACHED"
        rows.append(
            {
                "replicate": run["replicate"],
                "seed": run["seed"],
                "base": base,
                "pgrr": pgrr,
                "positive_pair": positive,
                "pgrr_two_actor_event_chain_complete": event_complete,
                "pgrr_original_goal_restored": restored,
                "qualifying_pair": positive and event_complete and restored,
                "pgrr_recovery": {
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
    return {
        "schema_version": 1,
        "scope": "train_only_replication_gate",
        "family": "closing_gap_multi_pedestrian",
        "variant_id": "closing_gap_bounded_release_v3",
        "route_distance_m": 15.0,
        "episode_timeout_s": 90,
        "promotion_rule": {"minimum_qualifying_pairs": 2, "total_pairs": 3},
        "selected_pairs": rows,
        "qualifying_pair_count": qualifying,
        "total_pair_count": len(rows),
        "train_replication_gate_passed": qualifying >= 2,
        "independent_validation_complete": False,
        "paper_claim_authorized": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 有限时间多行人收口 v3 训练内复现汇总",
        "",
        "| 重复 | seed | Base | PGRR | 双行人事件链 | 原目标恢复 | 合格配对 |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for row in summary["selected_pairs"]:
        lines.append(
            f"| r{row['replicate']:02d} | {row['seed']} | {row['base']['outcome']} | "
            f"{row['pgrr']['outcome']} | "
            f"{'完整' if row['pgrr_two_actor_event_chain_complete'] else '不完整'} | "
            f"{'是' if row['pgrr_original_goal_restored'] else '否'} | "
            f"{'是' if row['qualifying_pair'] else '否'} |"
        )
    lines.extend(
        [
            "",
            f"预声明门槛为至少 2/3 合格配对；实际为 "  # noqa: RUF001
            f"{summary['qualifying_pair_count']}/{summary['total_pair_count']}，"  # noqa: RUF001
            f"训练内复现门槛{'通过' if summary['train_replication_gate_passed'] else '未通过'}。",
            "",
            "这里只是训练场景复现，尚未完成独立 validation，"  # noqa: RUF001
            "也未授权论文结论。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-runtime", type=Path, required=True)
    parser.add_argument("--replication-runtime", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.screen_runtime, args.replication_runtime)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
