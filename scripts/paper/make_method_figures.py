#!/usr/bin/env python3
"""Generate result-independent vector method figures for the PGRR paper."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import yaml  # type: ignore[import-untyped]
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

PAPER_SCRIPT_DIR = Path(__file__).resolve().parent
if str(PAPER_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(PAPER_SCRIPT_DIR))

from make_state_machine_figure import build_figure as build_state_machine_figure  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_CONFIG = ROOT / "configs/experiments/scenario_catalog_moderate_v6.yaml"
EXPECTED_BENCHMARK_ID = "moderate_social_navigation_v6"

INK = "#1B1F23"
EDGE = "#53616A"
NEUTRAL = "#F3F5F6"
WORLD = "#EAF2F8"
WORLD_EDGE = "#356E9F"
RECOVERY = "#E8F6F3"
RECOVERY_EDGE = "#00866F"
GUARD = "#FFF4E6"
GUARD_EDGE = "#D55E00"
ZONE = "#FAFBFC"
WHITE = "#FFFFFF"

# Neutral gray is used for structure, not to encode a fourth category.
FUNCTIONAL_COLORS = (WORLD_EDGE, RECOVERY_EDGE, GUARD_EDGE)
ACTION_RADII_M = (0.6, 1.0, 1.4)
ACTION_ANGLES_DEG = (-90, -60, -30, 0, 30, 60, 90)
SPECIAL_ACTIONS = ((21, "WAIT"), (22, "BACKUP"), (23, "REPLAN"), (24, "CONTINUE"))
EXPECTED_FAMILIES = (
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
)

FIGURE_TITLE_SIZE = 8.4
FIGURE_TEXT_SIZE = 6.4
NAV2_BASIS = "Nav2 DWB Controller docs + navigation2/nav2_dwb_controller/README.md"
FOX_BASIS = "Fox, Burgard & Thrun (1997), doi:10.1109/100.580977"
ROSS_BASIS = "Ross, Gordon & Bagnell (2011), PMLR 15:627-635"


def _configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "svg.hashsalt": "pgrr-method-figures-v1",
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 7.0,
            "axes.facecolor": WHITE,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
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
    fontsize: float = 7.0,
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
        fontsize=fontsize,
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
    fontsize: float = 7.0,
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
            fontsize=fontsize,
            color=color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.7},
            zorder=5,
        )


def _figure_title(figure: Figure, title: str) -> None:
    figure.text(
        0.025,
        0.965,
        title,
        ha="left",
        va="top",
        fontsize=FIGURE_TITLE_SIZE,
        fontweight="semibold",
        color=INK,
    )


def _provenance_footer(figure: Figure, basis: str, *, kind: str = "explanatory redraw") -> None:
    figure.text(
        0.50,
        0.018,
        f"Original {kind}; not a runtime result. Basis: {basis}.",
        ha="center",
        va="bottom",
        fontsize=FIGURE_TEXT_SIZE,
        color=EDGE,
    )


def _robot_icon(axis: Axes, center: tuple[float, float], *, color: str = RECOVERY_EDGE) -> None:
    x_value, y_value = center
    axis.add_patch(
        FancyBboxPatch(
            (x_value - 0.035, y_value - 0.026),
            0.070,
            0.052,
            boxstyle="round,pad=0.004,rounding_size=0.012",
            facecolor=WHITE,
            edgecolor=color,
            linewidth=1.1,
            zorder=5,
        )
    )
    axis.add_patch(Circle((x_value - 0.026, y_value - 0.032), 0.009, color=color, zorder=5))
    axis.add_patch(Circle((x_value + 0.026, y_value - 0.032), 0.009, color=color, zorder=5))
    axis.add_patch(
        FancyArrowPatch(
            (x_value, y_value),
            (x_value + 0.055, y_value),
            arrowstyle="-|>",
            mutation_scale=7.0,
            linewidth=0.9,
            color=color,
            zorder=6,
        )
    )


def _blank_figure(
    title: str, *, figsize: tuple[float, float] = (7.16, 3.20)
) -> tuple[Figure, Axes]:
    _configure_matplotlib()
    figure, axis = plt.subplots(figsize=figsize)
    figure.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.15)
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    _figure_title(figure, title)
    return figure, axis


def _save(figure: Figure, output: Path) -> None:
    suffix = output.suffix.lower()
    if suffix not in {".pdf", ".svg"}:
        raise ValueError(f"method figures require .pdf or .svg output, got {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = (
        {
            "CreationDate": None,
            "ModDate": None,
            "Creator": "PGRR method figure generator",
        }
        if suffix == ".pdf"
        else {"Creator": "PGRR method figure generator", "Date": None}
    )
    figure.savefig(
        output,
        format=suffix.removeprefix("."),
        bbox_inches="tight",
        pad_inches=0.03,
        metadata=metadata,
    )
    if suffix == ".svg":
        # Matplotlib emits path commands with line-ending spaces. Canonicalize
        # the text so generated vectors pass Git whitespace checks and remain
        # stable review artifacts without changing their rendered geometry.
        svg_text = output.read_text(encoding="utf-8")
        output.write_text(
            "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
            encoding="utf-8",
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

    _box(
        axis,
        (0.035, 0.685, 0.125, 0.125),
        "Dynamic world\n+ robot",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
    )
    _box(
        axis,
        (0.205, 0.685, 0.165, 0.125),
        "LiDAR + navigation\nhistory",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
    )
    _diamond(axis, (0.460, 0.747), (0.130, 0.155), "Persistent\nfailure?")
    _box(
        axis,
        (0.605, 0.710, 0.145, 0.105),
        "Nav2 DWB\nnominal / subgoal",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
    )
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


def recovery_state_machine_figure(output: Path) -> None:
    """Render the implementation-synchronised seven-state controller."""

    _configure_matplotlib()
    _save(build_state_machine_figure(), output)


def _candidate_actions() -> list[tuple[int, float, float]]:
    candidates: list[tuple[int, float, float]] = []
    for radius in ACTION_RADII_M:
        for angle_degrees in ACTION_ANGLES_DEG:
            angle = math.radians(angle_degrees)
            candidates.append((len(candidates), radius * math.cos(angle), radius * math.sin(angle)))
    if len(candidates) + len(SPECIAL_ACTIONS) != 25:
        raise RuntimeError("recovery action inventory no longer contains exactly 25 actions")
    return candidates


def action_space_expert_figure(output: Path) -> None:
    """Draw the fixed action lattice and a non-empirical expert-rollout schematic."""

    _configure_matplotlib()
    candidates = _candidate_actions()
    pedestrian_x = 0.90
    masked = {
        action_id
        for action_id, x_value, y_value in candidates
        if abs(x_value - pedestrian_x) < 0.28 and abs(y_value) <= 0.95
    }
    selected = 12  # 1.0 m, +60 deg: illustrative legal candidate, not a measured decision.

    figure, axes = plt.subplots(
        1,
        2,
        figsize=(7.16, 3.18),
        gridspec_kw={"width_ratios": [1.04, 0.96]},
    )
    figure.subplots_adjust(left=0.055, right=0.990, top=0.900, bottom=0.235, wspace=0.22)

    lattice = axes[0]
    for radius in ACTION_RADII_M:
        lattice.add_patch(
            Circle(
                (0.0, 0.0),
                radius,
                fill=False,
                color="#C8D0D5",
                linewidth=0.75,
                linestyle="--",
                zorder=0,
            )
        )
    for action_id, x_value, y_value in candidates:
        lattice.plot([0.0, x_value], [0.0, y_value], color=WORLD_EDGE, alpha=0.18, lw=0.6)
        if action_id in masked:
            lattice.scatter(
                [x_value],
                [y_value],
                marker="x",
                s=25,
                linewidth=1.05,
                color=GUARD_EDGE,
                zorder=4,
            )
        else:
            is_selected = action_id == selected
            lattice.scatter(
                [x_value],
                [y_value],
                marker="*" if is_selected else "o",
                s=53 if is_selected else 22,
                color=RECOVERY_EDGE if is_selected else WORLD_EDGE,
                edgecolor=WHITE,
                linewidth=0.45,
                zorder=4,
            )
        lattice.text(
            x_value,
            y_value + 0.061,
            str(action_id),
            ha="center",
            va="bottom",
            fontsize=6.5,
            color=INK,
        )
    lattice.add_patch(
        FancyArrowPatch(
            (pedestrian_x, -1.15),
            (pedestrian_x, 1.12),
            arrowstyle="-|>",
            mutation_scale=8,
            color=GUARD_EDGE,
            linewidth=1.05,
            linestyle="--",
            zorder=2,
        )
    )
    lattice.scatter([0.0], [0.0], marker=">", s=62, color=RECOVERY_EDGE, zorder=5)
    lattice.scatter([pedestrian_x], [-1.15], marker="o", s=30, color=GUARD_EDGE, zorder=5)
    lattice.set(
        xlim=(-0.17, 1.58),
        ylim=(-1.53, 1.53),
        xlabel="Robot-frame $x$ [m]",
        ylabel="Robot-frame $y$ [m]",
    )
    lattice.set_aspect("equal")
    lattice.grid(color="#E1E5E8", linewidth=0.45)
    lattice.set_axisbelow(True)
    lattice.set_title("(a) 21 temporary subgoals", loc="left", fontsize=8.2, fontweight="semibold")

    rollout = axes[1]
    rollout.set_xlim(-0.08, 1.55)
    rollout.set_ylim(-0.82, 0.96)
    rollout.set_aspect("equal")
    rollout.grid(color="#E1E5E8", linewidth=0.45)
    rollout.set_axisbelow(True)
    rollout.set_xlabel("Local horizon $x$ [m]")
    rollout.set_ylabel("Local horizon $y$ [m]")
    rollout.set_title(
        "(b) Masked short-horizon expert", loc="left", fontsize=8.2, fontweight="semibold"
    )
    rollout.add_patch(Rectangle((0.82, -0.78), 0.19, 1.56, color=GUARD, ec="none", zorder=0))
    rollout.add_patch(
        FancyArrowPatch(
            (0.92, -0.64),
            (0.92, 0.72),
            arrowstyle="-|>",
            mutation_scale=8,
            color=GUARD_EDGE,
            linestyle="--",
            linewidth=1.1,
            zorder=3,
        )
    )
    rollout.scatter([0.92], [-0.64], s=28, color=GUARD_EDGE, zorder=4)
    trajectories = (
        (
            [0.0, 0.35, 0.72, 1.08, 1.42],
            [0.0, 0.15, 0.44, 0.57, 0.58],
            RECOVERY_EDGE,
            2.0,
            "selected legal",
        ),
        (
            [0.0, 0.38, 0.76, 1.12, 1.42],
            [0.0, -0.12, -0.33, -0.40, -0.38],
            WORLD_EDGE,
            1.1,
            "other legal",
        ),
        ([0.0, 0.40, 0.79, 1.12, 1.42], [0.0, 0.01, 0.04, 0.08, 0.10], GUARD_EDGE, 1.1, "masked"),
    )
    for x_values, y_values, color, linewidth, label in trajectories:
        rollout.plot(
            x_values,
            y_values,
            color=color,
            linewidth=linewidth,
            linestyle="--" if label == "masked" else "-",
            label=label,
            zorder=4,
        )
        rollout.scatter([x_values[-1]], [y_values[-1]], s=18, color=color, zorder=5)
    rollout.scatter([0.0], [0.0], marker=">", s=58, color=RECOVERY_EDGE, zorder=6)
    rollout.legend(loc="upper left", frameon=False, fontsize=6.8, handlelength=1.8)
    rollout.text(
        0.02,
        -0.75,
        "mask $\u2192$ 3 s rollout ranking $\u2192$ action + cost margin",
        color=INK,
        fontsize=7.0,
        ha="left",
        va="bottom",
    )

    special_text = "   ".join(f"{action_id}: {label}" for action_id, label in SPECIAL_ACTIONS)
    figure.text(0.50, 0.105, special_text, ha="center", va="center", color=INK, fontsize=7.2)
    figure.text(
        0.50,
        0.025,
        "Schematic only; pedestrian prediction and rollout paths are explanatory, "
        "not episode measurements.",
        ha="center",
        va="center",
        color=GUARD_EDGE,
        fontsize=6.9,
        fontweight="semibold",
    )
    _save(figure, output)


def _load_scenario_inventory(config_path: Path) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Read family/layout and density counts only; never inspect split manifests or results."""

    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"cannot read scenario catalog {config_path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("scenario catalog must be a mapping")
    if payload.get("benchmark_id") != EXPECTED_BENCHMARK_ID:
        raise ValueError(
            "scenario catalog benchmark drift: "
            f"expected {EXPECTED_BENCHMARK_ID!r}, got {payload.get('benchmark_id')!r}"
        )
    raw_families = payload.get("families")
    raw_densities = payload.get("densities")
    if not isinstance(raw_families, list) or not isinstance(raw_densities, dict):
        raise ValueError("scenario catalog requires family and density inventories")
    families: list[tuple[str, str]] = []
    for item in raw_families:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("every scenario family requires string id and layout fields")
        family = str(item["id"])
        layout = str(item.get("layout", ""))
        if not layout:
            raise ValueError(f"scenario family {family!r} has no layout")
        families.append((family, layout))
    ids = tuple(family for family, _ in families)
    if ids != EXPECTED_FAMILIES:
        raise ValueError(f"scenario family inventory/order drift: {ids!r}")
    densities = {str(name): int(count) for name, count in raw_densities.items()}
    if densities != {"low": 1, "medium": 2, "high": 4}:
        raise ValueError(f"unexpected density inventory: {densities!r}")
    return families, densities


