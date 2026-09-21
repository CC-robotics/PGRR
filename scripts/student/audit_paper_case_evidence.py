#!/usr/bin/env python3
"""Audit evidence and rendering readiness for the eight qualitative cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified(path: Path, expected: str) -> bool:
    return path.is_file() and bool(expected) and sha256(path) == expected


def audit(
    results: pd.DataFrame,
    selected: pd.DataFrame,
    published_evidence: dict[str, object],
) -> tuple[dict[str, object], pd.DataFrame]:
    records: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    published_pair = str(published_evidence.get("pair_id", ""))
    artifacts = published_evidence.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}

    for case in selected.to_dict(orient="records"):
        pair_id = str(case["pair_id"])
        rows = results[(results["pair_id"] == pair_id) & results["source_policy"].isin(METHODS)]
        if len(rows) != len(METHODS):
            raise ValueError(f"{pair_id}: expected {len(METHODS)} method rows, found {len(rows)}")
        scenario_values = rows[["scenario_path", "scenario_sha256"]].drop_duplicates()
        if len(scenario_values) != 1:
            raise ValueError(f"{pair_id}: scenario binding differs across methods")
        scenario_rel = Path(str(scenario_values.iloc[0]["scenario_path"]))
        scenario_path = ROOT / scenario_rel
        scenario_hash = str(scenario_values.iloc[0]["scenario_sha256"])
        scenario_verified = verified(scenario_path, scenario_hash)

        raw_ready = True
        for row in rows.to_dict(orient="records"):
            episode_id = str(row["episode_id"])
            raw_path = ROOT / "data" / "raw" / f"{episode_id}.jsonl"
            metadata_path = ROOT / "data" / "raw" / f"{episode_id}.metadata.json"
            outcome_path = ROOT / "data" / "raw" / f"{episode_id}.outcome.json"
            row_raw_ready = all(
                (
                    verified(raw_path, str(row["raw_sha256"])),
                    verified(metadata_path, str(row["metadata_sha256"])),
                    verified(outcome_path, str(row["outcome_sha256"])),
                )
            )
            if row["source_policy"] in {"base", "pgrr"}:
                raw_ready = raw_ready and row_raw_ready
            metric_rows.append(
                {
                    "case_number": int(case["case_number"]),
                    "pair_id": pair_id,
                    "family": row["family"],
                    "density": row["density"],
                    "method": row["source_policy"],
                    "episode_id": episode_id,
                    "outcome": row["outcome"],
                    "episode_duration_s": row["episode_duration_s"],
                    "path_length_m": row["path_length_m"],
                    "min_human_distance_m": row["min_human_distance_m"],
                    "recovery_trigger_count": row["recovery_trigger_count"],
                    "terminal_goal_distance_m": row["terminal_physical_goal_distance_m"],
                    "raw_sidecars_locally_verified": row_raw_ready,
                }
            )

        published_media_ready = pair_id == published_pair
        if published_media_ready:
            for artifact in artifacts.values():
                if not isinstance(artifact, dict):
                    published_media_ready = False
                    break
                path = ROOT / "outputs" / "moderate" / "final" / str(artifact.get("path", ""))
                if not verified(path, str(artifact.get("sha256", ""))):
                    published_media_ready = False
                    break

        records.append(
            {
                "case_number": int(case["case_number"]),
                "pair_id": pair_id,
                "scenario_id": case["scenario_id"],
                "family": case["family"],
                "density": case["density"],
                "seed": int(case["seed"]),
                "scenario_verified": scenario_verified,
                "five_method_rows_complete": True,
                "results_table_ready": True,
                "new_trajectory_render_ready": raw_ready,
                "published_media_ready": published_media_ready,
            }
        )

    metrics = pd.DataFrame(metric_rows).sort_values(["case_number", "method"])
    payload: dict[str, object] = {
        "status": "read_only_frozen_evidence_audit",
        "case_count": len(records),
        "results_table_ready_count": sum(bool(item["results_table_ready"]) for item in records),
        "scenario_verified_count": sum(bool(item["scenario_verified"]) for item in records),
        "new_trajectory_render_ready_count": sum(
            bool(item["new_trajectory_render_ready"]) for item in records
        ),
        "published_media_ready_count": sum(
            bool(item["published_media_ready"]) for item in records
        ),
        "cases": records,
    }
    return payload, metrics


def render_markdown(payload: dict[str, object], metrics: pd.DataFrame) -> str:
    cases = payload["cases"]
    assert isinstance(cases, list)
    lines = [
        "# Eight-case evidence readiness audit",
        "",
        (
            f"Results-table evidence ready: {payload['results_table_ready_count']}/"
            f"{payload['case_count']}; "
            f"local scenario files verified: {payload['scenario_verified_count']}/"
            f"{payload['case_count']}; "
            f"new trajectory rendering ready: {payload['new_trajectory_render_ready_count']}/"
            f"{payload['case_count']}; existing SHA-verified publication media: "
            f"{payload['published_media_ready_count']}/{payload['case_count']}."
        ),
        "",
        (
            "| # | Family | Density | Base | PGRR | PGRR triggers | Scenario | "
            "New plot | Existing media |"
        ),
        "|---:|---|---|---|---|---:|---|---|---|",
    ]
    for case in cases:
        number = int(case["case_number"])
        subset = metrics[metrics["case_number"] == number].set_index("method")
        lines.append(
            f"| {number} | `{case['family']}` | {case['density']} | "
            f"{subset.loc['base', 'outcome']} | {subset.loc['pgrr', 'outcome']} | "
            f"{int(subset.loc['pgrr', 'recovery_trigger_count'])} | "
            f"{'yes' if case['scenario_verified'] else 'no'} | "
            f"{'yes' if case['new_trajectory_render_ready'] else 'no'} | "
            f"{'yes' if case['published_media_ready'] else 'no'} |"
        )
    lines += [
        "",
        (
            "All eight cases can support a frozen-results table. New trajectory plots "
            "require the original JSONL and sidecars; their absence must not be replaced "
            "by rerunning or reconstructing unrecorded paths. The one existing publication "
            "figure remains explicitly labeled as telemetry reconstruction."
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", type=Path, default=ROOT / "outputs/moderate/final/results.parquet"
    )
    parser.add_argument(
        "--selected",
        type=Path,
        default=ROOT / "outputs/student/paper_case_shortlist/eight_matched_cases.csv",
    )
    parser.add_argument(
        "--published-evidence",
        type=Path,
        default=ROOT / "outputs/moderate/final/matched_base_pgrr_evidence.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "outputs/student/paper_case_shortlist"
    )
    args = parser.parse_args()
    payload, metrics = audit(
        pd.read_parquet(args.results),
        pd.read_csv(args.selected),
        json.loads(args.published_evidence.read_text(encoding="utf-8")),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "case_evidence_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    metrics.to_csv(args.output_dir / "case_metrics_long.csv", index=False)
    (args.output_dir / "case_evidence_audit.md").write_text(
        render_markdown(payload, metrics), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
