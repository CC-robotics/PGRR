#!/usr/bin/env python3
"""Run a locked validation or test manifest with isolated Arena workers.

The controller never edits or deletes raw episode artifacts.  A logical
episode may have two physical attempts (``a0`` and ``a1``); the second is
started only when the first is explicitly classified as SIMULATOR_FAILURE or
INVALID_RESET.  This keeps infrastructure failures auditable while requiring
exactly one valid algorithm outcome for every manifest row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
ALGORITHM_OUTCOMES = {"GOAL_REACHED", "COLLISION", "TIMEOUT", "PLANNER_FAILURE"}
RETRYABLE_OUTCOMES = {"SIMULATOR_FAILURE", "INVALID_RESET"}
ALL_OUTCOMES = ALGORITHM_OUTCOMES | RETRYABLE_OUTCOMES
METHOD_ALIASES = {"dagger": "bc", "triggered_dagger": "bc"}
LEARNED_METHODS = {"bc", "bc_uniform", "mwbc", "pgrr"}
SUPPORTED_METHODS = {"base", "standard", "heuristic", "oracle"} | LEARNED_METHODS
DEFAULT_METHOD_CHECKPOINTS = {
    "bc_uniform": Path("checkpoints/bc/uniform_scenario/best.onnx"),
    "mwbc": Path("checkpoints/bc/mwbc_scenario/best.onnx"),
    "pgrr": Path("checkpoints/dagger/coverage_safety_aligned/best.onnx"),
}
MAX_ROS_DOMAIN_ID = 232
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class EpisodeTask:
    """One method evaluated on one immutable scenario."""

    task_index: int
    scenario_id: str
    family: str
    density: str
    seed: int
    replicate: int
    split: str
    map_id: str
    scenario_path: Path
    scenario_relpath: str
    scenario_sha256: str
    method: str
    checkpoint_path: str
    checkpoint_sha256: str
    checkpoint_container_path: str
    episode_stem: str
    timeout_s: float
    robot_start: str
    robot_goal: str
    pedestrian_config_hash: str
    recovery_tau_on_override: str


@dataclass(frozen=True)
class CheckpointProvenance:
    """One deployable method checkpoint resolved inside the project root."""

    relative_path: str
    sha256: str
    container_path: str


def canonical_json(value: Any) -> str:
    """Return a stable compact JSON representation for hashes and Parquet."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    """Hash a file without loading a potentially large raw artifact at once."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_methods(values: Sequence[str]) -> tuple[str, ...]:
    """Parse comma/space separated method names and reject semantic duplicates."""

    parsed: list[str] = []
    for value in values:
        for item in value.split(","):
            method = METHOD_ALIASES.get(item.strip().lower(), item.strip().lower())
            if not method:
                continue
            if method not in SUPPORTED_METHODS:
                allowed = ", ".join(sorted(SUPPORTED_METHODS | set(METHOD_ALIASES)))
                raise ValueError(f"unsupported method {method!r}; choose from {allowed}")
            if method in parsed:
                raise ValueError(f"duplicate method after alias normalization: {method}")
            parsed.append(method)
    if not parsed:
        raise ValueError("at least one method is required")
    return tuple(parsed)


def normalize_recovery_tau_on_override(split: str, value: float | None) -> str:
    """Validate a declared validation-only trigger-threshold override.

    The empty string is the stable, Parquet-safe representation of "use the
    checked-in runtime default".  Test runs intentionally reject overrides so
    that validation choices must be committed before held-out evaluation.
    """

    if value is None:
        return ""
    if split != "validation":
        raise ValueError("--recovery-tau-on is validation-only; commit the selected default")
    if not math.isfinite(value) or not 0.35 < value < 1.0:
        raise ValueError("--recovery-tau-on must be finite and satisfy 0.35 < value < 1.0")
    return format(value, ".12g")


def _normalize_method(value: str) -> str:
    method = METHOD_ALIASES.get(value.strip().lower(), value.strip().lower())
    if method not in SUPPORTED_METHODS:
        allowed = ", ".join(sorted(SUPPORTED_METHODS | set(METHOD_ALIASES)))
        raise ValueError(f"unsupported method {method!r}; choose from {allowed}")
    return method


