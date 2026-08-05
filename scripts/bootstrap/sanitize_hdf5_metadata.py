#!/usr/bin/env python3
"""Make tracked HDF5 provenance attributes portable before a public release.

The sanitizer is deliberately limited to Git-tracked HDF5 files.  It rewrites
only textual attributes; datasets and non-text attributes are never changed.
Run without ``--write`` for a dry-run and add ``--write`` for an atomic update.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import h5py

ROOT = Path(__file__).resolve().parents[2]
HDF5_SUFFIXES = {".h5", ".hdf5"}
PROJECT_ROOT_TOKEN = "${PROJECT_ROOT}"
HOME_TOKEN = "${HOME}"

# The first expression recognizes both the legacy internal repository name and
# the public PGRR name without embedding any particular account name.
PROJECT_PATH_RE = re.compile(
    r"/(?:home|Users)/[^/\\\"'\s]+/"
    r"(?:RAMP|(?:[^/\\\"'\s]+/)*PGRR)(?=/|$)",
    re.IGNORECASE,
)
HOME_PATH_RE = re.compile(r"/(?:home|Users)/[^/\\\"'\s]+", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class AttributeChange:
    """One portable-provenance rewrite."""

    path: str
    object_name: str
    attribute_name: str


def sanitize_text(value: str) -> str:
    """Replace machine-specific roots and host identifiers with stable tokens."""

    result = PROJECT_PATH_RE.sub(PROJECT_ROOT_TOKEN, value)
    result = HOME_PATH_RE.sub(HOME_TOKEN, result)
    hostnames = {socket.gethostname().strip()}
    for hostname in sorted(hostnames, key=len, reverse=True):
        if hostname:
            result = re.sub(re.escape(hostname), "<redacted-host>", result, flags=re.IGNORECASE)
    return result


def _tracked_paths(root: Path) -> set[Path]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached"],
        check=True,
        capture_output=True,
    )
    return {
        (root / item.decode("utf-8", errors="surrogateescape")).resolve()
        for item in completed.stdout.split(b"\0")
        if item
    }


def tracked_hdf5_files(root: Path) -> list[Path]:
    """Return only tracked HDF5 paths, in deterministic repository order."""

    root = root.resolve()
    return sorted(
        path
        for path in _tracked_paths(root)
        if path.suffix.casefold() in HDF5_SUFFIXES and path.is_file()
    )


def _object_attributes(handle: h5py.File):
    yield "/", handle.attrs
    objects: list[tuple[str, h5py.Group | h5py.Dataset]] = []

    def collect(name: str, item: h5py.Group | h5py.Dataset) -> None:
        objects.append((f"/{name}", item))

    handle.visititems(collect)
    for object_name, item in objects:
        yield object_name, item.attrs


def _printable_strings(payload: bytes, minimum_length: int = 4) -> str:
    strings = re.findall(rb"[\x20-\x7e]{%d,}" % minimum_length, payload)
    return "\n".join(value.decode("ascii", errors="ignore") for value in strings)


def _contains_stale_machine_text(path: Path) -> bool:
    printable = _printable_strings(path.read_bytes())
    return sanitize_text(printable) != printable


def inspect_file(path: Path, *, display_path: str | None = None) -> list[AttributeChange]:
    """Report textual attributes whose portable value differs."""

    changes: list[AttributeChange] = []
    with h5py.File(path, "r") as handle:
        for object_name, attributes in _object_attributes(handle):
            for attribute_name, value in attributes.items():
                if isinstance(value, bytes):
                    text = value.decode("utf-8", errors="strict")
                elif isinstance(value, str):
                    text = value
                else:
                    continue
                if sanitize_text(text) != text:
                    changes.append(
                        AttributeChange(
                            display_path or path.as_posix(), object_name, str(attribute_name)
                        )
                    )
    # HDF5 may retain the old value in an internal free-space block after an
    # in-place attribute update.  A release audit scans binary strings too, so
    # report that stale storage and force a fresh-file reconstruction.
    if not changes and _contains_stale_machine_text(path):
        changes.append(
            AttributeChange(display_path or path.as_posix(), "<file>", "<stale-metadata>")
        )
    return sorted(changes)


def _portable_attribute(value: object) -> object:
    if isinstance(value, bytes):
        return sanitize_text(value.decode("utf-8", errors="strict")).encode("utf-8")
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def _copy_attributes(source: object, destination: object) -> None:
    source_attributes = source.attrs
    destination_attributes = destination.attrs
    for attribute_name, value in source_attributes.items():
        destination_attributes[attribute_name] = _portable_attribute(value)


def _rewrite_copy(path: Path, destination: Path) -> None:
    # Reconstruct the HDF5 container instead of updating it in place.  This
    # prevents the previous private string from surviving in an HDF5 free-space
    # block even after the visible attribute has been sanitized.
    with h5py.File(path, "r") as source, h5py.File(destination, "w") as output:
        for name in source:
            source.copy(name, output, name=name, without_attrs=True)
        _copy_attributes(source, output)

        def copy_object_attributes(name: str, item: object) -> None:
            _copy_attributes(item, output[name])

        source.visititems(copy_object_attributes)
        output.flush()
    shutil.copystat(path, destination)


def sanitize_file(
    path: Path,
    *,
    write: bool,
    display_path: str | None = None,
) -> list[AttributeChange]:
    """Inspect or atomically sanitize one HDF5 file."""

    changes = inspect_file(path, display_path=display_path)
    if not write or not changes:
        return changes
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".privacy-tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
        temporary_path = Path(temporary_name)
        _rewrite_copy(path, temporary_path)
        os.replace(temporary_path, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return changes


def _resolve_targets(root: Path, requested: Sequence[Path]) -> list[Path]:
    tracked = _tracked_paths(root)
    targets = (
        [(path if path.is_absolute() else root / path).resolve() for path in requested]
        if requested
        else tracked_hdf5_files(root)
    )
    for path in targets:
        if path not in tracked:
            raise ValueError(f"refusing non-tracked path: {path}")
        if path.suffix.casefold() not in HDF5_SUFFIXES:
            raise ValueError(f"not an HDF5 file: {path}")
        if not path.is_file():
            raise ValueError(f"missing HDF5 file: {path}")
    return sorted(set(targets))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="tracked HDF5 paths")
    parser.add_argument("--root", type=Path, default=ROOT, help="Git worktree root")
    parser.add_argument("--write", action="store_true", help="atomically apply rewrites")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        targets = _resolve_targets(root, args.paths)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"ERROR: {error}")
        return 2
    all_changes: list[AttributeChange] = []
    for path in targets:
        relative = path.relative_to(root).as_posix()
        all_changes.extend(sanitize_file(path, write=args.write, display_path=relative))
    action = "sanitized" if args.write else "would sanitize"
    for change in sorted(all_changes):
        print(f"{action}: {change.path}:{change.object_name}:{change.attribute_name}")
    if all_changes and not args.write:
        print(f"HDF5 privacy check FAIL: {len(all_changes)} attribute(s) need sanitizing")
        return 1
    print(
        f"HDF5 privacy {'rewrite' if args.write else 'check'} PASS: "
        f"{len(targets)} tracked file(s), {len(all_changes)} attribute(s) {action}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
