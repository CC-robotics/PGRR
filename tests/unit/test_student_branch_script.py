from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/teaching/make_student_branch.sh"
INSTALLER = ROOT / "teaching/student_templates/apply_student_tasks.py"


def test_student_branch_script_is_worktree_isolated_and_non_overwriting() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'SOURCE_BRANCH="teacher/reference"' in source
    assert 'STUDENT_BRANCH="student/reproduce"' in source
    assert "--allow-source-dirty" in source
    assert "status --porcelain=v1 --untracked-files=all" in source
    assert 'show-ref --verify --quiet "refs/heads/${STUDENT_BRANCH}"' in source
    assert "worktree add -b" in source
    assert '"${WORKTREE}" "${SOURCE_HEAD}"' in source
    assert "worktree remove --force" in source
    assert "update-ref -d" in source
    assert "symbolic-ref --quiet --short HEAD" in source
    for forbidden in (
        "reset --hard",
        "checkout --",
        "git stash",
        'git -C "${REPOSITORY}" switch',
        "rm -rf",
        'branch -D "${STUDENT_BRANCH}"',
    ):
        assert forbidden not in source
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _copy_student_release_inputs(repository: Path) -> None:
    files = (
        "pyproject.toml",
        "scripts/teaching/make_student_branch.sh",
        "packages/ramp_core/ramp_core/failure/rules.py",
        "scripts/paper/make_figures.py",
    )
    for relative in files:
        source = ROOT / relative
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copytree(
        ROOT / "teaching/student_templates",
        repository / "teaching/student_templates",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def test_allow_source_dirty_uses_committed_head_and_preserves_caller(tmp_path: Path) -> None:
    repository = tmp_path / "source"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "PGRR Test")
    _git(repository, "config", "user.email", "pgrr-test@example.invalid")
    _copy_student_release_inputs(repository)
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "teacher reference")
    _git(repository, "branch", "-M", "teacher/reference")

    source_head = _git(repository, "rev-parse", "HEAD^{commit}")
    tracked = repository / "pyproject.toml"
    tracked.write_text(
        tracked.read_text(encoding="utf-8") + "\n# retained teacher note\n",
        encoding="utf-8",
    )
    untracked = repository / "private-teacher-notes.txt"
    untracked.write_text("must remain byte-for-byte unchanged\n", encoding="utf-8")
    tracked_before = tracked.read_bytes()
    untracked_before = untracked.read_bytes()
    status_before = _git(repository, "status", "--porcelain=v1", "--untracked-files=all")

    script = repository / "scripts/teaching/make_student_branch.sh"
    refused = subprocess.run(
        [str(script)],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    assert refused.returncode == 1
    assert "--allow-source-dirty" in refused.stderr
    assert (
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/student/reproduce",
            ],
            check=False,
        ).returncode
        != 0
    )

    temporary_parent = tmp_path / "temporary-worktrees"
    temporary_parent.mkdir()
    environment = {**os.environ, "TMPDIR": str(temporary_parent)}
    created = subprocess.run(
        [str(script), "--allow-source-dirty"],
        cwd=repository,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    assert "using committed HEAD" in created.stderr
    assert _git(repository, "branch", "--show-current") == "teacher/reference"
    assert _git(repository, "rev-parse", "HEAD^{commit}") == source_head
    assert _git(repository, "status", "--porcelain=v1", "--untracked-files=all") == status_before
    assert tracked.read_bytes() == tracked_before
    assert untracked.read_bytes() == untracked_before
    assert _git(repository, "rev-parse", "student/reproduce^") == source_head
    assert "TODO(student)" in _git(
        repository,
        "show",
        "student/reproduce:packages/ramp_core/ramp_core/planning/astar.py",
    )
    assert _git(repository, "worktree", "list", "--porcelain").count("worktree ") == 1
    assert list(temporary_parent.iterdir()) == []

    student_tip = _git(repository, "rev-parse", "student/reproduce^{commit}")
    existing = subprocess.run(
        [str(script), "--allow-source-dirty"],
        cwd=repository,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert existing.returncode == 1
    assert "student branch already exists" in existing.stderr
    assert _git(repository, "rev-parse", "student/reproduce^{commit}") == student_tip
    assert _git(repository, "branch", "--show-current") == "teacher/reference"
    assert _git(repository, "status", "--porcelain=v1", "--untracked-files=all") == status_before


def test_installer_declares_all_seven_student_assignments() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    destinations = (
        "planning/astar.py",
        "action_space.py",
        "failure/rules.py",
        "planning/costs.py",
        "ramp_ml/bc.py",
        "offline_policy_ablation.py",
        "make_figures.py",
    )
    for destination in destinations:
        assert destination in source
    assert "TODO(student)" in source


def test_installer_applies_tasks_without_creating_a_git_branch(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    (fake_root / ".git").mkdir(parents=True)
    (fake_root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")

    required_sources = (
        "packages/ramp_core/ramp_core/failure/rules.py",
        "scripts/paper/make_figures.py",
    )
    for relative in required_sources:
        source = ROOT / relative
        destination = fake_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    specification = importlib.util.spec_from_file_location("student_installer", INSTALLER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.install(fake_root)

    assert "TODO(student)" in (
        fake_root / "packages/ramp_core/ramp_core/planning/astar.py"
    ).read_text(encoding="utf-8")
    rules = (fake_root / "packages/ramp_core/ramp_core/failure/rules.py").read_text(
        encoding="utf-8"
    )
    assert "STUDENT_TASK_BEGIN: failure_rules" in rules
    figures = (fake_root / "scripts/paper/make_figures.py").read_text(encoding="utf-8")
    assert "Student task: outcome by scenario and density" in figures
    assert (fake_root / "tests/student/test_student_tasks.py").is_file()