def parse_method_checkpoint_assignments(values: Sequence[str]) -> dict[str, Path]:
    """Parse repeatable ``METHOD=PATH`` checkpoint overrides."""

    assignments: dict[str, Path] = {}
    for value in values:
        method_text, separator, path_text = value.partition("=")
        if not separator or not method_text.strip() or not path_text.strip():
            raise ValueError("--method-checkpoint must use METHOD=PATH")
        method = _normalize_method(method_text)
        if method not in LEARNED_METHODS:
            raise ValueError(f"method {method!r} does not use a learned checkpoint")
        if method in assignments:
            raise ValueError(f"duplicate checkpoint assignment for method {method!r}")
        assignments[method] = Path(path_text)
    return assignments


def _resolve_project_file(root: Path, path: Path, *, description: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    project_root = root.resolve()
    if project_root not in resolved.parents:
        raise ValueError(f"{description} must be inside PROJECT_ROOT")
    if not resolved.is_file():
        raise FileNotFoundError(f"{description} does not exist: {resolved}")
    return resolved


def resolve_method_checkpoints(
    root: Path,
    methods: Sequence[str],
    legacy_checkpoint: Path,
    assignment_values: Sequence[str],
) -> dict[str, CheckpointProvenance]:
    """Resolve the exact checkpoint used by every selected learned method."""

    selected = set(methods)
    assignments = parse_method_checkpoint_assignments(assignment_values)
    unused = sorted(set(assignments) - selected)
    if unused:
        raise ValueError(
            "checkpoint assignments reference unselected methods: " + ", ".join(unused)
        )

    declared_paths = dict(DEFAULT_METHOD_CHECKPOINTS)
    declared_paths["bc"] = legacy_checkpoint
    declared_paths.update(assignments)
    provenance: dict[str, CheckpointProvenance] = {}
    for method in sorted(selected & LEARNED_METHODS):
        if method not in declared_paths:
            raise ValueError(f"no checkpoint configured for learned method {method!r}")
        resolved = _resolve_project_file(
            root,
            declared_paths[method],
            description=f"checkpoint for method {method}",
        )
        relative_path = str(resolved.relative_to(root.resolve()))
        provenance[method] = CheckpointProvenance(
            relative_path=relative_path,
            sha256=sha256_file(resolved),
            container_path=f"/workspace/{relative_path}",
        )
    return provenance


def worker_identity(worker_index: int, jobs: int, domain_base: int, run_id: str) -> tuple[int, str]:
    """Return the fixed DDS domain and Gazebo partition owned by one worker."""

    if jobs <= 0 or not 0 <= worker_index < jobs:
        raise ValueError("worker index must be inside the positive worker range")
    domain = domain_base + worker_index
    if domain < 0 or domain > MAX_ROS_DOMAIN_ID:
        raise ValueError(f"worker ROS_DOMAIN_ID {domain} is outside [0, {MAX_ROS_DOMAIN_ID}]")
    partition = f"ramp_eval_{run_id}_w{worker_index:02d}"
    return domain, partition


def _resolve_scenario_path(root: Path, declared_path: str) -> Path:
    candidate = (root / "scenarios" / "generated" / declared_path).resolve()
    generated_root = (root / "scenarios" / "generated").resolve()
    if candidate != generated_root and generated_root not in candidate.parents:
        raise ValueError(f"scenario path leaves scenarios/generated: {declared_path}")
    return candidate


def resolve_split_manifest_path(
    root: Path,
    split: str,
    split_manifest: Path | None = None,
) -> Path:
    """Resolve a default or explicit split manifest without weakening split checks."""

    if split not in {"validation", "test"}:
        raise ValueError("split must be validation or test")
    declared = split_manifest or Path("scenarios") / "splits" / f"{split}.yaml"
    candidate = declared if declared.is_absolute() else root / declared
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"split manifest does not exist: {resolved}")
    return resolved


