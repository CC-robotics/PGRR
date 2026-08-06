#!/usr/bin/env python3
"""Verify that an isolated PGRR publication repository has minimal clean history.

This check is intentionally separate from ``privacy_audit.py``.  The ordinary
privacy audit validates files, while this command validates the Git object graph
that will be pushed.  Run it only in the temporary repository created from a
final ``git archive`` snapshot, never as a reason to rewrite the research
worktree in place.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

MAIN_BRANCH = "main"
STUDENT_BRANCH = "student/reproduce"
ALLOWED_NAME = "Charles Chen"
ALLOWED_EMAIL = "charles.chen@example.invalid"
MAX_GITHUB_FILE_BYTES = 100_000_000


class ReleaseGitAuditError(RuntimeError):
    """Raised when the candidate publication graph is not minimal or anonymous."""


def _run(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown Git error"
        raise ReleaseGitAuditError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line]


def _commit_count(repository: Path, ref: str) -> int:
    return int(_run(repository, "rev-list", "--count", ref))


def _verify_file_sizes(repository: Path, ref: str) -> None:
    listing = _run(repository, "ls-tree", "-l", "-r", ref)
    for line in _lines(listing):
        metadata, separator, path = line.partition("\t")
        if not separator:
            raise ReleaseGitAuditError(f"unparseable ls-tree row on {ref}")
        fields = metadata.split()
        if len(fields) != 4 or fields[1] != "blob" or fields[3] == "-":
            continue
        if int(fields[3]) >= MAX_GITHUB_FILE_BYTES:
            raise ReleaseGitAuditError(
                f"GitHub file-size limit exceeded on {ref}: {path} ({fields[3]} bytes)"
            )


def audit_release_repository(repository: Path) -> tuple[str, str]:
    repository = repository.expanduser().resolve()
    if not repository.is_dir():
        raise ReleaseGitAuditError(f"repository is not a directory: {repository}")
    if _run(repository, "rev-parse", "--is-inside-work-tree") != "true":
        raise ReleaseGitAuditError("candidate is not a Git worktree")
    if _run(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ReleaseGitAuditError("candidate publication worktree is dirty")

    heads = set(_lines(_run(repository, "for-each-ref", "--format=%(refname:short)", "refs/heads")))
    expected_heads = {MAIN_BRANCH, STUDENT_BRANCH}
    if heads != expected_heads:
        raise ReleaseGitAuditError(
            f"local heads must be exactly {sorted(expected_heads)}; found {sorted(heads)}"
        )
    if _lines(_run(repository, "for-each-ref", "--format=%(refname)", "refs/tags")):
        raise ReleaseGitAuditError("candidate publication repository must not contain tags")
    if _lines(_run(repository, "for-each-ref", "--format=%(refname)", "refs/remotes")):
        raise ReleaseGitAuditError("candidate publication repository must not contain remote refs")

    main_oid = _run(repository, "rev-parse", f"{MAIN_BRANCH}^{{commit}}")
    student_oid = _run(repository, "rev-parse", f"{STUDENT_BRANCH}^{{commit}}")
    if _commit_count(repository, MAIN_BRANCH) != 1:
        raise ReleaseGitAuditError("main must contain exactly one root commit")
    main_parents = _run(repository, "rev-list", "--parents", "-n", "1", MAIN_BRANCH).split()
    if main_parents != [main_oid]:
        raise ReleaseGitAuditError("main commit must not have a parent")
    if _commit_count(repository, STUDENT_BRANCH) != 2:
        raise ReleaseGitAuditError("student/reproduce must contain main plus one teaching commit")
    student_parents = _run(repository, "rev-list", "--parents", "-n", "1", STUDENT_BRANCH).split()
    if student_parents != [student_oid, main_oid]:
        raise ReleaseGitAuditError("student/reproduce must be a single child of main")

    history = _run(
        repository,
        "log",
        "--format=%H%x09%an%x09%ae%x09%cn%x09%ce",
        MAIN_BRANCH,
        STUDENT_BRANCH,
    )
    commits: set[str] = set()
    for line in _lines(history):
        fields = line.split("\t")
        if len(fields) != 5:
            raise ReleaseGitAuditError("unparseable Git identity row")
        oid, author_name, author_email, committer_name, committer_email = fields
        commits.add(oid)
        if (author_name, author_email) != (ALLOWED_NAME, ALLOWED_EMAIL):
            raise ReleaseGitAuditError(f"non-allowlisted author identity on commit {oid[:12]}")
        if (committer_name, committer_email) != (ALLOWED_NAME, ALLOWED_EMAIL):
            raise ReleaseGitAuditError(f"non-allowlisted committer identity on commit {oid[:12]}")
    if commits != {main_oid, student_oid}:
        raise ReleaseGitAuditError("unexpected commit is reachable from publication branches")

    _verify_file_sizes(repository, MAIN_BRANCH)
    _verify_file_sizes(repository, STUDENT_BRANCH)
    return main_oid, student_oid


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repository",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="isolated candidate publication repository (default: current directory)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        main_oid, student_oid = audit_release_repository(args.repository)
    except (OSError, ReleaseGitAuditError, ValueError) as exc:
        print(f"Release Git audit FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "Release Git audit PASS: "
        f"main={main_oid[:12]} (1 commit), student/reproduce={student_oid[:12]} (2 commits)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
