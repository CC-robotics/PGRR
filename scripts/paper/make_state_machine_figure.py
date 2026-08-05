#!/usr/bin/env python3
"""Render the deployed recovery state machine as a publication vector figure.

The drawing is intentionally independent of experimental result files.  Its
state and transition inventories mirror ``ramp_core.state_machine`` and are
kept as public constants so a focused unit test can detect semantic drift.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[2]

# Three functional groups: classical/monitoring, learned recovery/rejoin, and
# safety/failure.  Neutral ink and gray are not used to encode state classes.
BLUE: Final = "#0072B2"
TEAL: Final = "#008F72"
ORANGE: Final = "#D55E00"
FUNCTIONAL_COLORS: Final = (BLUE, TEAL, ORANGE)

INK: Final = "#20262C"
MID_GREY: Final = "#5F6B73"
LINE_GREY: Final = "#89939A"
LIGHT_GREY: Final = "#F3F5F6"
WHITE: Final = "#FFFFFF"

DOUBLE_COLUMN_WIDTH_IN: Final = 7.16
FIGURE_HEIGHT_IN: Final = 4.35
TITLE_SIZE_PT: Final = 8.2
DETAIL_SIZE_PT: Final = 7.0

FIGURE_STATES: Final = (
    "NORMAL",
    "PENDING_RECOVERY",
    "RECOVERY",
    "REJOIN",
    "EMERGENCY_STOP",
    "FAILED",
    "SUCCEEDED",
)

# State-changing branches in RecoveryStateMachine.update, excluding global
# emergency and terminal guards represented separately below.
NOMINAL_TRANSITIONS: Final = frozenset(
    {
        ("NORMAL", "PENDING_RECOVERY"),
        ("NORMAL", "RECOVERY"),
        ("NORMAL", "FAILED"),
        ("PENDING_RECOVERY", "NORMAL"),
        ("PENDING_RECOVERY", "RECOVERY"),
        ("PENDING_RECOVERY", "FAILED"),
        ("RECOVERY", "REJOIN"),
        ("REJOIN", "RECOVERY"),
        ("REJOIN", "NORMAL"),
    }
)
SAFETY_PREEMPT_SOURCES: Final = frozenset(
    {"NORMAL", "PENDING_RECOVERY", "RECOVERY", "REJOIN"}
)
SAFETY_CLEAR_TARGETS: Final = frozenset(
    {"NORMAL", "PENDING_RECOVERY", "RECOVERY", "REJOIN"}
)
GLOBAL_TERMINAL_TARGETS: Final = frozenset({"FAILED", "SUCCEEDED"})
GLOBAL_FAILURE_GUARDS: Final = frozenset(
    {"unrecoverable_failure", "recovery_sequence_timeout"}
)


@dataclass(frozen=True)
class NodeStyle:
    """Geometry and semantic style for one real state."""

    xy: tuple[float, float]
    width: float
    height: float
    title: str
    detail: str
    edge: str
    fill: str

    @property
    def center(self) -> tuple[float, float]:
        return self.xy[0] + self.width / 2.0, self.xy[1] + self.height / 2.0


STATE_LAYOUT: Final = {
    "NORMAL": NodeStyle(
        (0.035, 0.400),
        0.150,
        0.150,
        "NORMAL",
        "Nav2 tracks\nthe original goal",
        BLUE,
        "#EAF3F8",
    ),
    "PENDING_RECOVERY": NodeStyle(
        (0.265, 0.400),
        0.175,
        0.150,
        "PENDING RECOVERY",
        "debounce + cooldown",
        BLUE,
        "#EAF3F8",
    ),
    "RECOVERY": NodeStyle(
        (0.515, 0.400),
        0.165,
        0.150,
        "RECOVERY",
        "bounded masked\nrecovery option",
        TEAL,
        "#E6F3EF",
    ),
    "REJOIN": NodeStyle(
        (0.795, 0.400),
        0.145,
        0.150,
        "REJOIN",
        "restore original goal;\nverify progress",
        TEAL,
        "#E6F3EF",
    ),
    "EMERGENCY_STOP": NodeStyle(
        (0.400, 0.810),
        0.200,
        0.140,
        "EMERGENCY STOP",
        "hold while hazardous;\nstop or bounded escape",
        ORANGE,
        "#FFF0E8",
    ),
    "FAILED": NodeStyle(
        (0.035, 0.025),
        0.150,
        0.115,
        "FAILED",
        "terminal until reset",
        ORANGE,
        "#FFF0E8",
    ),
    "SUCCEEDED": NodeStyle(
        (0.810, 0.025),
        0.155,
        0.115,
        "SUCCEEDED",
        "terminal until reset",
        TEAL,
        "#E6F3EF",
    ),
}


def _configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": DETAIL_SIZE_PT,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
            "axes.facecolor": WHITE,
        }
    )


def _state_node(axis: Axes, state: str) -> None:
    style = STATE_LAYOUT[state]
    patch = FancyBboxPatch(
        style.xy,
        style.width,
        style.height,
        boxstyle="round,pad=0.008,rounding_size=0.018",
        facecolor=style.fill,
        edgecolor=style.edge,
        linewidth=1.15,
        zorder=5,
    )
    axis.add_patch(patch)
    center_x, center_y = style.center
    axis.text(
        center_x,
        center_y + 0.029,
        style.title,
        ha="center",
        va="center",
        fontsize=TITLE_SIZE_PT,
        fontweight="semibold",
        color=INK,
        zorder=6,
    )
    axis.text(
        center_x,
        center_y - 0.035,
        style.detail,
        ha="center",
        va="center",
        fontsize=DETAIL_SIZE_PT,
        color=MID_GREY,
        linespacing=1.12,
        zorder=6,
    )


def _box(
    axis: Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    title: str,
    detail: str,
    *,
    edge: str = LINE_GREY,
    fill: str = LIGHT_GREY,
    linestyle: str = "--",
) -> None:
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.007,rounding_size=0.012",
        facecolor=fill,
        edgecolor=edge,
        linewidth=0.85,
        linestyle=linestyle,
        zorder=3,
    )
    axis.add_patch(patch)
    axis.text(
        xy[0] + 0.012,
        xy[1] + height - 0.024,
        title,
        ha="left",
        va="top",
        fontsize=TITLE_SIZE_PT,
        fontweight="semibold",
        color=INK,
        zorder=4,
    )
    axis.text(
        xy[0] + 0.012,
        xy[1] + height - 0.060,
        detail,
        ha="left",
        va="top",
        fontsize=DETAIL_SIZE_PT,
        color=MID_GREY,
        linespacing=1.12,
        zorder=4,
    )


def _arrow(
    axis: Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = MID_GREY,
    connectionstyle: str = "arc3",
    linestyle: str = "-",
    linewidth: float = 0.95,
    mutation_scale: float = 8.5,
    zorder: int = 2,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=mutation_scale,
            linewidth=linewidth,
            linestyle=linestyle,
            color=color,
            connectionstyle=connectionstyle,
            shrinkA=1.0,
            shrinkB=1.0,
            zorder=zorder,
        )
    )


def _polyline_arrow(
    axis: Axes,
    points: tuple[tuple[float, float], ...],
    *,
    color: str = MID_GREY,
    linestyle: str = "-",
) -> None:
    codes = [MplPath.MOVETO, *([MplPath.LINETO] * (len(points) - 1))]
    path = MplPath(points, codes)
    axis.add_patch(
        FancyArrowPatch(
            path=path,
            arrowstyle="-|>",
            mutation_scale=8.5,
            linewidth=0.95,
            linestyle=linestyle,
            color=color,
            shrinkA=0.5,
            shrinkB=0.5,
            zorder=2,
        )
    )


def _edge_label(
    axis: Axes,
    xy: tuple[float, float],
    text: str,
    *,
    color: str = MID_GREY,
    ha: str = "center",
    va: str = "center",
) -> None:
    axis.text(
        *xy,
        text,
        ha=ha,
        va=va,
        fontsize=DETAIL_SIZE_PT,
        color=color,
        linespacing=1.12,
        bbox={"facecolor": WHITE, "edgecolor": "none", "pad": 0.7, "alpha": 0.96},
        zorder=7,
    )


def _draw_nominal_flow(axis: Axes) -> None:
    # Main path: nominal planning, trigger confirmation, bounded option, rejoin.
    _arrow(axis, (0.185, 0.475), (0.265, 0.475), color=BLUE)
    _edge_label(axis, (0.225, 0.505), "high")

    _arrow(axis, (0.440, 0.475), (0.515, 0.475), color=TEAL)

    _arrow(axis, (0.680, 0.490), (0.795, 0.490), color=TEAL)
    _edge_label(
        axis,
        (0.738, 0.585),
        "clear + done/progress\nor option timeout",
    )

    # A configuration may satisfy confirmation while still in NORMAL.
    _arrow(
        axis,
        (0.175, 0.540),
        (0.525, 0.540),
        color=TEAL,
        connectionstyle="arc3,rad=-0.22",
    )
    _edge_label(axis, (0.350, 0.640), "confirmed while still NORMAL")

    # Pending cancellation and bounded rejoin retry are shown on separate lanes.
    _arrow(
        axis,
        (0.265, 0.425),
        (0.185, 0.425),
        color=BLUE,
        connectionstyle="arc3,rad=-0.45",
    )
    _edge_label(axis, (0.225, 0.350), "not high")

    _arrow(
        axis,
        (0.795, 0.425),
        (0.680, 0.425),
        color=TEAL,
        connectionstyle="arc3,rad=-0.42",
    )
    _edge_label(
        axis,
        (0.738, 0.335),
        r"high / $T_{rejoin}$"
        "\nretry count $<R$",
    )

    # REJOIN returns control only after observed progress, or after the bounded
    # retry budget is exhausted.  The original goal has already been reissued
    # on entry to REJOIN by the recovery manager.
    _polyline_arrow(
        axis,
        ((0.868, 0.400), (0.868, 0.255), (0.110, 0.255), (0.110, 0.400)),
        color=TEAL,
    )
    _edge_label(
        axis,
        (0.490, 0.225),
        "progress + low risk, or retries exhausted",
        color=TEAL,
    )


def _draw_safety_priority(axis: Axes) -> None:
    # Every nonterminal navigation state feeds one common safety-preemption
    # rail.  This avoids four crossing copies of the same transition.
    centers = [STATE_LAYOUT[name].center[0] for name in SAFETY_PREEMPT_SOURCES]
    bus_y = 0.715
    for center_x in centers:
        axis.plot(
            [center_x, center_x],
            [0.550, bus_y],
            color=ORANGE,
            linewidth=0.75,
            linestyle=(0, (2.0, 2.0)),
            zorder=1,
        )
    axis.plot(
        [min(centers), max(centers)],
        [bus_y, bus_y],
        color=ORANGE,
        linewidth=0.95,
        zorder=1,
    )
    _arrow(axis, (0.500, bus_y), (0.500, 0.810), color=ORANGE, linewidth=1.05)
    _edge_label(
        axis,
        (0.500, 0.735),
        "hazard preempts nominal state logic",
        color=ORANGE,
    )

    _box(
        axis,
        (0.015, 0.755),
        0.330,
        0.230,
        "HYSTERESIS + BOUNDS",
        r"high: $f>\tau_{on}$ for $N_{on}$ frames + cooldown"
        "\n"
        r"clear: $f<\tau_{off}$ for $N_{off}$ frames + hold"
        "\n"
        r"option: $T_{rec}/T_{ext}$; rejoin: $T_{rejoin}$; budgets: $K,R$"
        "\n"
        r"$T_{seq}$ spans recovery, rejoin, and emergency stops"
        "\nmeaningful goal progress resets " + r"$K$ and $T_{seq}$",
    )

    _box(
        axis,
        (0.655, 0.755),
        0.330,
        0.230,
        "HAZARD-CLEAR ROUTING",
        r"saved $\in\{$RECOVERY, REJOIN$\}$; high: $f>\tau_{on}$"
        "\n"
        r"high + saved $\rightarrow$ RECOVERY"
        "\n"
        r"high + other $\rightarrow$ PENDING"
        "\n"
        r"else + saved $\rightarrow$ REJOIN"
        "\n"
        r"else + other $\rightarrow$ NORMAL",
        edge=ORANGE,
        fill="#FFF8F4",
    )
    _arrow(axis, (0.600, 0.880), (0.655, 0.880), color=ORANGE)


def _draw_terminal_guards(axis: Axes) -> None:
    axis.text(
        0.500,
        0.180,
        r"NONTERMINAL PRIORITY: goal $\rightarrow$ unrecoverable $\rightarrow$ "
        r"$T_{seq}$ cap $\rightarrow$ safety $\rightarrow$ state logic",
        ha="center",
        va="center",
        fontsize=DETAIL_SIZE_PT,
        color=MID_GREY,
        zorder=4,
    )
    _box(
        axis,
        (0.235, 0.010),
        0.290,
        0.145,
        "FAILURE GUARDS",
        "unrecoverable: any nonterminal state\n"
        + r"$T_{seq}$ expired: any active sequence"
        + "\n"
        + r"$K$ exhausted: NORMAL / PENDING",
        edge=ORANGE,
        fill="#FFF8F4",
    )
    _arrow(axis, (0.235, 0.084), (0.185, 0.084), color=ORANGE)
    _box(
        axis,
        (0.590, 0.028),
        0.170,
        0.112,
        "GOAL GUARD",
        "goal reached\nchecked first",
        edge=TEAL,
        fill="#F1FAF7",
    )
    _arrow(axis, (0.760, 0.084), (0.810, 0.084), color=TEAL)


def build_figure() -> Figure:
    """Build the state-machine figure without writing it to disk."""

    if set(STATE_LAYOUT) != set(FIGURE_STATES):
        missing = sorted(set(FIGURE_STATES) - set(STATE_LAYOUT))
        extra = sorted(set(STATE_LAYOUT) - set(FIGURE_STATES))
        raise RuntimeError(f"state layout drift: missing={missing}, extra={extra}")

    _configure_matplotlib()
    figure, axis = plt.subplots(figsize=(DOUBLE_COLUMN_WIDTH_IN, FIGURE_HEIGHT_IN))
    figure.subplots_adjust(left=0.012, right=0.988, bottom=0.025, top=0.975)
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")

    _draw_nominal_flow(axis)
    _draw_safety_priority(axis)
    _draw_terminal_guards(axis)
    for state in FIGURE_STATES:
        _state_node(axis, state)

    # Entry marker is deliberately not styled as an additional state.
    axis.plot([0.012], [0.505], marker="o", markersize=3.0, color=BLUE, zorder=6)
    _arrow(axis, (0.015, 0.505), (0.035, 0.505), color=BLUE, mutation_scale=7.5)
    return figure


def generate(output_dir: Path, stem: str = "recovery_state_machine") -> tuple[Path, Path]:
    """Write vector PDF and 300-dpi PNG versions of the same deterministic figure."""

    if not stem or Path(stem).name != stem:
        raise ValueError("stem must be a non-empty filename component")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"{stem}.pdf"
    png_path = output_dir / f"{stem}.png"
    figure = build_figure()
    figure.savefig(pdf_path, format="pdf", dpi=300, metadata={"Creator": "PGRR"})
    figure.savefig(png_path, format="png", dpi=300, metadata={"Software": "PGRR"})
    plt.close(figure)
    return pdf_path, png_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "paper" / "figures",
        help="Destination directory (default: paper/figures)",
    )
    parser.add_argument("--stem", default="recovery_state_machine")
    return parser


def main() -> int:
    args = _parser().parse_args()
    outputs = generate(args.output_dir, args.stem)
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
