from __future__ import annotations

import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    specification = spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


release_git_audit = _load_module(
    "release_git_audit", ROOT / "scripts/bootstrap/audit_release_git.py"
)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _candidate_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "candidate"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    _git(repository, "config", "user.name", "Charles Chen")
    _git(repository, "config", "user.email", "charles.chen@example.invalid")
    (repository / "README.md").write_text("PGRR release\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "release: clean root")
    _git(repository, "switch", "-q", "-c", "student/reproduce")
    (repository / "STUDENT.md").write_text("TODO(student)\n", encoding="utf-8")
    _git(repository, "add", "STUDENT.md")
    _git(repository, "commit", "-q", "-m", "teaching: student tasks")
    _git(repository, "switch", "-q", "main")
    return repository


def test_clean_minimal_release_history_passes(tmp_path: Path) -> None:
    repository = _candidate_repository(tmp_path)

    main_oid, student_oid = release_git_audit.audit_release_repository(repository)

    assert main_oid == _git(repository, "rev-parse", "main")
    assert student_oid == _git(repository, "rev-parse", "student/reproduce")
    assert release_git_audit.main([str(repository)]) == 0


@pytest.mark.parametrize("violation", ["dirty", "extra-main-commit", "private-author"])
def test_release_history_rejects_nonminimal_or_private_graph(
    tmp_path: Path, violation: str
) -> None:
    repository = _candidate_repository(tmp_path)
    if violation == "dirty":
        (repository / "private-notes.txt").write_text("not releasable\n", encoding="utf-8")
    elif violation == "extra-main-commit":
        (repository / "README.md").write_text("second main revision\n", encoding="utf-8")
        _git(repository, "add", "README.md")
        _git(repository, "commit", "-q", "-m", "unexpected history")
    else:
        _git(repository, "switch", "-q", "student/reproduce")
        _git(repository, "config", "user.name", "Sensitive Person")
        private_email = f"sensitive{chr(64)}example.com"
        _git(repository, "config", "user.email", private_email)
        _git(repository, "commit", "-q", "--amend", "--no-edit", "--reset-author")
        _git(repository, "switch", "-q", "main")

    with pytest.raises(release_git_audit.ReleaseGitAuditError):
        release_git_audit.audit_release_repository(repository)


def test_release_history_rejects_extra_ref_or_tag(tmp_path: Path) -> None:
    repository = _candidate_repository(tmp_path)
    _git(repository, "branch", "private/archive", "main")

    with pytest.raises(release_git_audit.ReleaseGitAuditError, match="local heads"):
        release_git_audit.audit_release_repository(repository)

    _git(repository, "branch", "-d", "private/archive")
    _git(repository, "tag", "old-release", "main")
    with pytest.raises(release_git_audit.ReleaseGitAuditError, match="must not contain tags"):
        release_git_audit.audit_release_repository(repository)