def load_split_records(
    root: Path,
    split: str,
    split_manifest: Path | None = None,
) -> list[dict[str, Any]]:
    """Load and fully verify one checked-in validation/test split."""

    split_path = resolve_split_manifest_path(root, split, split_manifest)
    document = yaml.safe_load(split_path.read_text(encoding="utf-8"))
    if document.get("split") != split or not isinstance(document.get("scenarios"), list):
        raise ValueError(f"invalid split manifest: {split_path}")

    records: list[dict[str, Any]] = []
    scenario_ids: set[str] = set()
    for declared in document["scenarios"]:
        scenario_id = str(declared["scenario_id"])
        if scenario_id in scenario_ids:
            raise ValueError(f"duplicate scenario_id in split manifest: {scenario_id}")
        scenario_ids.add(scenario_id)
        scenario_path = _resolve_scenario_path(root, str(declared["path"]))
        if not scenario_path.is_file():
            raise FileNotFoundError(f"scenario does not exist: {scenario_path}")
        actual_sha = sha256_file(scenario_path)
        if actual_sha != str(declared["sha256"]):
            raise ValueError(f"scenario SHA256 mismatch: {scenario_id}")
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        metadata = scenario.get("ramp_metadata", {})
        declared_replicate = declared.get("replicate", metadata.get("replicate", 0))
        if isinstance(declared_replicate, bool) or not isinstance(declared_replicate, int):
            raise ValueError(f"scenario replicate must be a non-negative integer: {scenario_id}")
        if declared_replicate < 0:
            raise ValueError(f"scenario replicate must be a non-negative integer: {scenario_id}")
        metadata_replicate = metadata.get("replicate")
        if metadata_replicate is not None and metadata_replicate != declared_replicate:
            raise ValueError(
                f"scenario metadata mismatch for {scenario_id}: "
                f"replicate={metadata_replicate!r}, expected {declared_replicate!r}"
            )
        expected = {
            "scenario_id": scenario_id,
            "family": str(declared["family"]),
            "density": str(declared["density"]),
            "seed": int(declared["seed"]),
            "split": split,
            "map_id": str(declared["map_id"]),
        }
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise ValueError(
                    f"scenario metadata mismatch for {scenario_id}: "
                    f"{key}={metadata.get(key)!r}, expected {value!r}"
                )
        robot = scenario["robots"][0]
        records.append(
            {
                **expected,
                "replicate": declared_replicate,
                "scenario_path": scenario_path,
                "scenario_relpath": str(scenario_path.relative_to(root)),
                "scenario_sha256": actual_sha,
                "robot_start": canonical_json(robot["start"]),
                "robot_goal": canonical_json(robot["goal"]),
                "pedestrian_config_hash": hashlib.sha256(
                    canonical_json(scenario.get("obstacles", {}).get("dynamic", [])).encode()
                ).hexdigest(),
            }
        )
    if not records:
        raise ValueError(f"split contains no scenarios: {split_path}")
    return records


def experiment_fingerprint(
    records: Sequence[dict[str, Any]],
    methods: Sequence[str],
    high_density_methods: Sequence[str],
    timeout_s: float,
    method_checkpoints: Mapping[str, CheckpointProvenance],
    project_commit: str,
    recovery_tau_on_override: str = "",
) -> str:
    """Identify exactly one frozen experiment configuration."""

    payload = {
        "project_commit": project_commit,
        "methods": list(methods),
        "high_density_methods": list(high_density_methods),
        "timeout_s": timeout_s,
        "recovery_tau_on_override": recovery_tau_on_override,
        "method_checkpoints": {
            method: {
                "path": checkpoint.relative_path,
                "sha256": checkpoint.sha256,
            }
            for method, checkpoint in sorted(method_checkpoints.items())
        },
        "scenarios": [
            {
                "scenario_id": record["scenario_id"],
                "scenario_sha256": record["scenario_sha256"],
                "replicate": int(record.get("replicate", 0)),
            }
            for record in records
        ],
    }
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()[:12]


