from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate/merge_validation_results.py"
SPEC = importlib.util.spec_from_file_location("pgrr_merge_validation_results", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

COMMIT = "a" * 40
ARENA_COMMIT = "b" * 40
SPLIT_SHA256 = "c" * 64


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _row(method: str, condition: int, task_index: int) -> dict[str, Any]:
    family = MODULE.moderate_artifacts.FAMILY_ORDER[condition % 8]
    density = MODULE.moderate_artifacts.DENSITY_ORDER[(condition // 8) % 3]
    replicate = condition // 24
    seed = 77_000 + condition
    scenario_id = f"{family}_{density}_validation_moderate_v6_r{replicate:02d}_s{seed:05d}"
    pair_id = f"{scenario_id}_seed{seed}"
    episode_id = f"{scenario_id}_eval_{method}_r{'1' * 12}_a0_dwb"
    outcome = "GOAL_REACHED" if condition % 4 else "COLLISION"
    return {
        "task_index": task_index,
        "episode_id": episode_id,
        "logical_episode_id": episode_id,
        "pair_id": pair_id,
        "scenario_id": scenario_id,
        "scenario": scenario_id,
        "scenario_path": f"scenarios/generated/moderate_v6/arena/map_empty/{scenario_id}.json",
        "scenario_sha256": _sha256_text(f"scenario-{condition}"),
        "family": family,
        "density": density,
        "seed": seed,
        "replicate": replicate,
        "split": "validation",
        "map": "map_empty",
        "map_id": "map_empty",
        "robot_start": "[5.0,12.0,0.0]",
        "robot_goal": "[26.0,12.0,0.0]",
        "pedestrian_config_hash": _sha256_text(f"pedestrians-{condition}"),
        "source_policy": method,
        "method": method,
        "planner_id": "dwb",
        "arena_commit": ARENA_COMMIT,
        "project_commit": COMMIT,
        "timeout_s": 240.0,
        "recovery_tau_on_override": "",
        "outcome": outcome,
        "included_in_algorithm_metrics": True,
        "min_human_distance_m": 1.5,
        "physical_attempt_count": 1,
    }


def _frame(methods: tuple[str, ...]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    task_index = 0
    for method in methods:
        for condition in range(MODULE.EXPECTED_CONDITIONS):
            rows.append(_row(method, condition, task_index))
            task_index += 1
    return pd.DataFrame(rows)


def _run_manifest(frame: pd.DataFrame, run_id: str) -> dict[str, Any]:
    methods = list(dict.fromkeys(frame["source_policy"].astype(str)))
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                "task_index": int(row["task_index"]),
                "episode_id": row["episode_id"],
                "scenario_id": row["scenario_id"],
                "replicate": int(row["replicate"]),
                "method": row["source_policy"],
                "status": "complete",
                "attempts": [
                    {
                        "attempt": 0,
                        "episode_id": row["episode_id"],
                        "outcome": row["outcome"],
                    }
                ],
            }
        )
    return {
        "schema_version": 1,
        "run_id": run_id,
        "project_commit": str(frame["project_commit"].iloc[0]),
        "split": "validation",
        "split_manifest": "scenarios/splits/moderate_v6_validation.yaml",
        "split_manifest_sha256": SPLIT_SHA256,
        "episode_manifest": f"outputs/{run_id}/episode_manifest.parquet",
        "timeout_s": float(frame["timeout_s"].iloc[0]),
        "recovery_tau_on_override": str(frame["recovery_tau_on_override"].iloc[0]),
        "requested_jobs": 6,
        "effective_jobs": 6,
        "methods": methods,
        "high_density_methods": [],
        "expected_task_count": len(frame),
        "completed_task_count": len(frame),
        "worker_errors": [],
        "results": records,
    }


def _write_source(
    directory: Path,
    frame: pd.DataFrame,
    run_id: str,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    results_path = directory / "results.parquet"
    run_path = directory / "run_manifest.json"
    frame.to_parquet(results_path, index=False)
    run_path.write_text(
        json.dumps(_run_manifest(frame, run_id), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results_path, run_path


def _sources(tmp_path: Path) -> tuple[tuple[Path, Path], tuple[Path, Path]]:
    base = _write_source(tmp_path / "base", _frame(("base",)), "1" * 12)
    methods = _write_source(
        tmp_path / "methods",
        _frame(("standard", "heuristic", "bc_uniform", "pgrr")),
        "2" * 12,
    )
    return base, methods


def _load_bundles(
    sources: tuple[tuple[Path, Path], tuple[Path, Path]],
) -> list[Any]:
    return [MODULE.load_input_bundle(results, run) for results, run in sources]


def _rewrite_source(
    source: tuple[Path, Path],
    frame: pd.DataFrame,
    *,
    run_id: str,
) -> None:
    results_path, run_path = source
    frame.to_parquet(results_path, index=False)
    run_path.write_text(
        json.dumps(_run_manifest(frame, run_id), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_first_pass_attempt_manifest(
    path: Path,
    frame: pd.DataFrame,
    *,
    run_id: str,
    error_count: int = 33,
) -> Path:
    payload = _run_manifest(frame, run_id)
    error_indices = list(range(len(frame) - error_count, len(frame)))
    for index in error_indices:
        record = payload["results"][index]
        record["status"] = "error"
        record["episode_id"] = None
        record["attempts"] = []
        record["error"] = (
            "RuntimeError: episode command returned 1 without outcome: "
            f"{frame.iloc[index]['episode_id']}"
        )
    payload["completed_task_count"] = len(frame) - error_count
    payload["requested_jobs"] = 8
    payload["effective_jobs"] = 8
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_merge_writes_complete_atomic_results_and_distinct_provenance(tmp_path: Path) -> None:
    base, methods = _sources(tmp_path)
    # Reverse CLI order to prove output and merge-manifest ordering is canonical.
    bundles = _load_bundles((methods, base))
    output = tmp_path / "combined/results.parquet"
    merge_manifest = tmp_path / "combined/merge_manifest.json"

    merged, payload = MODULE.write_merged_outputs(
        bundles=bundles,
        output_path=output,
        merge_manifest_path=merge_manifest,
        project_root=tmp_path,
    )

    assert len(merged) == MODULE.EXPECTED_ROWS == 360
    assert merged.groupby("source_policy").size().to_dict() == {
        method: 72 for method in MODULE.METHODS
    }
    first_pair = merged.loc[merged["pair_id"] == merged["pair_id"].iloc[0], "source_policy"]
    assert first_pair.tolist() == list(MODULE.METHODS)
    assert output.is_file() and merge_manifest.is_file()
    assert not list(output.parent.glob("*.tmp"))

    stored = json.loads(merge_manifest.read_text(encoding="utf-8"))
    assert stored == payload
    assert stored["artifact_type"] == "validation_results_merge"
    assert stored["split"] == "validation"
    assert stored["project_commit"] == COMMIT
    assert stored["methods"] == list(MODULE.METHODS)
    assert stored["row_count"] == 360
    assert stored["condition_count"] == 72
    assert stored["source_run_ids"] == ["1" * 12, "2" * 12]
    assert [record["row_count"] for record in stored["inputs"]] == [72, 288]
    assert [record["methods"] for record in stored["inputs"]] == [
        ["base"],
        ["standard", "heuristic", "bc_uniform", "pgrr"],
    ]
    assert stored["provenance_policy"] == {
        "synthetic_run_manifest_created": False,
        "source_run_manifests_preserved": True,
        "source_run_manifests_are_final_completeness_snapshots": True,
        "source_run_manifests_claim_complete_attempt_history": False,
        "attempt_manifest_records_are_not_algorithm_outcomes": True,
        "condition_filtering": False,
    }
    assert stored["technical_attempt_provenance"] == {
        "attempt_manifest_count": 0,
        "no_outcome_error_record_count": 0,
        "unique_no_outcome_error_record_count": 0,
        "other_error_record_count": 0,
        "algorithm_outcomes_added_to_results": 0,
        "history_status": "not_supplied",
    }
    assert stored["output"]["results_sha256"] == MODULE.sha256_file(output)
    for record in stored["inputs"]:
        assert len(record["results_sha256"]) == 64
        assert len(record["run_manifest_sha256"]) == 64
    assert "run_manifest" not in stored


def test_cli_uses_sibling_real_run_manifests_by_default(tmp_path: Path) -> None:
    base, methods = _sources(tmp_path)
    output = tmp_path / "combined/results.parquet"
    merge_manifest = tmp_path / "combined/provenance.json"
    exit_code = MODULE.main(
        [
            "--results",
            str(base[0]),
            "--results",
            str(methods[0]),
            "--output",
            str(output),
            "--merge-manifest",
            str(merge_manifest),
        ]
    )
    assert exit_code == 0
    assert len(pd.read_parquet(output)) == 360


def test_merge_preserves_first_pass_no_outcome_errors_as_nonalgorithm_provenance(
    tmp_path: Path,
) -> None:
    base, methods = _sources(tmp_path)
    bundles = _load_bundles((base, methods))
    methods_frame = pd.read_parquet(methods[0])
    attempt_path = _write_first_pass_attempt_manifest(
        tmp_path / "methods/attempt_manifests/run_manifest_jobs8_first_pass.json",
        methods_frame,
        run_id="2" * 12,
    )
    evidence = MODULE.load_attempt_manifest(attempt_path, bundles)
    assert evidence.status_counts == {"complete": 255, "error": 33}
    assert evidence.no_outcome_error_count == 33
    assert evidence.other_error_count == 0
    assert evidence.requested_jobs == evidence.effective_jobs == 8

    output = tmp_path / "combined/results.parquet"
    merge_manifest = tmp_path / "combined/merge_manifest.json"
    merged, payload = MODULE.write_merged_outputs(
        bundles=bundles,
        output_path=output,
        merge_manifest_path=merge_manifest,
        attempt_manifests=[evidence],
        project_root=tmp_path,
    )

    assert len(merged) == 360
    assert payload["technical_attempt_provenance"] == {
        "attempt_manifest_count": 1,
        "no_outcome_error_record_count": 33,
        "unique_no_outcome_error_record_count": 33,
        "other_error_record_count": 0,
        "algorithm_outcomes_added_to_results": 0,
        "history_status": "supplied",
    }
    methods_input = payload["inputs"][1]
    assert methods_input["source_attempt_manifests"] == [
        {
            "path": "methods/attempt_manifests/run_manifest_jobs8_first_pass.json",
            "sha256": MODULE.sha256_file(attempt_path),
            "run_id": "2" * 12,
            "status_counts": {"complete": 255, "error": 33},
            "expected_task_count": 288,
            "completed_task_count": 255,
            "no_outcome_error_count": 33,
            "other_error_count": 0,
            "worker_error_count": 0,
            "requested_jobs": 8,
            "effective_jobs": 8,
            "algorithm_outcomes_added_to_results": 0,
        }
    ]
    assert set(merged["outcome"]) <= set(MODULE.moderate_artifacts.ALGORITHM_OUTCOMES)


def test_attempt_manifest_must_match_a_source_run_and_task_accounting(tmp_path: Path) -> None:
    base, methods = _sources(tmp_path)
    bundles = _load_bundles((base, methods))
    frame = pd.read_parquet(methods[0])
    path = _write_first_pass_attempt_manifest(
        tmp_path / "methods/attempt_manifests/first.json",
        frame,
        run_id="2" * 12,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["completed_task_count"] += 1
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(MODULE.MergeValidationError, match="completed-task count"):
        MODULE.load_attempt_manifest(path, bundles)


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("map", "different_map"),
        ("family", "different_family"),
        ("arena_commit", "d" * 40),
        ("scenario_sha256", "e" * 64),
        ("recovery_tau_on_override", "0.75"),
    ],
)
def test_merge_rejects_cross_method_shared_metadata_drift_without_outputs(
    tmp_path: Path,
    column: str,
    replacement: str,
) -> None:
    base, methods = _sources(tmp_path)
    frame = pd.read_parquet(methods[0])
    if column == "recovery_tau_on_override":
        frame[column] = replacement
    else:
        selected = (frame["source_policy"] == "pgrr") & frame["pair_id"].eq(
            frame["pair_id"].iloc[0]
        )
        frame.loc[selected, column] = replacement
    _rewrite_source(methods, frame, run_id="2" * 12)
    bundles = _load_bundles((base, methods))
    output = tmp_path / "combined/results.parquet"
    merge_manifest = tmp_path / "combined/merge_manifest.json"

    with pytest.raises(MODULE.MergeValidationError, match="metadata mismatch"):
        MODULE.write_merged_outputs(
            bundles=bundles,
            output_path=output,
            merge_manifest_path=merge_manifest,
            project_root=tmp_path,
        )
    assert not output.exists()
    assert not merge_manifest.exists()


def test_merge_rejects_different_project_commits(tmp_path: Path) -> None:
    base, methods = _sources(tmp_path)
    frame = pd.read_parquet(methods[0])
    frame["project_commit"] = "f" * 40
    _rewrite_source(methods, frame, run_id="2" * 12)

    with pytest.raises(MODULE.MergeValidationError, match="share one project_commit"):
        MODULE.merge_frames(_load_bundles((base, methods)))


def test_merge_rejects_method_overlap_or_missing_method(tmp_path: Path) -> None:
    base, methods = _sources(tmp_path)
    frame = pd.read_parquet(methods[0])
    frame.loc[frame["source_policy"] == "standard", ["source_policy", "method"]] = "base"
    _rewrite_source(methods, frame, run_id="2" * 12)

    with pytest.raises(MODULE.MergeValidationError, match="method sets must be disjoint"):
        MODULE.merge_frames(_load_bundles((base, methods)))


@pytest.mark.parametrize(
    "mutation", ["missing_row", "duplicate_pair", "test_split", "validation_case"]
)
def test_input_contract_rejects_incomplete_duplicate_or_nonvalidation_rows(
    tmp_path: Path,
    mutation: str,
) -> None:
    _, methods = _sources(tmp_path)
    frame = pd.read_parquet(methods[0])
    if mutation == "missing_row":
        frame = frame.iloc[:-1].copy()
    elif mutation == "duplicate_pair":
        pgrr_indices = frame.index[frame["source_policy"] == "pgrr"]
        frame.loc[pgrr_indices[1], "pair_id"] = frame.loc[pgrr_indices[0], "pair_id"]
    elif mutation == "test_split":
        frame.loc[0, "split"] = "test"
    else:
        frame["split"] = "Validation"
    _rewrite_source(methods, frame, run_id="2" * 12)

    with pytest.raises(MODULE.MergeValidationError):
        MODULE.load_input_bundle(*methods)


def test_source_run_manifest_must_match_collected_physical_rows(tmp_path: Path) -> None:
    _, methods = _sources(tmp_path)
    payload = json.loads(methods[1].read_text(encoding="utf-8"))
    payload["results"][0]["attempts"][-1]["outcome"] = "TIMEOUT"
    methods[1].write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(MODULE.MergeValidationError, match="final attempt disagrees"):
        MODULE.load_input_bundle(*methods)


def test_input_schemas_and_pair_sets_must_match_exactly(tmp_path: Path) -> None:
    base, methods = _sources(tmp_path)
    frame = pd.read_parquet(methods[0])
    frame = frame.loc[:, list(reversed(frame.columns))]
    _rewrite_source(methods, frame, run_id="2" * 12)
    with pytest.raises(MODULE.MergeValidationError, match="column order or membership"):
        MODULE.merge_frames(_load_bundles((base, methods)))

    base, methods = _sources(tmp_path / "pair_set")
    frame = pd.read_parquet(methods[0])
    selected = frame.index[frame["source_policy"] == "pgrr"][0]
    frame.loc[selected, "pair_id"] = "unexpected_pair_seed99999"
    _rewrite_source(methods, frame, run_id="2" * 12)
    with pytest.raises(MODULE.MergeValidationError, match="complete five-method pairs"):
        MODULE.merge_frames(_load_bundles((base, methods)))


def test_merge_refuses_to_impersonate_a_run_manifest(tmp_path: Path) -> None:
    bundles = _load_bundles(_sources(tmp_path))
    with pytest.raises(MODULE.MergeValidationError, match="must not be named run_manifest"):
        MODULE.write_merged_outputs(
            bundles=bundles,
            output_path=tmp_path / "combined/results.parquet",
            merge_manifest_path=tmp_path / "combined/run_manifest.json",
            project_root=tmp_path,
        )