def _flow_arrow(
    axis: Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    pedestrian: bool = False,
    linewidth: float = 1.15,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=7.5,
            linewidth=linewidth,
            linestyle="--" if pedestrian else "-",
            color=GUARD_EDGE if pedestrian else WORLD_EDGE,
            zorder=3,
        )
    )


def _draw_scenario(axis: Axes, family: str, layout: str, panel: str) -> None:
    def wall(xy: tuple[float, float], width: float, height: float) -> Rectangle:
        return Rectangle(
            xy,
            width,
            height,
            facecolor=NEUTRAL,
            edgecolor=EDGE,
            linewidth=0.55,
            hatch="////",
        )

    axis.add_patch(Rectangle((-1.72, -0.90), 3.44, 1.80, fc=WHITE, ec="#D5DBDF", lw=0.55))
    if layout == "horizontal_corridor":
        axis.add_patch(wall((-1.72, -0.90), 3.44, 0.31))
        axis.add_patch(wall((-1.72, 0.59), 3.44, 0.31))
        _flow_arrow(axis, (-1.45, -0.14), (1.25, -0.14))
        _flow_arrow(axis, (1.35, 0.16), (-1.18, 0.16), pedestrian=True)
    elif layout in {"doorway", "temporary_blockage"}:
        axis.add_patch(wall((-0.22, -0.90), 0.44, 0.58))
        axis.add_patch(wall((-0.22, 0.32), 0.44, 0.58))
        _flow_arrow(axis, (-1.45, -0.12), (1.27, -0.12))
        if layout == "doorway":
            _flow_arrow(axis, (1.30, 0.16), (-0.85, 0.16), pedestrian=True)
        else:
            for y_value in (-0.25, 0.0, 0.25):
                axis.scatter([0.40], [y_value], s=16, color=GUARD_EDGE, zorder=4)
            axis.annotate(
                "pause",
                (0.40, 0.25),
                xytext=(0.75, 0.52),
                fontsize=6.5,
                color=GUARD_EDGE,
                arrowprops={"arrowstyle": "-", "color": GUARD_EDGE, "lw": 0.6},
            )
    elif layout == "crossing":
        _flow_arrow(axis, (-1.45, -0.14), (1.30, -0.14))
        _flow_arrow(axis, (0.14, -0.76), (0.14, 0.74), pedestrian=True)
    elif layout == "blind_corner":
        axis.add_patch(wall((-1.72, 0.25), 1.82, 0.65))
        axis.add_patch(wall((0.10, 0.25), 0.42, 0.65))
        _flow_arrow(axis, (-1.45, -0.18), (0.72, -0.18))
        _flow_arrow(axis, (0.90, 0.72), (0.90, -0.46), pedestrian=True)
    elif layout == "group_blocking":
        _flow_arrow(axis, (-1.45, -0.12), (1.30, -0.12))
        for x_value, y_value in ((0.05, -0.28), (0.35, -0.03), (0.08, 0.28), (0.59, 0.28)):
            axis.scatter([x_value], [y_value], s=17, color=GUARD_EDGE, zorder=4)
    elif layout == "overtaking":
        _flow_arrow(axis, (-1.45, -0.23), (1.30, -0.23))
        _flow_arrow(axis, (-0.35, 0.18), (0.72, 0.18), pedestrian=True)
    elif layout == "opposite_streams":
        axis.add_patch(wall((-1.72, -0.90), 3.44, 0.22))
        axis.add_patch(wall((-1.72, 0.68), 3.44, 0.22))
        _flow_arrow(axis, (-1.45, -0.28), (1.30, -0.28))
        for y_value in (0.00, 0.30):
            _flow_arrow(axis, (1.30, y_value), (-1.20, y_value), pedestrian=True, linewidth=0.85)
    else:
        raise ValueError(f"unsupported scenario layout {layout!r}")
    axis.set_xlim(-1.75, 1.75)
    axis.set_ylim(-0.93, 0.93)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_title(
        f"({panel}) {family.replace('_', ' ')}",
        loc="left",
        fontsize=7.4,
        fontweight="semibold",
        pad=2.0,
    )
    for spine in axis.spines.values():
        spine.set_visible(False)