def build_tasks(
    records: Sequence[dict[str, Any]],
    methods: Sequence[str],
    high_density_methods: Sequence[str],
    timeout_s: float,
    method_checkpoints: Mapping[str, CheckpointProvenance] | None = None,
    run_namespace: str = "",
    recovery_tau_on_override: str = "",
) -> list[EpisodeTask]:
    """Expand scenario records into a deterministic, duplicate-free task list."""

    if timeout_s <= 0.0:
        raise ValueError("timeout must be positive")
    if run_namespace and (not run_namespace.replace("_", "").isalnum() or len(run_namespace) > 32):
        raise ValueError("run namespace must be at most 32 alphanumeric/underscore characters")
    checkpoints = method_checkpoints or {}
    tasks: list[EpisodeTask] = []
    stems: set[str] = set()
    for record in records:
        selected_methods = list(methods)
        if record["density"] == "high":
            selected_methods.extend(high_density_methods)
        for method in selected_methods:
            checkpoint = checkpoints.get(method)
            if method in LEARNED_METHODS and method_checkpoints is not None and checkpoint is None:
                raise ValueError(f"no checkpoint provenance supplied for learned method {method!r}")
            stem = f"{record['scenario_id']}_eval_{method}"
            if run_namespace:
                stem = f"{stem}_{run_namespace}"
            if stem in stems:
                raise ValueError(f"duplicate logical episode stem: {stem}")
            stems.add(stem)
            tasks.append(
                EpisodeTask(
                    task_index=len(tasks),
                    scenario_id=str(record["scenario_id"]),
                    family=str(record["family"]),
                    density=str(record["density"]),
                    seed=int(record["seed"]),
                    replicate=int(record.get("replicate", 0)),
                    split=str(record["split"]),
                    map_id=str(record["map_id"]),
                    scenario_path=Path(record["scenario_path"]),
                    scenario_relpath=str(record["scenario_relpath"]),
                    scenario_sha256=str(record["scenario_sha256"]),
                    method=method,
                    checkpoint_path=checkpoint.relative_path if checkpoint else "",
                    checkpoint_sha256=checkpoint.sha256 if checkpoint else "",
                    checkpoint_container_path=checkpoint.container_path if checkpoint else "",
                    episode_stem=stem,
                    timeout_s=timeout_s,
                    robot_start=str(record["robot_start"]),
                    robot_goal=str(record["robot_goal"]),
                    pedestrian_config_hash=str(record["pedestrian_config_hash"]),
                    recovery_tau_on_override=recovery_tau_on_override,
                )
            )
    return tasks


def episode_id(task: EpisodeTask, attempt: int) -> str:
    """Return an immutable physical episode identifier."""

    if not 0 <= attempt < MAX_ATTEMPTS:
        raise ValueError(f"attempt must be in [0, {MAX_ATTEMPTS - 1}]")
    return f"{task.episode_stem}_a{attempt}_dwb"


def manifest_rows(
    tasks: Sequence[EpisodeTask],
    project_commit: str,
) -> list[dict[str, Any]]:
    """Build the stable logical-episode table written before simulation."""

    return [
        {
            "task_index": task.task_index,
            "episode_id": episode_id(task, 0),
            "map": task.map_id,
            "map_id": task.map_id,
            "scenario": task.scenario_id,
            "scenario_id": task.scenario_id,
            "pair_id": f"{task.scenario_id}_seed{task.seed}",
            "replicate": task.replicate,
            "family": task.family,
            "density": task.density,
            "seed": task.seed,
            "split": task.split,
            "method": task.method,
            "source_policy": task.method,
            "planner_id": "dwb",
            "robot_start": task.robot_start,
            "robot_goal": task.robot_goal,
            "pedestrian_config_hash": task.pedestrian_config_hash,
            "scenario_path": task.scenario_relpath,
            "scenario_sha256": task.scenario_sha256,
            "checkpoint_path": task.checkpoint_path,
            "checkpoint_sha256": task.checkpoint_sha256,
            "project_commit": project_commit,
            "timeout_s": task.timeout_s,
            "recovery_tau_on_override": task.recovery_tau_on_override,
        }
        for task in tasks
    ]


def _artifact_paths(root: Path, identifier: str) -> dict[str, Path]:
    prefix = root / "data" / "raw" / identifier
    return {
        "stream": prefix.with_suffix(".jsonl"),
        "outcome": prefix.with_suffix(".outcome.json"),
        "metadata": prefix.with_suffix(".metadata.json"),
    }


def inspect_attempt(root: Path, identifier: str) -> dict[str, Any] | None:
    """Inspect an existing attempt without mutating it."""

    paths = _artifact_paths(root, identifier)
    present = {name: path.exists() for name, path in paths.items()}
    if not any(present.values()):
        return None
    if not present["outcome"]:
        raise RuntimeError(f"partial episode has no outcome and cannot be resumed: {identifier}")
    payload = json.loads(paths["outcome"].read_text(encoding="utf-8"))
    outcome = payload.get("outcome")
    if outcome not in ALL_OUTCOMES:
        raise RuntimeError(f"unknown outcome for {identifier}: {outcome!r}")
    result: dict[str, Any] = {
        "episode_id": identifier,
        "outcome": outcome,
        "outcome_path": str(paths["outcome"].relative_to(root)),
        "stream_path": str(paths["stream"].relative_to(root)) if present["stream"] else None,
        "metadata_path": (
            str(paths["metadata"].relative_to(root)) if present["metadata"] else None
        ),
    }
    if outcome in ALGORITHM_OUTCOMES:
        if not present["stream"] or not paths["stream"].stat().st_size or not present["metadata"]:
            raise RuntimeError(f"valid outcome has incomplete artifacts: {identifier}")
        metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        if metadata.get("episode_id") != identifier or payload.get("episode_id") != identifier:
            raise RuntimeError(f"episode ID mismatch inside artifacts: {identifier}")
        result["raw_sha256"] = sha256_file(paths["stream"])
        result["sample_count"] = int(payload["sample_count"])
    return result


