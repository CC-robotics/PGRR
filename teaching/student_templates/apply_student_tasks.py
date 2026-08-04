#!/usr/bin/env python3
"""Install the reviewed student starters into an isolated branch worktree."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent

FILE_TEMPLATES = {
    "astar.py.template": "packages/ramp_core/ramp_core/planning/astar.py",
    "action_space.py.template": "packages/ramp_core/ramp_core/action_space.py",
    "costs.py.template": "packages/ramp_core/ramp_core/planning/costs.py",
    "bc.py.template": "packages/ramp_ml/ramp_ml/bc.py",
    "offline_policy_ablation.py.template": "scripts/evaluate/offline_policy_ablation.py",
    "test_student_tasks.py.template": "tests/student/test_student_tasks.py",
}

RULE_HELPERS = '''\
# STUDENT_TASK_BEGIN: failure_rules
def detect_freeze(
    window: list[TimedNavigationSample],
    sample: TimedNavigationSample,
    config: RuleFailureConfig,
) -> float:
    """Return a binary freeze score using only observable history.

    A freeze requires a complete time window, a goal farther than the goal
    threshold, low path displacement, and sustained evidence that the base
    planner requested motion or reported no valid control. Reaching the goal
    must suppress the label.
    """

    # TODO(student): implement the configured freeze rule from Assignment 3.
    _ = window, sample, config
    return 0.0


def detect_oscillation(
    window: list[TimedNavigationSample],
    config: RuleFailureConfig,
) -> float:
    """Return a binary oscillation score for a complete observable window.

    Ignore angular velocities within ``angular_deadband_radps``. Trigger only
    when the configured number of sign reversals occurs while goal progress
    remains below ``oscillation_progress_m``.
    """

    # TODO(student): implement the configured oscillation rule from Assignment 3.
    _ = window, config
    return 0.0
# STUDENT_TASK_END: failure_rules


'''

RULE_CALLS = """\
        freeze_window = self._window(self.config.freeze_window_s)
        freeze = detect_freeze(freeze_window, sample, self.config)

        oscillation_window = self._window(self.config.oscillation_window_s)
        oscillation = detect_oscillation(oscillation_window, self.config)

"""

FIGURE_TASK = '''\
def outcome_density_figure(results: pd.DataFrame, output: Path) -> None:
    """Plot method outcomes by scenario and crowd density.

    Use only rows accepted by ``_valid_rows``. Compare the central reference
    and proposed methods selected by ``_select_central_methods``. The finished
    vector figure must show per-scenario success and the terminal-outcome mix
    for low, medium, and high density without inventing missing observations.
    """

    # TODO(student): replace this labelled placeholder with Assignment 7's plot.
    _ = results
    figure, axis = plt.subplots(figsize=(7.05, 2.6), constrained_layout=True)
    axis.axis("off")
    axis.text(
        0.5,
        0.5,
        "Student task: outcome by scenario and density",
        ha="center",
        va="center",
        color=INK,
        transform=axis.transAxes,
    )
    _save_pdf(figure, output)


'''


def replace_region(source: str, start: str, end: str, replacement: str) -> str:
    """Replace exactly one source region, failing on release drift."""

    if source.count(start) != 1 or source.count(end) != 1:
        raise RuntimeError(f"expected one region delimited by {start!r} and {end!r}")
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[:begin] + replacement + source[finish:]


def install(root: Path) -> None:
    """Apply all seven assignments to a fresh PGRR worktree."""

    root = root.resolve()
    if not (root / "pyproject.toml").is_file() or not (root / ".git").exists():
        raise RuntimeError(f"not a PGRR Git worktree: {root}")

    for template_name, relative_destination in FILE_TEMPLATES.items():
        destination = root / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE_DIR / template_name, destination)

    rules_path = root / "packages/ramp_core/ramp_core/failure/rules.py"
    rules = rules_path.read_text(encoding="utf-8")
    if "STUDENT_TASK_BEGIN: failure_rules" in rules:
        raise RuntimeError("failure-rule student task is already installed")
    rules = rules.replace(
        "class RuleFailureDetector:\n",
        RULE_HELPERS + "class RuleFailureDetector:\n",
        1,
    )
    rules = replace_region(
        rules,
        "        freeze_window = self._window(self.config.freeze_window_s)\n",
        "        deadlock_window = self._window(self.config.deadlock_window_s)\n",
        RULE_CALLS,
    )
    rules = rules.replace(
        "from ramp_core.failure.metrics import angular_sign_changes, goal_progress, "
        "path_displacement\n",
        "from ramp_core.failure.metrics import goal_progress, path_displacement\n",
        1,
    )
    # After the student helpers remove the only NumPy-using oscillation body,
    # Ruff classifies NumPy and the project imports in one third-party block.
    rules = rules.replace(
        "import numpy as np\n\nfrom ramp_core",
        "import numpy as np\nfrom ramp_core",
        1,
    )
    rules_path.write_text(rules, encoding="utf-8")

    figures_path = root / "scripts/paper/make_figures.py"
    figures = figures_path.read_text(encoding="utf-8")
    figures = replace_region(
        figures,
        "def outcome_density_figure(results: pd.DataFrame, output: Path) -> None:\n",
        "def _bootstrap_median(",
        FIGURE_TASK,
    )
    figures = figures.replace(
        "from matplotlib.colors import LinearSegmentedColormap\n",
        "",
        1,
    )
    figures_path.write_text(figures, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_student_tasks.py WORKTREE_ROOT")
    install(Path(sys.argv[1]))
    print("Installed seven PGRR student tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
