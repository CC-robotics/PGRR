import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate" / "run_experiment.py"
_SPEC = importlib.util.spec_from_file_location("ramp_run_experiment", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _record(
    tmp_path: Path,
    scenario_id: str = "crossing_flow_high_test_s03220",
    *,
    replicate: int | None = None,
) -> dict:
    record = {
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
    if replicate is not None:
        record["replicate"] = replicate
    return record


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
    assert _MODULE.normalize_methods(["bc_uniform", "mwbc", "pgrr"]) == (
        "bc_uniform",
        "mwbc",
        "pgrr",
    )


def test_recovery_tau_override_is_validation_only_and_stably_serialized() -> None:
    assert _MODULE.normalize_recovery_tau_on_override("validation", None) == ""
    assert _MODULE.normalize_recovery_tau_on_override("validation", 0.8) == "0.8"
    for invalid in (0.35, 1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite"):
            _MODULE.normalize_recovery_tau_on_override("validation", invalid)
    with pytest.raises(ValueError, match="validation-only"):
        _MODULE.normalize_recovery_tau_on_override("test", 0.8)


def test_method_checkpoint_defaults_overrides_and_provenance(tmp_path: Path) -> None:
    defaults = _MODULE.resolve_method_checkpoints(
        _SCRIPT.parents[2],
        ("bc_uniform", "pgrr"),
        _SCRIPT.parents[2] / "checkpoints/dagger/coverage_safety_aligned/best.onnx",
        (),
    )
    assert defaults["bc_uniform"].relative_path == ("checkpoints/bc/uniform_scenario/best.onnx")
    assert defaults["pgrr"].relative_path == (
        "checkpoints/dagger/coverage_safety_aligned/best.onnx"
    )
    assert len(defaults["pgrr"].sha256) == 64

    custom = tmp_path / "models" / "custom.onnx"
    custom.parent.mkdir()
    custom.write_bytes(b"checkpoint")
    overridden = _MODULE.resolve_method_checkpoints(
        tmp_path,
        ("pgrr",),
        Path("unused.onnx"),
        ("pgrr=models/custom.onnx",),
    )
    assert overridden["pgrr"].relative_path == "models/custom.onnx"
    assert overridden["pgrr"].container_path == "/workspace/models/custom.onnx"
    assert overridden["pgrr"].sha256 == _MODULE.sha256_file(custom)

    with pytest.raises(ValueError, match="does not use"):
        _MODULE.resolve_method_checkpoints(
            tmp_path,
            ("base",),
            Path("unused.onnx"),
            ("base=models/custom.onnx",),
        )
    with pytest.raises(ValueError, match="unselected"):
        _MODULE.resolve_method_checkpoints(
            tmp_path,
            ("pgrr",),
            Path("unused.onnx"),
            ("bc_uniform=models/custom.onnx",),
        )


def test_explicit_split_manifest_still_enforces_declared_split(tmp_path: Path) -> None:
    generated = tmp_path / "scenarios" / "generated"
    generated.mkdir(parents=True)
    scenario_path = generated / "custom.json"
    scenario = {
        "ramp_metadata": {
            "scenario_id": "custom_test",
            "family": "crossing_flow",
            "density": "low",
            "seed": 7,
            "replicate": 3,
            "split": "test",
            "map_id": "map_empty",
        },
        "robots": [{"start": [0, 0, 0], "goal": [1, 0, 0]}],
        "obstacles": {"dynamic": []},
    }
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    manifest = tmp_path / "custom_split.yaml"
    document = {
        "split": "test",
        "scenarios": [
            {
                "scenario_id": "custom_test",
                "family": "crossing_flow",
                "density": "low",
                "seed": 7,
                "replicate": 3,
                "map_id": "map_empty",
                "path": "custom.json",
                "sha256": _MODULE.sha256_file(scenario_path),
            }
        ],
    }
    manifest.write_text(yaml.safe_dump(document), encoding="utf-8")
    records = _MODULE.load_split_records(tmp_path, "test", manifest)
    assert [record["scenario_id"] for record in records] == ["custom_test"]
    assert [record["replicate"] for record in records] == [3]

    document["split"] = "validation"
    manifest.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid split manifest"):
        _MODULE.load_split_records(tmp_path, "test", manifest)


def test_split_manifest_replicate_is_validated_and_legacy_records_default_to_zero(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "scenarios" / "generated"
    generated.mkdir(parents=True)
    scenario_path = generated / "custom.json"
    scenario = {
        "ramp_metadata": {
            "scenario_id": "custom_test",
            "family": "crossing_flow",
            "density": "low",
            "seed": 7,
            "split": "test",
            "map_id": "map_empty",
        },
        "robots": [{"start": [0, 0, 0], "goal": [1, 0, 0]}],
        "obstacles": {"dynamic": []},
    }
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    record = {
        "scenario_id": "custom_test",
        "family": "crossing_flow",
        "density": "low",
        "seed": 7,
        "map_id": "map_empty",
        "path": "custom.json",
        "sha256": _MODULE.sha256_file(scenario_path),
    }
    manifest = tmp_path / "custom_split.yaml"
    manifest.write_text(
        yaml.safe_dump({"split": "test", "scenarios": [record]}),
        encoding="utf-8",
    )
    assert _MODULE.load_split_records(tmp_path, "test", manifest)[0]["replicate"] == 0

    record["replicate"] = -1
    manifest.write_text(
        yaml.safe_dump({"split": "test", "scenarios": [record]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-negative integer"):
        _MODULE.load_split_records(tmp_path, "test", manifest)


def test_worker_identity_is_fixed_unique_and_bounded() -> None:
    identities = [_MODULE.worker_identity(index, 4, 40, "abc123") for index in range(4)]
    assert [identity[0] for identity in identities] == [40, 41, 42, 43]
    assert len({identity[1] for identity in identities}) == 4
    assert _MODULE.worker_identity(2, 4, 40, "abc123") == identities[2]
    with pytest.raises(ValueError, match="outside"):
        _MODULE.worker_identity(3, 4, 230, "abc123")


def test_worker_assignment_continues_after_episode_process_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks = _MODULE.build_tasks(
        [
            _record(tmp_path, "crossing_flow_high_test_s03220", replicate=0),
            _record(tmp_path, "crossing_flow_high_test_s03221", replicate=1),
        ],
        ("base",),
        (),
        1.0,
        run_namespace="risolation",
    )
    attempted: list[int] = []

    def fake_run_task(task: object, **_: object) -> dict:
        task_index = int(task.task_index)
        attempted.append(task_index)
        if task_index == 0:
            raise RuntimeError("episode command returned 1 without outcome")
        return {
            "task_index": task_index,
            "scenario_id": task.scenario_id,
            "replicate": task.replicate,
            "method": task.method,
            "checkpoint_path": task.checkpoint_path,
            "checkpoint_sha256": task.checkpoint_sha256,
            "status": "complete",
            "episode_id": _MODULE.episode_id(task, 0),
            "attempts": [],
        }

    monkeypatch.setattr(_MODULE, "run_task", fake_run_task)
    results = _MODULE.run_worker_assignment(
        0,
        tasks,
        root=tmp_path,
        jobs=1,
        domain_base=20,
        run_id="isolation",
        resume=False,
    )

    assert attempted == [0, 1]
    assert [result["status"] for result in results] == ["error", "complete"]
    assert results[0]["episode_id"] is None
    assert "without outcome" in results[0]["error"]


def test_build_tasks_produces_deterministic_unique_episode_ids(tmp_path: Path) -> None:
    records = [
        _record(tmp_path, replicate=4),
        _record(tmp_path, "group_blocking_high_test_s03420", replicate=7),
    ]
    checkpoints = {
        "bc_uniform": _MODULE.CheckpointProvenance(
            "checkpoints/bc/uniform.onnx", "c" * 64, "/workspace/checkpoints/bc/uniform.onnx"
        ),
        "pgrr": _MODULE.CheckpointProvenance(
            "checkpoints/dagger/pgrr.onnx", "d" * 64, "/workspace/checkpoints/dagger/pgrr.onnx"
        ),
    }
    tasks = _MODULE.build_tasks(
        records,
        ("base", "bc_uniform", "pgrr"),
        (),
        180.0,
        checkpoints,
        recovery_tau_on_override="0.8",
    )
    assert len(tasks) == 6
    identifiers = [_MODULE.episode_id(task, 0) for task in tasks]
    assert len(identifiers) == len(set(identifiers))
    assert identifiers[0].endswith("_eval_base_a0_dwb")
    assert _MODULE.episode_id(tasks[0], 1).endswith("_a1_dwb")
    assert any(identifier.endswith("_eval_bc_uniform_a0_dwb") for identifier in identifiers)
    assert any(identifier.endswith("_eval_pgrr_a0_dwb") for identifier in identifiers)
    pgrr_task = next(task for task in tasks if task.method == "pgrr")
    assert pgrr_task.checkpoint_sha256 == "d" * 64
    assert pgrr_task.replicate == 4
    assert pgrr_task.recovery_tau_on_override == "0.8"
    assert {row["recovery_tau_on_override"] for row in _MODULE.manifest_rows(tasks, "d" * 40)} == {
        "0.8"
    }
    assert {row["replicate"] for row in _MODULE.manifest_rows(tasks, "d" * 40)} == {4, 7}


def test_run_namespace_prevents_cross_commit_raw_artifact_collisions(tmp_path: Path) -> None:
    record = _record(tmp_path)
    first = _MODULE.build_tasks([record], ("base",), (), 180.0, run_namespace="rabc123")[0]
    second = _MODULE.build_tasks([record], ("base",), (), 180.0, run_namespace="rdef456")[0]
    assert _MODULE.episode_id(first, 0) != _MODULE.episode_id(second, 0)
    assert _MODULE.episode_id(first, 0).endswith("_eval_base_rabc123_a0_dwb")
    with pytest.raises(ValueError, match="run namespace"):
        _MODULE.build_tasks([record], ("base",), (), 180.0, run_namespace="not/a/namespace")


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
    checkpoints = {
        "bc": _MODULE.CheckpointProvenance(
            "checkpoints/dagger/best.onnx", "c" * 64, "/workspace/checkpoints/dagger/best.onnx"
        )
    }
    tasks = _MODULE.build_tasks(
        records,
        ("base", "bc"),
        ("standard", "heuristic"),
        180.0,
        checkpoints,
    )
    assert len(tasks) == 64
    assert sum(task.method == "base" for task in tasks) == 24
    assert sum(task.method == "bc" for task in tasks) == 24
    assert sum(task.method == "standard" for task in tasks) == 8
    assert sum(task.method == "heuristic" for task in tasks) == 8
    assert all(task.density == "high" for task in tasks if task.method in {"standard", "heuristic"})

    rows = _MODULE.manifest_rows(tasks, "d" * 40)
    assert len({row["pair_id"] for row in rows}) == 24
    assert all(row["source_policy"] == row["method"] for row in rows)
    assert {row["replicate"] for row in rows} == {0}
    assert {row["checkpoint_sha256"] for row in rows if row["method"] == "bc"} == {"c" * 64}
    assert {row["checkpoint_sha256"] for row in rows if row["method"] == "base"} == {""}


def test_fingerprint_includes_complete_method_checkpoint_map(tmp_path: Path) -> None:
    records = [_record(tmp_path)]
    uniform = _MODULE.CheckpointProvenance("uniform.onnx", "a" * 64, "/workspace/uniform.onnx")
    pgrr = _MODULE.CheckpointProvenance("pgrr.onnx", "b" * 64, "/workspace/pgrr.onnx")
    first = _MODULE.experiment_fingerprint(
        records,
        ("bc_uniform", "pgrr"),
        (),
        180.0,
        {"bc_uniform": uniform, "pgrr": pgrr},
        "d" * 40,
    )
    changed = _MODULE.experiment_fingerprint(
        records,
        ("bc_uniform", "pgrr"),
        (),
        180.0,
        {
            "bc_uniform": uniform,
            "pgrr": _MODULE.CheckpointProvenance("pgrr.onnx", "e" * 64, "/workspace/pgrr.onnx"),
        },
        "d" * 40,
    )
    assert first != changed
    threshold_changed = _MODULE.experiment_fingerprint(
        records,
        ("bc_uniform", "pgrr"),
        (),
        180.0,
        {"bc_uniform": uniform, "pgrr": pgrr},
        "d" * 40,
        "0.8",
    )
    assert first != threshold_changed


def test_parse_args_accepts_repeatable_method_checkpoints_and_split_manifest() -> None:
    args = _MODULE.parse_args(
        [
            "--split",
            "validation",
            "--split-manifest",
            "scenarios/splits/validation.yaml",
            "--methods",
            "bc_uniform",
            "pgrr",
            "--method-checkpoint",
            "bc_uniform=checkpoints/bc/uniform_scenario/best.onnx",
            "--method-checkpoint",
            "pgrr=checkpoints/dagger/coverage_safety_aligned/best.onnx",
            "--recovery-tau-on",
            "0.8",
        ]
    )
    assert args.split_manifest == Path("scenarios/splits/validation.yaml")
    assert args.method_checkpoint == [
        "bc_uniform=checkpoints/bc/uniform_scenario/best.onnx",
        "pgrr=checkpoints/dagger/coverage_safety_aligned/best.onnx",
    ]
    assert args.recovery_tau_on == 0.8


def test_runtime_maps_new_source_policies_to_bc_without_renaming_logs() -> None:
    root = _SCRIPT.parents[2]
    runtime = (root / "scripts/arena/run_baseline_episode_inner.sh").read_text(encoding="utf-8")
    wrapper = (root / "scripts/arena/run_baseline_episode.sh").read_text(encoding="utf-8")
    for method in ("bc_uniform", "mwbc", "pgrr"):
        assert method in runtime
        assert method in wrapper or method == "bc_uniform"
    assert '-p source_policy:="${SOURCE_POLICY}"' in runtime
    assert 'recovery_policy_type="bc"' in runtime
    assert "checkpoints/dagger/coverage_safety_aligned/best.onnx" in wrapper
    assert 'optional_runtime_environment+=("RAMP_TAU_ON=${RAMP_TAU_ON}")' in wrapper
    assert 'recovery_tau_on_overrides=(-p "tau_on:=${RAMP_TAU_ON}")' in runtime
    assert 'detector_trigger_overrides=(-p "trigger_threshold:=${RAMP_TAU_ON}")' in runtime
    assert 'RAMP_REPLICATE="${RAMP_REPLICATE:-}"' in wrapper
    assert '"${RAMP_REPLICATE}" != "${replicate}"' in runtime


def test_declared_tau_override_reaches_runtime_and_ambient_value_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAMP_TAU_ON", "0.99")
    assert "RAMP_TAU_ON" not in _MODULE._clean_runtime_environment()
    task = _MODULE.build_tasks(
        [_record(tmp_path, replicate=5)],
        ("base",),
        (),
        1.0,
        run_namespace="rthreshold",
        recovery_tau_on_override="0.8",
    )[0]
    captured: dict[str, str] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured.update(environment)
        identifier = _MODULE.episode_id(task, 0)
        raw = tmp_path / "data" / "raw"
        raw.mkdir(parents=True)
        (raw / f"{identifier}.jsonl").write_text("{}\n", encoding="utf-8")
        (raw / f"{identifier}.outcome.json").write_text(
            json.dumps(
                {
                    "episode_id": identifier,
                    "outcome": "GOAL_REACHED",
                    "sample_count": 1,
                }
            ),
            encoding="utf-8",
        )
        (raw / f"{identifier}.metadata.json").write_text(
            json.dumps({"episode_id": identifier}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_MODULE.subprocess, "run", fake_run)
    result = _MODULE.run_task(
        task,
        root=tmp_path,
        domain=20,
        partition="ramp_threshold_test",
        resume=False,
    )
    assert result["status"] == "complete"
    assert result["replicate"] == 5
    assert captured["RAMP_TAU_ON"] == "0.8"
    assert captured["RAMP_REPLICATE"] == "5"


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


def test_run_task_retries_a_classified_logger_artifact_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _MODULE.build_tasks([_record(tmp_path)], ("base",), (), 1.0, run_namespace="rretry")[0]
    attempted: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        identifier = str(environment["RAMP_EPISODE_ID"])
        attempted.append(identifier)
        raw = tmp_path / "data" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        if identifier.endswith("_a0_dwb"):
            (raw / f"{identifier}.outcome.json").write_text(
                json.dumps(
                    {
                        "episode_id": identifier,
                        "outcome": "SIMULATOR_FAILURE",
                        "sample_count": 0,
                        "detail": "episode logger exited without complete artifacts (status=1)",
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 1)
        (raw / f"{identifier}.jsonl").write_text("{}\n", encoding="utf-8")
        (raw / f"{identifier}.outcome.json").write_text(
            json.dumps(
                {
                    "episode_id": identifier,
                    "outcome": "GOAL_REACHED",
                    "sample_count": 1,
                }
            ),
            encoding="utf-8",
        )
        (raw / f"{identifier}.metadata.json").write_text(
            json.dumps({"episode_id": identifier}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_MODULE.subprocess, "run", fake_run)
    result = _MODULE.run_task(
        task,
        root=tmp_path,
        domain=20,
        partition="ramp_retry_test",
        resume=False,
    )
    assert result["status"] == "complete"
    assert result["episode_id"].endswith("_a1_dwb")
    assert len(result["attempts"]) == 2
    assert [attempt["outcome"] for attempt in result["attempts"]] == [
        "SIMULATOR_FAILURE",
        "GOAL_REACHED",
    ]
    assert len(attempted) == 2


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