def scenario_overview_figure(output: Path, config_path: Path = DEFAULT_SCENARIO_CONFIG) -> None:
    """Render eight configuration-derived scenario schematics without episode data."""

    _configure_matplotlib()
    families, densities = _load_scenario_inventory(config_path)
    figure, axes = plt.subplots(2, 4, figsize=(7.16, 3.55))
    figure.subplots_adjust(
        left=0.020, right=0.995, top=0.910, bottom=0.155, wspace=0.12, hspace=0.27
    )
    for index, (axis, (family, layout)) in enumerate(zip(axes.flat, families, strict=True)):
        _draw_scenario(axis, family, layout, chr(ord("a") + index))
    figure.suptitle(
        "Eight deterministic dynamic-interaction families",
        x=0.02,
        y=0.975,
        ha="left",
        fontsize=8.5,
        fontweight="semibold",
        color=INK,
    )
    legend = (
        Line2D([0], [0], color=WORLD_EDGE, lw=1.3, label="robot route"),
        Line2D([0], [0], color=GUARD_EDGE, lw=1.1, ls="--", label="pedestrian route / actor"),
        Rectangle((0, 0), 1, 1, fc=NEUTRAL, ec=EDGE, hatch="////", label="static obstacle"),
    )
    figure.legend(
        handles=legend,
        loc="lower center",
        bbox_to_anchor=(0.50, 0.066),
        ncol=3,
        frameon=False,
        fontsize=7.0,
        handlelength=2.0,
    )
    density_text = ", ".join(f"{name}={count}" for name, count in densities.items())
    figure.text(
        0.50,
        0.018,
        f"Configured pedestrian counts: {density_text}. Schematics are not to scale "
        "and contain no outcome data.",
        ha="center",
        va="bottom",
        color=EDGE,
        fontsize=6.8,
    )
    _save(figure, output)


