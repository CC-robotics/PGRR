#!/usr/bin/env python3
"""Locate manifest-pinned DAgger HDF5 artifacts locally and in Git history."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _requirements(manifests: list[Path]) -> list[dict[str, Any]]:
    output = []
    for manifest in manifests:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        for role in ("dataset", "validation_dataset"):
            item = payload[role]
            output.append(
                {
                    "manifest": manifest.as_posix(),
                    "role": role,
                    "declared_path": item["path"],
                    "expected_sha256": item["sha256"].lower(),
                }
            )
    return output


def _local_index(data_root: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for path in sorted(data_root.rglob("*.h5")):
        index.setdefault(_sha256_file(path), []).append(path.as_posix())
    return index


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL
    )


def _historical_h5_paths(repo: Path) -> list[str]:
    text = _git(repo, "log", "--all", "--format=", "--name-only", "--", "data").decode(
        "utf-8", errors="replace"
    )
    return sorted({line.strip() for line in text.splitlines() if line.strip().endswith(".h5")})


def _history_matches(repo: Path, expected: set[str]) -> dict[str, list[dict[str, str]]]:
    matches: dict[str, list[dict[str, str]]] = {value: [] for value in expected}
    seen_objects: set[str] = set()
    for path in _historical_h5_paths(repo):
        commits = _git(repo, "rev-list", "--all", "--", path).decode().splitlines()
        for commit in commits:
            try:
                object_id = _git(repo, "rev-parse", f"{commit}:{path}").decode().strip()
            except subprocess.CalledProcessError:
                continue
            if object_id in seen_objects:
                continue
            seen_objects.add(object_id)
            content = _git(repo, "cat-file", "blob", object_id)
            digest = _sha256_bytes(content)
            if digest in matches:
                matches[digest].append(
                    {"path": path, "commit": commit, "git_object": object_id}
                )
    return matches


def audit(repo: Path, manifests: list[Path]) -> dict[str, Any]:
    requirements = _requirements(manifests)
    expected = {item["expected_sha256"] for item in requirements}
    local = _local_index(repo / "data")
    unresolved = {value for value in expected if value not in local}
    history = _history_matches(repo, unresolved) if unresolved else {}
    for item in requirements:
        digest = item["expected_sha256"]
        item["local_matches"] = local.get(digest, [])
        item["git_history_matches"] = history.get(digest, [])
        item["status"] = (
            "local_match"
            if item["local_matches"]
            else "git_history_match"
            if item["git_history_matches"]
            else "not_found_local_or_git_history"
        )
    counts: dict[str, int] = {}
    for item in requirements:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "schema_version": 1,
        "requirements": requirements,
        "status_counts": dict(sorted(counts.items())),
        "claim_boundary": "read_only_local_and_git_history_search; no remote lookup",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.repo.resolve(), [path.resolve() for path in args.manifest])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
