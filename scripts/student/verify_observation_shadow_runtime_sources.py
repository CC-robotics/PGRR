#!/usr/bin/env python3
"""Compare a runtime checkout with the preflight-pinned shadow source hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _normalized_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def verify(manifest_path: Path, runtime_root: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("runtime_source_normalized_sha256")
    if not isinstance(expected, dict) or not expected:
        raise ValueError(
            "preflight manifest has no runtime_source_normalized_sha256 mapping"
        )

    files: list[dict[str, Any]] = []
    for relative, expected_sha in sorted(expected.items()):
        path = runtime_root / relative
        exists = path.is_file()
        actual_sha = _normalized_sha256(path) if exists else None
        files.append(
            {
                "path": relative,
                "exists": exists,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "line_endings_normalized": True,
                "matches": exists and actual_sha == expected_sha,
            }
        )

    ready = all(item["matches"] for item in files)
    return {
        "ready": ready,
        "diagnostic_only": True,
        "copy_performed": False,
        "runtime_root": str(runtime_root.resolve()),
        "preflight_manifest": str(manifest_path.resolve()),
        "episode_id": manifest.get("episode_id"),
        "file_count": len(files),
        "matching_file_count": sum(item["matches"] for item in files),
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.manifest, args.runtime_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