def dwb_nav2_role_figure(output: Path) -> None:
    """Explain DWB's local-controller role inside a Nav2 closed loop."""

    figure, axis = _blank_figure("DWB in Nav2: local trajectory control, not global planning")

    _box(
        axis,
        (0.035, 0.650, 0.140, 0.130),
        "Goal + map",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.220, 0.650, 0.155, 0.130),
        "Planner Server\nglobal path",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.035, 0.255, 0.140, 0.130),
        "Sensors + pose",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.220, 0.255, 0.155, 0.130),
        "Local costmap\nrobot state",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )

    axis.add_patch(
        FancyBboxPatch(
            (0.425, 0.270),
            0.325,
            0.555,
            boxstyle="round,pad=0.012,rounding_size=0.020",
            facecolor=ZONE,
            edgecolor=RECOVERY_EDGE,
            linewidth=1.0,
            linestyle="--",
        )
    )
    axis.text(
        0.445,
        0.785,
        "Controller Server",
        ha="left",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=EDGE,
        fontweight="semibold",
    )
    _box(
        axis,
        (0.465, 0.555, 0.245, 0.125),
        "DWB controller plugin\nsample trajectories",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.465, 0.350, 0.245, 0.125),
        "Critic plugins\nscore legal trajectories",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.588, 0.555), (0.588, 0.475), fontsize=FIGURE_TEXT_SIZE)

    _box(
        axis,
        (0.805, 0.545, 0.135, 0.135),
        "cmd_vel",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.805, 0.255, 0.135, 0.135),
        "Mobile robot\n+ world",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _robot_icon(axis, (0.873, 0.322))

    _arrow(axis, (0.175, 0.715), (0.220, 0.715), fontsize=FIGURE_TEXT_SIZE)
    _arrow(
        axis,
        (0.375, 0.715),
        (0.465, 0.620),
        label="path",
        label_position=(0.415, 0.680),
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.175, 0.320), (0.220, 0.320), fontsize=FIGURE_TEXT_SIZE)
    _arrow(
        axis,
        (0.375, 0.320),
        (0.465, 0.405),
        label="constraints",
        label_position=(0.415, 0.330),
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(
        axis,
        (0.710, 0.413),
        (0.805, 0.612),
        label="lowest legal score",
        label_position=(0.765, 0.505),
        color=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.873, 0.545), (0.873, 0.390), fontsize=FIGURE_TEXT_SIZE)
    _arrow(
        axis,
        (0.805, 0.300),
        (0.105, 0.280),
        label="motion changes the next observation",
        label_position=(0.275, 0.135),
        color=WORLD_EDGE,
        rad=-0.20,
        fontsize=FIGURE_TEXT_SIZE,
    )

    axis.text(
        0.588,
        0.300,
        "PGRR may change the temporary goal; DWB remains the motion executor.",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    _provenance_footer(figure, NAV2_BASIS)
    _save(figure, output)


def dwb_dynamic_window_figure(output: Path) -> None:
    """Show DWA ancestry while making DWB's pluggable generator boundary explicit."""

    figure, axis = _blank_figure(
        "DWA ancestry: conceptual velocity space; DWB generators are pluggable"
    )

    x0, y0, width, height = 0.070, 0.205, 0.430, 0.600
    axis.add_patch(Rectangle((x0, y0), width, height, fc=WORLD, ec=WORLD_EDGE, lw=0.9))
    axis.add_patch(
        Polygon(
            (
                (x0 + 0.015, y0 + height - 0.015),
                (x0 + 0.185, y0 + height - 0.015),
                (x0 + 0.080, y0 + 0.360),
                (x0 + 0.015, y0 + 0.330),
            ),
            closed=True,
            facecolor=GUARD,
            edgecolor=GUARD_EDGE,
            linewidth=0.8,
            hatch="////",
        )
    )
    reachable = Rectangle(
        (x0 + 0.170, y0 + 0.205),
        0.185,
        0.215,
        fc=RECOVERY,
        ec=RECOVERY_EDGE,
        lw=1.15,
    )
    axis.add_patch(reachable)
    for x_value in (x0 + 0.195, x0 + 0.245, x0 + 0.295, x0 + 0.335):
        for y_value in (y0 + 0.235, y0 + 0.285, y0 + 0.345, y0 + 0.395):
            axis.scatter([x_value], [y_value], s=8, color=WORLD_EDGE, zorder=4)
    axis.scatter(
        [x0 + 0.335],
        [y0 + 0.345],
        s=55,
        marker="*",
        color=RECOVERY_EDGE,
        edgecolor=WHITE,
        linewidth=0.5,
        zorder=5,
    )
    _arrow(
        axis,
        (x0, y0),
        (x0 + width + 0.025, y0),
        color=INK,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(
        axis,
        (x0, y0),
        (x0, y0 + height + 0.030),
        color=INK,
        fontsize=FIGURE_TEXT_SIZE,
    )
    axis.text(
        x0 + width + 0.020,
        y0 - 0.035,
        "$v_x$",
        ha="right",
        va="top",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    axis.text(
        x0 - 0.028,
        y0 + height + 0.020,
        "$\\omega$",
        ha="right",
        va="top",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    axis.text(
        x0 + 0.010,
        y0 + 0.030,
        "configured velocity bounds",
        ha="left",
        va="bottom",
        fontsize=FIGURE_TEXT_SIZE,
        color=WORLD_EDGE,
    )
    axis.text(
        x0 + 0.262,
        y0 + 0.313,
        "reachable / sampled\nconceptual window",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=RECOVERY_EDGE,
    )
    axis.text(
        x0 + 0.065,
        y0 + 0.525,
        "inadmissible",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=GUARD_EDGE,
    )

    axis.text(
        0.555,
        0.815,
        "DWB trajectory generation boundary",
        ha="left",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        fontweight="semibold",
        color=EDGE,
    )
    _box(
        axis,
        (0.555, 0.650, 0.375, 0.105),
        "TrajectoryGenerator plugin",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.555, 0.450, 0.175, 0.115),
        "StandardTrajectoryGenerator\nproject does not override it",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.755, 0.450, 0.175, 0.115),
        "LimitedAccelGenerator\ncloser to DWA windowing",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.665, 0.650), (0.642, 0.565), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.820, 0.650), (0.842, 0.565), fontsize=FIGURE_TEXT_SIZE)
    _box(
        axis,
        (0.625, 0.235, 0.235, 0.105),
        "trajectory critics select cmd_vel",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.642, 0.450), (0.700, 0.340), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.842, 0.450), (0.785, 0.340), fontsize=FIGURE_TEXT_SIZE)
    axis.text(
        0.742,
        0.175,
        "DWB uses DWA ideas, but is not identical to the 1997 algorithm.",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    _provenance_footer(figure, f"{FOX_BASIS}; {NAV2_BASIS}", kind="conceptual redraw")
    _save(figure, output)


def dwb_critic_scoring_figure(output: Path) -> None:
    """Explain DWB trajectory generation, critic aggregation, and command selection."""

    figure, axis = _blank_figure("DWB critic scoring: reject invalid, then minimize weighted cost")

    axis.add_patch(Rectangle((0.025, 0.205), 0.300, 0.605, fc=ZONE, ec="#C6CED3", lw=0.8))
    axis.text(
        0.045,
        0.775,
        "Candidate trajectories",
        ha="left",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        fontweight="semibold",
        color=EDGE,
    )
    axis.plot([0.065, 0.285], [0.450, 0.450], color=WORLD_EDGE, lw=0.8, ls="--")
    axis.scatter([0.225, 0.260], [0.545, 0.350], s=40, color=GUARD_EDGE, zorder=4)
    _robot_icon(axis, (0.075, 0.450))
    candidate_paths = (
        ([0.105, 0.150, 0.205, 0.275], [0.450, 0.510, 0.620, 0.690], WORLD_EDGE, "legal"),
        (
            [0.105, 0.155, 0.215, 0.285],
            [0.450, 0.430, 0.420, 0.450],
            RECOVERY_EDGE,
            "best legal",
        ),
        ([0.105, 0.155, 0.205, 0.265], [0.450, 0.385, 0.330, 0.350], GUARD_EDGE, "invalid"),
    )
    for x_values, y_values, color, label in candidate_paths:
        axis.plot(
            x_values,
            y_values,
            color=color,
            lw=2.0 if label == "best legal" else 1.2,
            ls="--" if label == "invalid" else "-",
            zorder=3,
        )
    axis.text(
        0.175,
        0.245,
        "generated by a pluggable\nTrajectoryGenerator",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )

    axis.add_patch(
        FancyBboxPatch(
            (0.370, 0.205),
            0.315,
            0.605,
            boxstyle="round,pad=0.010,rounding_size=0.018",
            fc=ZONE,
            ec=RECOVERY_EDGE,
            lw=0.9,
        )
    )
    axis.text(
        0.390,
        0.775,
        "Critic plugins",
        ha="left",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        fontweight="semibold",
        color=EDGE,
    )
    critics = (
        ("PathAlign", 0.405, 0.625),
        ("GoalAlign", 0.535, 0.625),
        ("PathDist", 0.405, 0.505),
        ("GoalDist", 0.535, 0.505),
        ("BaseObstacle", 0.405, 0.385),
        ("Oscillation", 0.535, 0.385),
    )
    for label, x_value, y_value in critics:
        _box(
            axis,
            (x_value, y_value, 0.115, 0.075),
            label,
            facecolor=WORLD if "Obstacle" not in label else GUARD,
            edgecolor=WORLD_EDGE if "Obstacle" not in label else GUARD_EDGE,
            fontsize=FIGURE_TEXT_SIZE,
        )
    axis.text(
        0.527,
        0.275,
        "$J(v,\\omega)=\\sum_i \\lambda_i c_i$",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )

    _diamond(axis, (0.785, 0.655), (0.120, 0.120), "valid?")
    _box(
        axis,
        (0.865, 0.620, 0.100, 0.080),
        "reject",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.700, 0.390, 0.180, 0.105),
        "minimum total score",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.720, 0.225, 0.140, 0.080),
        "cmd_vel",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.325, 0.505), (0.370, 0.505), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.685, 0.655), (0.725, 0.655), fontsize=FIGURE_TEXT_SIZE)
    _arrow(
        axis,
        (0.845, 0.655),
        (0.865, 0.660),
        label="no",
        label_position=(0.833, 0.710),
        color=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(
        axis,
        (0.785, 0.595),
        (0.810, 0.495),
        label="yes",
        label_position=(0.738, 0.535),
        color=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.790, 0.390), (0.790, 0.305), fontsize=FIGURE_TEXT_SIZE)
    _provenance_footer(figure, NAV2_BASIS)
    _save(figure, output)