def validate_existing_attempts(tasks: Sequence[EpisodeTask], root: Path, resume: bool) -> None:
    """Reject overwrite hazards and impossible/duplicate retry layouts before launch."""

    for task in tasks:
        existing = [
            inspect_attempt(root, episode_id(task, attempt)) for attempt in range(MAX_ATTEMPTS)
        ]
        if not resume and any(record is not None for record in existing):
            first_existing = next(record for record in existing if record is not None)
            raise FileExistsError(
                f"refusing to overwrite existing episode: {first_existing['episode_id']}"
            )
        first, second = existing
        if second is not None and first is None:
            raise RuntimeError(f"retry exists without primary attempt: {second['episode_id']}")
        if first is not None and first["outcome"] in ALGORITHM_OUTCOMES and second is not None:
            raise RuntimeError(
                "duplicate attempt exists after a valid primary outcome: "
                f"{first['episode_id']}, {second['episode_id']}"
            )


def _clean_runtime_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_PROMPT_MODIFIER",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "AMENT_PREFIX_PATH",
        "COLCON_PREFIX_PATH",
        "CMAKE_PREFIX_PATH",
        "ROS_DISTRO",
        "ROS_VERSION",
        "ROS_PYTHON_VERSION",
        "RAMP_TAU_ON",
    ):
        environment.pop(name, None)
    return environment


def run_task(
    task: EpisodeTask,
    *,
    root: Path,
    domain: int,
    partition: str,
    resume: bool,
) -> dict[str, Any]:
    """Run or resume one logical episode, retaining one retry at most."""

    attempts: list[dict[str, Any]] = []
    for attempt in range(MAX_ATTEMPTS):
        identifier = episode_id(task, attempt)
        existing = inspect_attempt(root, identifier)
        if existing is not None:
            if not resume:
                raise FileExistsError(f"refusing to overwrite existing episode: {identifier}")
            attempts.append({**existing, "attempt": attempt, "resumed": True})
            if existing["outcome"] in ALGORITHM_OUTCOMES:
                return {
                    "task_index": task.task_index,
                    "scenario_id": task.scenario_id,
                    "replicate": task.replicate,
                    "method": task.method,
                    "checkpoint_path": task.checkpoint_path,
                    "checkpoint_sha256": task.checkpoint_sha256,
                    "status": "complete",
                    "episode_id": identifier,
                    "attempts": attempts,
                }
            continue

        environment = _clean_runtime_environment()
        environment.update(
            {
                "RAMP_EPISODE_ID": identifier,
                "RAMP_EPISODE_TIMEOUT_S": str(task.timeout_s),
                "RAMP_REPLICATE": str(task.replicate),
                "RAMP_SOURCE_POLICY": task.method,
                "ROS_DOMAIN_ID": str(domain),
                "GZ_PARTITION": partition,
                "IGN_PARTITION": partition,
            }
        )
        if task.method in LEARNED_METHODS:
            if not task.checkpoint_container_path or not task.checkpoint_sha256:
                raise RuntimeError(f"method {task.method} requires checkpoint provenance")
            environment["RAMP_BC_MODEL_PATH"] = task.checkpoint_container_path
            environment["RAMP_CHECKPOINT_SHA256"] = task.checkpoint_sha256
        if task.recovery_tau_on_override:
            environment["RAMP_TAU_ON"] = task.recovery_tau_on_override
        print(
            f"[worker domain={domain}] RUN task={task.task_index} "
            f"attempt={attempt} episode={identifier}",
            flush=True,
        )
        completed = subprocess.run(
            [str(root / "scripts" / "arena" / "run_baseline_episode.sh"), str(task.scenario_path)],
            cwd=root,
            env=environment,
            check=False,
        )
        inspected = inspect_attempt(root, identifier)
        if inspected is None:
            raise RuntimeError(
                f"episode command returned {completed.returncode} without outcome: {identifier}"
            )
        attempt_record = {
            **inspected,
            "attempt": attempt,
            "resumed": False,
            "returncode": completed.returncode,
        }
        attempts.append(attempt_record)
        if inspected["outcome"] in ALGORITHM_OUTCOMES:
            if completed.returncode != 0:
                raise RuntimeError(
                    f"valid-looking outcome came from failed command: {identifier} "
                    f"returncode={completed.returncode}"
                )
            return {
                "task_index": task.task_index,
                "scenario_id": task.scenario_id,
                "replicate": task.replicate,
                "method": task.method,
                "checkpoint_path": task.checkpoint_path,
                "checkpoint_sha256": task.checkpoint_sha256,
                "status": "complete",
                "episode_id": identifier,
                "attempts": attempts,
            }
        if completed.returncode == 0:
            raise RuntimeError(
                f"retryable outcome unexpectedly returned success: {identifier} "
                f"outcome={inspected['outcome']}"
            )
    return {
        "task_index": task.task_index,
        "scenario_id": task.scenario_id,
        "replicate": task.replicate,
        "method": task.method,
        "checkpoint_path": task.checkpoint_path,
        "checkpoint_sha256": task.checkpoint_sha256,
        "status": "incomplete",
        "episode_id": None,
        "attempts": attempts,
        "error": f"exhausted {MAX_ATTEMPTS} infrastructure attempts",
    }


