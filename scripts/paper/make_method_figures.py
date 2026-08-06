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
DEFAULT_SCENARIO_CONFIG = ROOT / "configs/experiments/scenario_catalog_moderate_v5.yaml"

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


def generate_method_figures(
    output_dir: Path,
    scenario_config: Path = DEFAULT_SCENARIO_CONFIG,
) -> list[Path]:
    """Generate every paper figure that does not depend on final results."""

    renderers = (
        ("system_architecture", system_architecture_figure),
        ("recovery_state_machine", recovery_state_machine_figure),
        ("action_space_expert", action_space_expert_figure),
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