def dwb_social_failure_figure(output: Path) -> None:
    """Illustrate why persistent social-navigation failures can need recovery."""

    figure, axes = plt.subplots(1, 3, figsize=(7.16, 3.20))
    _configure_matplotlib()
    figure.subplots_adjust(left=0.025, right=0.985, top=0.855, bottom=0.180, wspace=0.16)
    _figure_title(figure, "Local control can be correct locally yet fail to complete socially")

    titles = (
        "(a) Dynamic bottleneck",
        "(b) Persistent local symptom",
        "(c) Failure-triggered recovery",
    )
    for plot, title in zip(axes, titles, strict=True):
        plot.set_xlim(0.0, 1.0)
        plot.set_ylim(0.0, 1.0)
        plot.axis("off")
        plot.set_title(title, loc="left", fontsize=FIGURE_TEXT_SIZE, fontweight="semibold")
        plot.add_patch(Rectangle((0.02, 0.04), 0.96, 0.88, fc=ZONE, ec="#D5DBDF", lw=0.7))

    first, second, third = axes
    first.add_patch(Rectangle((0.02, 0.04), 0.96, 0.20, fc=NEUTRAL, ec=EDGE, lw=0.5))
    first.add_patch(Rectangle((0.02, 0.72), 0.96, 0.20, fc=NEUTRAL, ec=EDGE, lw=0.5))
    _robot_icon(first, (0.20, 0.48))
    for x_value, y_value in ((0.53, 0.40), (0.62, 0.57), (0.76, 0.43)):
        first.scatter([x_value], [y_value], s=45, color=GUARD_EDGE, zorder=4)
    first.add_patch(
        FancyArrowPatch(
            (0.28, 0.48),
            (0.88, 0.48),
            arrowstyle="-|>",
            mutation_scale=8,
            color=WORLD_EDGE,
            lw=1.0,
            linestyle="--",
        )
    )
    first.text(
        0.50,
        0.12,
        "moving people alter the next local cost",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=EDGE,
    )

    _robot_icon(second, (0.24, 0.50))
    second.plot([0.31, 0.52, 0.72], [0.50, 0.68, 0.60], color=WORLD_EDGE, lw=1.3)
    second.plot([0.31, 0.52, 0.72], [0.50, 0.32, 0.40], color=GUARD_EDGE, lw=1.3)
    second.add_patch(
        FancyArrowPatch(
            (0.58, 0.63),
            (0.58, 0.37),
            arrowstyle="<|-|>",
            mutation_scale=7,
            color=EDGE,
            lw=0.8,
        )
    )
    second.text(
        0.58,
        0.78,
        "best local score alternates",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    _box(
        second,
        (0.235, 0.105, 0.530, 0.115),
        "freeze · oscillation · deadlock",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )

    _diamond(third, (0.50, 0.735), (0.60, 0.175), "failure persists?")
    _box(
        third,
        (0.200, 0.455, 0.600, 0.135),
        "PGRR selects a bounded\nrecovery action",
        facecolor=RECOVERY,
        edgecolor=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        third,
        (0.200, 0.185, 0.600, 0.135),
        "DWB executes temporary goal\nthen rejoins original goal",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(third, (0.50, 0.648), (0.50, 0.590), fontsize=FIGURE_TEXT_SIZE)
    _arrow(third, (0.50, 0.455), (0.50, 0.320), fontsize=FIGURE_TEXT_SIZE)

    figure.text(
        0.50,
        0.125,
        "Illustrative mechanism only: it does not reconstruct a measured episode.",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=GUARD_EDGE,
    )
    _provenance_footer(
        figure,
        f"{NAV2_BASIS}; {FOX_BASIS}",
        kind="conceptual failure-mode schematic",
    )
    _save(figure, output)


def bc_distribution_shift_figure(output: Path) -> None:
    """Contrast expert-state behavior cloning with learner-induced deployment states."""

    figure, axes = plt.subplots(1, 2, figsize=(7.16, 3.20))
    _configure_matplotlib()
    figure.subplots_adjust(left=0.040, right=0.980, top=0.855, bottom=0.205, wspace=0.13)
    _figure_title(figure, "Behavior cloning: the state distribution changes after deployment")

    training, deployment = axes
    for plot in axes:
        plot.set_xlim(0.0, 1.0)
        plot.set_ylim(0.0, 1.0)
        plot.axis("off")
        plot.add_patch(Rectangle((0.02, 0.04), 0.96, 0.92, fc=ZONE, ec="#D5DBDF", lw=0.7))

    training.set_title(
        "(a) One-shot BC sees expert states",
        loc="left",
        fontsize=FIGURE_TEXT_SIZE,
        fontweight="semibold",
    )
    expert_points = ((0.15, 0.22), (0.30, 0.34), (0.45, 0.49), (0.62, 0.64), (0.82, 0.78))
    for x_value, y_value in expert_points:
        training.add_patch(
            Circle((x_value, y_value), 0.075, fc=WORLD, ec="none", alpha=0.90, zorder=1)
        )
    training.plot(
        [point[0] for point in expert_points],
        [point[1] for point in expert_points],
        color=WORLD_EDGE,
        lw=2.0,
        zorder=3,
    )
    training.scatter(
        [point[0] for point in expert_points],
        [point[1] for point in expert_points],
        s=18,
        color=WORLD_EDGE,
        zorder=4,
    )
    training.text(
        0.50,
        0.865,
        "$D_0=\\{(s,\\pi^*(s)):\\ s\\sim d_{\\pi^*}\\}$",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    _box(
        training,
        (0.235, 0.075, 0.530, 0.105),
        "supervised fit on $d_{\\pi^*}$",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )

    deployment.set_title(
        "(b) The learned policy induces new states",
        loc="left",
        fontsize=FIGURE_TEXT_SIZE,
        fontweight="semibold",
    )
    deployment.plot(
        [point[0] for point in expert_points],
        [point[1] for point in expert_points],
        color=WORLD_EDGE,
        lw=1.0,
        ls="--",
        zorder=2,
    )
    learner_points = (
        (0.15, 0.22),
        (0.30, 0.34),
        (0.43, 0.42),
        (0.56, 0.32),
        (0.70, 0.22),
        (0.85, 0.14),
    )
    for index, (x_value, y_value) in enumerate(learner_points):
        if index >= 2:
            deployment.add_patch(
                Circle((x_value, y_value), 0.075, fc=GUARD, ec="none", alpha=0.95, zorder=1)
            )
    deployment.plot(
        [point[0] for point in learner_points],
        [point[1] for point in learner_points],
        color=GUARD_EDGE,
        lw=2.0,
        zorder=3,
    )
    deployment.scatter(
        [point[0] for point in learner_points],
        [point[1] for point in learner_points],
        s=18,
        color=GUARD_EDGE,
        zorder=4,
    )
    deployment.annotate(
        "early error",
        xy=(0.43, 0.42),
        xytext=(0.63, 0.55),
        fontsize=FIGURE_TEXT_SIZE,
        color=GUARD_EDGE,
        ha="center",
        arrowprops={"arrowstyle": "-|>", "color": GUARD_EDGE, "lw": 0.8},
    )
    deployment.text(
        0.72,
        0.78,
        "$d_{\\hat\\pi} \\ne d_{\\pi^*}$",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    _box(
        deployment,
        (0.185, 0.075, 0.630, 0.105),
        "unseen states can compound later errors",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )

    figure.text(
        0.50,
        0.145,
        "DAgger responds by labeling states visited by the learner, not by adding a reward.",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=RECOVERY_EDGE,
        fontweight="semibold",
    )
    _provenance_footer(figure, ROSS_BASIS, kind="distribution-shift redraw")
    _save(figure, output)


def dagger_loop_figure(output: Path) -> None:
    """Render the canonical Dataset Aggregation feedback loop."""

    figure, axis = _blank_figure("DAgger: collect where the learner goes, label with the expert")

    positions = (
        (0.405, 0.700, 0.190, 0.105, "Current learner\n$\\hat\\pi_i$"),
        (0.700, 0.555, 0.215, 0.105, "Roll out on\ntraining scenarios"),
        (0.650, 0.255, 0.265, 0.105, "Expert labels visited states\n$D_i=\\{(s,\\pi^*(s))\\}$"),
        (0.250, 0.205, 0.210, 0.105, "Aggregate\n$D \\leftarrow D \\cup D_i$"),
        (0.070, 0.495, 0.220, 0.105, "Supervised retrain\non all $D$"),
    )
    for index, (x_value, y_value, width, height, label) in enumerate(positions):
        _box(
            axis,
            (x_value, y_value, width, height),
            label,
            facecolor=RECOVERY if index in {0, 4} else WORLD,
            edgecolor=RECOVERY_EDGE if index in {0, 4} else WORLD_EDGE,
            fontsize=FIGURE_TEXT_SIZE,
        )

    _arrow(axis, (0.595, 0.753), (0.700, 0.608), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.807, 0.555), (0.790, 0.360), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.650, 0.308), (0.460, 0.258), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.250, 0.258), (0.180, 0.495), fontsize=FIGURE_TEXT_SIZE)
    _arrow(
        axis,
        (0.290, 0.548),
        (0.405, 0.753),
        label="next policy",
        label_position=(0.345, 0.675),
        color=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )

    _box(
        axis,
        (0.385, 0.430, 0.230, 0.120),
        "Validation gate\nreturn best $\\hat\\pi_i$",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(
        axis,
        (0.500, 0.700),
        (0.500, 0.550),
        dashed=True,
        color=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    axis.text(
        0.500,
        0.370,
        "Optional canonical rollout mixture:\n$\\pi_i=\\beta_i\\pi^*+(1-\\beta_i)\\hat\\pi_i$",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=EDGE,
    )
    _box(
        axis,
        (0.055, 0.725, 0.235, 0.085),
        "expert action labels",
        facecolor=WORLD,
        edgecolor=WORLD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _box(
        axis,
        (0.700, 0.735, 0.240, 0.085),
        "no reward · no critic · no PPO",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _provenance_footer(figure, ROSS_BASIS, kind="Algorithm 3.1 redraw")
    _save(figure, output)


def pgrr_dagger_rounds_figure(output: Path) -> None:
    """Document the two completed DAgger rounds and validation-only selection."""

    figure, axis = _blank_figure("PGRR training provenance: two rounds run, validation chooses")

    stages = (
        (0.025, 0.575, 0.135, 0.135, "Uniform BC\nexpert data", WORLD, WORLD_EDGE),
        (
            0.200,
            0.575,
            0.145,
            0.135,
            "DAgger round 1\nvisit + relabel",
            RECOVERY,
            RECOVERY_EDGE,
        ),
        (
            0.385,
            0.575,
            0.145,
            0.135,
            "DAgger round 2\nvisit + relabel",
            RECOVERY,
            RECOVERY_EDGE,
        ),
        (
            0.700,
            0.575,
            0.170,
            0.135,
            "accepted aggregate\n+ train-only coverage",
            WORLD,
            WORLD_EDGE,
        ),
        (0.900, 0.575, 0.075, 0.135, "freeze\nbest.onnx", RECOVERY, RECOVERY_EDGE),
    )
    for x_value, y_value, width, height, label, facecolor, edgecolor in stages:
        _box(
            axis,
            (x_value, y_value, width, height),
            label,
            facecolor=facecolor,
            edgecolor=edgecolor,
            fontsize=FIGURE_TEXT_SIZE,
        )
    _diamond(axis, (0.615, 0.642), (0.130, 0.160), "validation\nselection")
    _arrow(axis, (0.160, 0.642), (0.200, 0.642), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.345, 0.642), (0.385, 0.642), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.530, 0.642), (0.550, 0.642), fontsize=FIGURE_TEXT_SIZE)
    _arrow(
        axis,
        (0.680, 0.642),
        (0.700, 0.642),
        label="selected path",
        label_position=(0.690, 0.750),
        color=RECOVERY_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(axis, (0.870, 0.642), (0.900, 0.642), fontsize=FIGURE_TEXT_SIZE)

    _box(
        axis,
        (0.505, 0.300, 0.220, 0.105),
        "round-2 candidate retained\nbut rejected on validation",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    _arrow(
        axis,
        (0.615, 0.562),
        (0.615, 0.405),
        label="not selected",
        label_position=(0.545, 0.480),
        color=GUARD_EDGE,
        dashed=True,
        fontsize=FIGURE_TEXT_SIZE,
    )

    axis.add_patch(
        FancyBboxPatch(
            (0.035, 0.185),
            0.400,
            0.190,
            boxstyle="round,pad=0.010,rounding_size=0.018",
            fc=ZONE,
            ec="#AAB5BC",
            lw=0.8,
            linestyle="--",
        )
    )
    axis.text(
        0.055,
        0.335,
        "Split discipline",
        ha="left",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        fontweight="semibold",
        color=EDGE,
    )
    axis.text(
        0.235,
        0.255,
        "rollouts: train only   ·   model choice: validation only\n"
        "locked test: never used for labels, tuning, or selection",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
    )
    _box(
        axis,
        (0.760, 0.280, 0.190, 0.095),
        "PPO is not part\nof this release",
        facecolor=GUARD,
        edgecolor=GUARD_EDGE,
        fontsize=FIGURE_TEXT_SIZE,
    )
    axis.text(
        0.820,
        0.480,
        "coverage retraining\nis not a third DAgger round",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=EDGE,
    )
    _provenance_footer(figure, ROSS_BASIS, kind="project-specific DAgger adaptation")
    _save(figure, output)


def evaluation_evidence_chain_figure(output: Path) -> None:
    """Show the fail-closed path from frozen protocol to publication artifacts."""

    figure, axis = _blank_figure("Evaluation evidence chain: frozen inputs to auditable claims")

    top_stages = (
        (
            0.025,
            "1  Freeze inputs",
            "scenario/map splits\nconfigs + checkpoint hashes",
            WORLD,
            WORLD_EDGE,
        ),
        (
            0.350,
            "2  Execute conditions",
            "same condition keys\nacross all methods",
            RECOVERY,
            RECOVERY_EDGE,
        ),
        (
            0.675,
            "3  Preserve outcomes",
            "goal · collision · timeout\nplanner/simulator/reset failure",
            GUARD,
            GUARD_EDGE,
        ),
    )
    for x_value, heading, label, facecolor, edgecolor in top_stages:
        axis.text(
            x_value,
            0.795,
            heading,
            ha="left",
            va="center",
            fontsize=FIGURE_TEXT_SIZE,
            fontweight="semibold",
            color=edgecolor,
        )
        _box(
            axis,
            (x_value, 0.590, 0.285, 0.145),
            label,
            facecolor=facecolor,
            edgecolor=edgecolor,
            fontsize=FIGURE_TEXT_SIZE,
        )
    _arrow(axis, (0.310, 0.662), (0.350, 0.662), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.635, 0.662), (0.675, 0.662), fontsize=FIGURE_TEXT_SIZE)

    bottom_stages = (
        (0.675, "4  Checked-in ledger", "Parquet · CSV · JSON", WORLD, WORLD_EDGE),
        (
            0.350,
            "5  Preregistered analysis",
            "paired tests · intervals\nglobal Holm correction",
            RECOVERY,
            RECOVERY_EDGE,
        ),
        (
            0.025,
            "6  Generated artifacts",
            "figures · tables\npaper · report · deck",
            WORLD,
            WORLD_EDGE,
        ),
    )
    for x_value, heading, label, facecolor, edgecolor in bottom_stages:
        axis.text(
            x_value,
            0.430,
            heading,
            ha="left",
            va="center",
            fontsize=FIGURE_TEXT_SIZE,
            fontweight="semibold",
            color=edgecolor,
        )
        _box(
            axis,
            (x_value, 0.225, 0.285, 0.145),
            label,
            facecolor=facecolor,
            edgecolor=edgecolor,
            fontsize=FIGURE_TEXT_SIZE,
        )
    _arrow(axis, (0.818, 0.590), (0.818, 0.370), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.675, 0.298), (0.635, 0.298), fontsize=FIGURE_TEXT_SIZE)
    _arrow(axis, (0.350, 0.298), (0.310, 0.298), fontsize=FIGURE_TEXT_SIZE)

    axis.text(
        0.500,
        0.125,
        "Validation selects; locked test estimates. "
        "Infrastructure retries never replace algorithm outcomes.",
        ha="center",
        va="center",
        fontsize=FIGURE_TEXT_SIZE,
        color=INK,
        fontweight="semibold",
    )
    _provenance_footer(
        figure,
        f"{NAV2_BASIS}; {ROSS_BASIS}",
        kind="PGRR evidence-flow schematic",
    )
    _save(figure, output)


def generate_method_figures(
    output_dir: Path,
    scenario_config: Path = DEFAULT_SCENARIO_CONFIG,
) -> list[Path]:
    """Generate every paper figure that does not depend on final results."""

    renderers = (
        ("system_architecture", system_architecture_figure),
        ("recovery_state_machine", recovery_state_machine_figure),
        ("action_space_expert", action_space_expert_figure),
        ("dwb_nav2_role", dwb_nav2_role_figure),
        ("dwb_dynamic_window", dwb_dynamic_window_figure),
        ("dwb_critic_scoring", dwb_critic_scoring_figure),
        ("dwb_social_failure", dwb_social_failure_figure),
        ("bc_distribution_shift", bc_distribution_shift_figure),
        ("dagger_loop", dagger_loop_figure),
        ("pgrr_dagger_rounds", pgrr_dagger_rounds_figure),
        ("evaluation_evidence_chain", evaluation_evidence_chain_figure),
        (
            "scenario_overview",
            lambda path: scenario_overview_figure(path, scenario_config),
        ),
    )
    outputs: list[Path] = []
    for stem, renderer in renderers:
        for suffix in (".pdf", ".svg"):
            output = output_dir / f"{stem}{suffix}"
            renderer(output)
            outputs.append(output)
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "paper/figures")
    parser.add_argument(
        "--scenario-config",
        type=Path,
        default=DEFAULT_SCENARIO_CONFIG,
        help="Catalog used only for family/layout and density metadata.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_method_figures(args.output_dir, args.scenario_config)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