def validate_completed_results(
    tasks: Sequence[EpisodeTask], results: Sequence[dict[str, Any]]
) -> None:
    """Require one and only one valid completion for every logical task."""

    expected = {task.task_index for task in tasks}
    seen_indices = [int(result["task_index"]) for result in results]
    duplicates = sorted(index for index in set(seen_indices) if seen_indices.count(index) > 1)
    missing = sorted(expected - set(seen_indices))
    unexpected = sorted(set(seen_indices) - expected)
    incomplete = sorted(
        int(result["task_index"]) for result in results if result.get("status") != "complete"
    )
    episode_ids = [str(result["episode_id"]) for result in results if result.get("episode_id")]
    duplicate_ids = sorted(
        identifier for identifier in set(episode_ids) if episode_ids.count(identifier) > 1
    )
    if missing or unexpected or duplicates or incomplete or duplicate_ids:
        raise RuntimeError(
            "experiment completeness failure: "
            f"missing={missing}, unexpected={unexpected}, duplicate_tasks={duplicates}, "
            f"incomplete={incomplete}, duplicate_episode_ids={duplicate_ids}"
        )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_or_validate_parquet(path: Path, rows: list[dict[str, Any]], resume: bool) -> None:
    frame = pd.DataFrame(rows)
    if path.exists():
        if not resume:
            raise FileExistsError(f"refusing to overwrite locked episode manifest: {path}")
        existing = pd.read_parquet(path)
        if list(existing.columns) != list(frame.columns) or existing.to_dict(
            orient="records"
        ) != frame.to_dict(orient="records"):
            raise RuntimeError(f"existing episode manifest differs from requested run: {path}")
        return
    temporary = path.with_suffix(".parquet.tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _git_output(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument(
        "--split-manifest",
        type=Path,
        help="Explicit split YAML; its declared split must still match --split.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=("base", "bc"),
        help="Space- or comma-separated methods; dagger is an alias for bc.",
    )
    parser.add_argument(
        "--high-density-methods",
        nargs="+",
        default=(),
        help="Additional methods run only on high-density rows of the same split.",
    )
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--recovery-tau-on",
        type=float,
        help=(
            "Validation-only recovery trigger threshold. The declared value is hashed "
            "into all run provenance; test runs must use the checked-in default."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "checkpoints" / "dagger" / "coverage_safety_aligned" / "best.onnx",
        help="Legacy checkpoint for method bc; prefer --method-checkpoint for new runs.",
    )
    parser.add_argument(
        "--method-checkpoint",
        action="append",
        default=[],
        metavar="METHOD=PATH",
        help=(
            "Repeatable learned-method checkpoint override. Defaults are registered for "
            "bc_uniform, mwbc, and pgrr."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "final")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.jobs <= 0:
        raise ValueError("--jobs must be positive")
    methods = normalize_methods(args.methods)
    high_density_methods = (
        normalize_methods(args.high_density_methods) if args.high_density_methods else ()
    )
    overlap = sorted(set(methods) & set(high_density_methods))
    if overlap:
        raise ValueError(f"methods repeated across full/high-density groups: {overlap}")
    selected_methods = (*methods, *high_density_methods)
    recovery_tau_on_override = normalize_recovery_tau_on_override(args.split, args.recovery_tau_on)
    method_checkpoints = resolve_method_checkpoints(
        ROOT,
        selected_methods,
        args.checkpoint,
        args.method_checkpoint,
    )
    split_manifest_path = resolve_split_manifest_path(ROOT, args.split, args.split_manifest)
    records = load_split_records(ROOT, args.split, split_manifest_path)
    project_commit = _git_output(ROOT, "rev-parse", "HEAD")

    run_id = experiment_fingerprint(
        records,
        methods,
        high_density_methods,
        args.timeout,
        method_checkpoints,
        project_commit,
        recovery_tau_on_override,
    )
    tasks = build_tasks(
        records,
        methods,
        high_density_methods,
        args.timeout,
        method_checkpoints,
        run_namespace=f"r{run_id}",
        recovery_tau_on_override=recovery_tau_on_override,
    )
    validate_existing_attempts(tasks, ROOT, args.resume)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_manifest_path = output_dir / "episode_manifest.parquet"
    run_manifest_path = output_dir / "run_manifest.json"
    if run_manifest_path.exists() and not args.resume:
        raise FileExistsError(f"refusing to overwrite run manifest: {run_manifest_path}")
    _write_or_validate_parquet(
        episode_manifest_path,
        manifest_rows(tasks, project_commit),
        args.resume,
    )

    jobs = min(args.jobs, len(tasks))
    domain_base = int(os.environ.get("RAMP_ROS_DOMAIN_BASE", "20"))
    worker_assignments = [tasks[index::jobs] for index in range(jobs)]

    def worker_loop(worker_index: int, assigned: Iterable[EpisodeTask]) -> list[dict[str, Any]]:
        domain, partition = worker_identity(worker_index, jobs, domain_base, run_id)
        return [
            run_task(
                task,
                root=ROOT,
                domain=domain,
                partition=partition,
                resume=args.resume,
            )
            for task in assigned
        ]

    results: list[dict[str, Any]] = []
    worker_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(worker_loop, index, assigned): index
            for index, assigned in enumerate(worker_assignments)
        }
        for future in as_completed(futures):
            worker_index = futures[future]
            try:
                results.extend(future.result())
            except Exception as error:
                worker_errors.append(f"worker {worker_index}: {type(error).__name__}: {error}")

    results.sort(key=lambda result: int(result["task_index"]))
    split_manifest_display = str(split_manifest_path)
    try:
        split_manifest_display = str(split_manifest_path.relative_to(ROOT.resolve()))
    except ValueError:
        pass
    checkpoint_payload = {
        method: {
            "path": checkpoint.relative_path,
            "sha256": checkpoint.sha256,
        }
        for method, checkpoint in sorted(method_checkpoints.items())
    }
    legacy_checkpoint = method_checkpoints.get("bc")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "split": args.split,
        "split_manifest": split_manifest_display,
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "methods": list(methods),
        "high_density_methods": list(high_density_methods),
        "requested_jobs": args.jobs,
        "effective_jobs": jobs,
        "timeout_s": args.timeout,
        "recovery_tau_on_override": recovery_tau_on_override,
        "project_commit": project_commit,
        "method_checkpoints": checkpoint_payload,
        "checkpoint": legacy_checkpoint.relative_path if legacy_checkpoint else None,
        "checkpoint_sha256": legacy_checkpoint.sha256 if legacy_checkpoint else None,
        "episode_manifest": str(episode_manifest_path.relative_to(ROOT)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_task_count": len(tasks),
        "completed_task_count": sum(result.get("status") == "complete" for result in results),
        "worker_errors": worker_errors,
        "results": results,
    }
    _atomic_write_json(run_manifest_path, payload)
    if worker_errors:
        raise RuntimeError("; ".join(worker_errors))
    validate_completed_results(tasks, results)
    print(
        f"Experiment PASS: split={args.split} tasks={len(tasks)} run_manifest={run_manifest_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
