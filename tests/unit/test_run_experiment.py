import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "run_experiment.py"
_SPEC = importlib.util.spec_from_file_location("ramp_run_experiment", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _record(tmp_path: Path, scenario_id: str = "crossing_flow_high_test_s03220") -> dict:
    return {
        "scenario_id": scenario_id,
        "family": "crossing_flow",
        "density": "high",
        "seed": 3220,
        "split": "test",
        "map_id": "map_empty",
        "scenario_path": tmp_path / f"{scenario_id}.json",
        "scenario_relpath": f"scenarios/generated/{scenario_id}.json",
        "scenario_sha256": "a" * 64,
        "robot_start": "[5,12,0]",
        "robot_goal": "[26,12,0]",
        "pedestrian_config_hash": "b" * 64,
    }


def test_normalize_methods_supports_aliases_and_rejects_duplicates() -> None:
    assert _MODULE.normalize_methods(["base,dagger", "heuristic"]) == (
        "base",
        "bc",
        "heuristic",
    )
    with pytest.raises(ValueError, match="duplicate"):
        _MODULE.normalize_methods(["bc", "dagger"])
    with pytest.raises(ValueError, match="unsupported"):
        _MODULE.normalize_methods(["random"])


def test_worker_identity_is_fixed_unique_and_bounded() -> None:
    identities = [_MODULE.worker_identity(index, 4, 40, "abc123") for index in range(4)]
    assert [identity[0] for identity in identities] == [40, 41, 42, 43]
    assert len({identity[1] for identity in identities}) == 4
    assert _MODULE.worker_identity(2, 4, 40, "abc123") == identities[2]
    with pytest.raises(ValueError, match="outside"):
        _MODULE.worker_identity(3, 4, 230, "abc123")


def test_build_tasks_produces_deterministic_unique_episode_ids(tmp_path: Path) -> None:
    records = [_record(tmp_path), _record(tmp_path, "group_blocking_high_test_s03420")]
    tasks = _MODULE.build_tasks(records, ("base", "bc"), (), 180.0)
    assert len(tasks) == 4
    identifiers = [_MODULE.episode_id(task, 0) for task in tasks]
    assert len(identifiers) == len(set(identifiers))
    assert identifiers[0].endswith("_eval_base_a0_dwb")
    assert _MODULE.episode_id(tasks[0], 1).endswith("_a1_dwb")


def test_validate_completed_results_rejects_missing_and_duplicate_tasks(tmp_path: Path) -> None:
    tasks = _MODULE.build_tasks([_record(tmp_path)], ("base", "bc"), (), 180.0)
    complete = [
        {
            "task_index": task.task_index,
            "status": "complete",
            "episode_id": _MODULE.episode_id(task, 0),
        }
        for task in tasks
    ]
    _MODULE.validate_completed_results(tasks, complete)
    with pytest.raises(RuntimeError, match="missing"):
        _MODULE.validate_completed_results(tasks, complete[:1])
    with pytest.raises(RuntimeError, match="duplicate_tasks"):
        _MODULE.validate_completed_results(tasks, [complete[0], complete[0], complete[1]])


def test_high_density_method_selection_builds_64_final_tasks(tmp_path: Path) -> None:
    records = []
    for family_index in range(8):
        for density_index, density in enumerate(("low", "medium", "high")):
            record = _record(
                tmp_path,
                f"family{family_index}_{density}_test_s{family_index}{density_index}",
            )
            record["family"] = f"family{family_index}"
            record["density"] = density
            records.append(record)
    tasks = _MODULE.build_tasks(
        records,
        ("base", "bc"),
        ("standard", "heuristic"),
        180.0,
    )
    assert len(tasks) == 64
    assert sum(task.method == "base" for task in tasks) == 24
    assert sum(task.method == "bc" for task in tasks) == 24
    assert sum(task.method == "standard" for task in tasks) == 8
    assert sum(task.method == "heuristic" for task in tasks) == 8
    assert all(task.density == "high" for task in tasks if task.method in {"standard", "heuristic"})

    rows = _MODULE.manifest_rows(tasks, "c" * 64, "d" * 40)
    assert len({row["pair_id"] for row in rows}) == 24
    assert all(row["source_policy"] == row["method"] for row in rows)
    assert {row["replicate"] for row in rows} == {0}


def test_inspect_attempt_preserves_retryable_outcome_without_stream(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    identifier = "scenario_eval_run_base_a0_dwb"
    (raw / f"{identifier}.outcome.json").write_text(
        '{"episode_id":"scenario_eval_run_base_a0_dwb",'
        '"outcome":"SIMULATOR_FAILURE","sample_count":0}\n',
        encoding="utf-8",
    )
    inspected = _MODULE.inspect_attempt(tmp_path, identifier)
    assert inspected is not None
    assert inspected["outcome"] == "SIMULATOR_FAILURE"
    assert inspected["stream_path"] is None


def test_existing_attempt_preflight_rejects_overwrite_and_orphan_retry(tmp_path: Path) -> None:
    tasks = _MODULE.build_tasks([_record(tmp_path)], ("base",), (), 180.0)
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    primary = _MODULE.episode_id(tasks[0], 0)
    (raw / f"{primary}.outcome.json").write_text(
        f'{{"episode_id":"{primary}","outcome":"SIMULATOR_FAILURE","sample_count":0}}\n',
        encoding="utf-8",
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _MODULE.validate_existing_attempts(tasks, tmp_path, False)
    _MODULE.validate_existing_attempts(tasks, tmp_path, True)

    (raw / f"{primary}.outcome.json").unlink()
    retry = _MODULE.episode_id(tasks[0], 1)
    (raw / f"{retry}.outcome.json").write_text(
        f'{{"episode_id":"{retry}","outcome":"INVALID_RESET","sample_count":0}}\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="retry exists without primary"):
        _MODULE.validate_existing_attempts(tasks, tmp_path, True)
