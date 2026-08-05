#!/usr/bin/env python3
"""Generate result-independent vector method figures for the PGRR paper."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

try:
    from make_figures import action_space_expert_figure
except ModuleNotFoundError:  # Imported as a namespace module by pytest.
    from scripts.paper.make_figures import action_space_expert_figure

ROOT = Path(__file__).resolve().parents[2]

INK = "#1B1F23"
EDGE = "#53616A"
NEUTRAL = "#F3F5F6"
WORLD = "#EAF2F8"
RECOVERY = "#E8F6F3"
RECOVERY_EDGE = "#16836B"
GUARD = "#FFF4E6"
GUARD_EDGE = "#D97706"
ZONE = "#FAFBFC"


def _configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 7.0,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _box(
    axis: Axes,
    xywh: tuple[float, float, float, float],
    label: str,
    *,
    facecolor: str,
    edgecolor: str = EDGE,
    linewidth: float = 1.0,
) -> None:
    x_value, y_value, width, height = xywh
    axis.add_patch(
        FancyBboxPatch(
            (x_value, y_value),
            width,
            height,
            boxstyle="round,pad=0.009,rounding_size=0.018",
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
            zorder=3,
        )
    )
    axis.text(
        x_value + width / 2.0,
        y_value + height / 2.0,
        label,
        ha="center",
        va="center",
        fontsize=7.0,
        color=INK,
        linespacing=1.05,
        zorder=4,
    )


def _diamond(
    axis: Axes,
    center: tuple[float, float],
    size: tuple[float, float],
    label: str,
) -> None:
    x_value, y_value = center
    width, height = size
    points = (
        (x_value, y_value + height / 2.0),
        (x_value + width / 2.0, y_value),
        (x_value, y_value - height / 2.0),
        (x_value - width / 2.0, y_value),
    )
    axis.add_patch(
        Polygon(
            points,
            closed=True,
            facecolor=GUARD,
            edgecolor=GUARD_EDGE,
            linewidth=1.05,
            zorder=3,
        )
    )
    axis.text(
        x_value,
        y_value,
        label,
        ha="center",
        va="center",
        fontsize=7.0,
        color=INK,
        linespacing=1.0,
        zorder=4,
    )


def _arrow(
    axis: Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    label: str | None = None,
    label_position: tuple[float, float] | None = None,
    color: str = EDGE,
    rad: float = 0.0,
    dashed: bool = False,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=8.5,
            linewidth=0.9,
            linestyle="--" if dashed else "-",
            color=color,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=1.5,
            shrinkB=1.5,
            zorder=2,
        )
    )
    if label is not None and label_position is not None:
        axis.text(
            *label_position,
            label,
            ha="center",
            va="center",
            fontsize=7.0,
            color=color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.7},
            zorder=5,
        )


def _save(figure: Figure, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        bbox_inches="tight",
        pad_inches=0.03,
        metadata={
            "CreationDate": None,
            "ModDate": None,
            "Creator": "PGRR method figure generator",
        },
    )
    plt.close(figure)


def system_architecture_figure(output: Path) -> None:
    """Render the sensing--planning--execution loop and training-only branch."""

    _configure_matplotlib()
    figure, axis = plt.subplots(figsize=(7.16, 3.25))
    figure.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")

    axis.add_patch(
        FancyBboxPatch(
            (0.012, 0.315),
            0.976,
            0.655,
            boxstyle="round,pad=0.008,rounding_size=0.018",
            facecolor="white",
            edgecolor="#C6CED3",
            linewidth=0.8,
            zorder=0,
        )
    )
    axis.text(
        0.026,
        0.945,
        "DEPLOYMENT  ·  OBSERVABLE CLOSED LOOP",
        ha="left",
        va="center",
        fontsize=8.5,
        fontweight="semibold",
        color=EDGE,
    )

    _box(axis, (0.035, 0.685, 0.125, 0.125), "Dynamic world\n+ robot", facecolor=WORLD)
    _box(
        axis,
        (0.205, 0.685, 0.165, 0.125),
        "LiDAR + navigation\nhistory",
        facecolor=WORLD,
    )
    _diamond(axis, (0.460, 0.747), (0.130, 0.155), "Persistent\nfailure?")
    _box(axis, (0.605, 0.710, 0.145, 0.105), "Nav2 DWB\nnominal / subgoal", facecolor=WORLD)
    _box(
        axis,
        (0.815, 0.710, 0.145, 0.105),
        "Safety supervisor\nstopping override",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
    )
    _box(
        axis,
        (0.485, 0.430, 0.145, 0.115),
        "Planning mask\nlegal actions",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
    )
    _box(
        axis,
        (0.675, 0.430, 0.135, 0.115),
        "DAgger policy\n25 decisions",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
    )
    _box(
        axis,
        (0.850, 0.430, 0.110, 0.115),
        "Goal / mode\nmux",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
    )

    _arrow(axis, (0.160, 0.747), (0.205, 0.747), label="sense", label_position=(0.182, 0.777))
    _arrow(
        axis,
        (0.370, 0.747),
        (0.395, 0.747),
        label="rule scores + hysteresis",
        label_position=(0.383, 0.825),
    )
    _arrow(axis, (0.525, 0.747), (0.605, 0.762), label="no", label_position=(0.563, 0.785))
    _arrow(
        axis,
        (0.460, 0.670),
        (0.558, 0.545),
        label="yes",
        label_position=(0.493, 0.610),
    )
    _arrow(axis, (0.630, 0.488), (0.675, 0.488), label="mask", label_position=(0.653, 0.517))
    _arrow(axis, (0.810, 0.488), (0.850, 0.488), label="action", label_position=(0.830, 0.517))
    _arrow(
        axis,
        (0.904, 0.545),
        (0.733, 0.710),
        label="bounded recovery",
        label_position=(0.840, 0.635),
        rad=0.11,
    )
    _arrow(axis, (0.750, 0.762), (0.815, 0.762), label="cmd", label_position=(0.783, 0.790))
    _arrow(
        axis,
        (0.888, 0.815),
        (0.098, 0.810),
        label="safe action · environment feedback",
        label_position=(0.505, 0.875),
        color=RECOVERY_EDGE,
        rad=0.10,
    )

    axis.add_patch(
        FancyBboxPatch(
            (0.150, 0.035),
            0.665,
            0.230,
            boxstyle="round,pad=0.010,rounding_size=0.018",
            facecolor=ZONE,
            edgecolor="#AAB5BC",
            linewidth=0.8,
            linestyle="--",
            zorder=0,
        )
    )
    axis.text(
        0.168,
        0.237,
        "TRAINING ONLY  ·  PRIVILEGED STATE ISOLATED FROM DEPLOYMENT",
        ha="left",
        va="center",
        fontsize=8.5,
        fontweight="semibold",
        color=EDGE,
    )
    _box(axis, (0.190, 0.090, 0.135, 0.095), "Privileged\nsimulator state", facecolor=NEUTRAL)
    _box(
        axis,
        (0.405, 0.090, 0.155, 0.095),
        "3-s rollout expert\nall legal actions",
        facecolor=NEUTRAL,
    )
    _box(axis, (0.640, 0.090, 0.135, 0.095), "Uniform BC +\n2 DAgger rounds", facecolor=NEUTRAL)
    _arrow(axis, (0.325, 0.138), (0.405, 0.138), label="state", label_position=(0.365, 0.168))
    _arrow(axis, (0.560, 0.138), (0.640, 0.138), label="labels", label_position=(0.600, 0.168))
    _arrow(
        axis,
        (0.708, 0.185),
        (0.742, 0.430),
        label="export ONNX",
        label_position=(0.762, 0.304),
        color=RECOVERY_EDGE,
        dashed=True,
        rad=-0.04,
    )
    _save(figure, output)


def generate_method_figures(output_dir: Path) -> list[Path]:
    """Generate every paper figure that does not depend on final results."""

    outputs = [
        output_dir / "system_architecture.pdf",
        output_dir / "action_space_expert.pdf",
    ]
    system_architecture_figure(outputs[0])
    action_space_expert_figure(outputs[1])
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "paper/figures")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_method_figures(args.output_dir)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
