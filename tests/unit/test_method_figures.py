from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "paper" / "make_method_figures.py"
SPEC = importlib.util.spec_from_file_location("pgrr_method_figures", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _minimal_catalog() -> dict[str, object]:
    layouts = {
        "head_on_corridor": "horizontal_corridor",
        "doorway_bottleneck": "doorway",
        "crossing_flow": "crossing",
        "blind_corner": "blind_corner",
        "group_blocking": "group_blocking",
        "overtaking": "overtaking",
        "opposite_streams": "opposite_streams",
        "temporary_blockage": "temporary_blockage",
    }
    return {
        "schema_version": 1,
        "densities": {"low": 1, "medium": 2, "high": 4},
        "families": [
            {"id": family, "layout": layouts[family]} for family in MODULE.EXPECTED_FAMILIES
        ],
        # A deliberately nonexistent test-manifest path proves the schematic
        # generator does not open a split or consume held-out episode data.
        "splits": {"test": {"manifest": "/definitely/not/read/test.yaml"}},
    }


def _write_catalog(path: Path, payload: dict[str, object] | None = None) -> Path:
    path.write_text(
        yaml.safe_dump(_minimal_catalog() if payload is None else payload, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_method_figure_inventory_and_palette_are_fixed() -> None:
    assert len(MODULE._candidate_actions()) == 21
    assert MODULE.SPECIAL_ACTIONS == (
        (21, "WAIT"),
        (22, "BACKUP"),
        (23, "REPLAN"),
        (24, "CONTINUE"),
    )
    assert len(MODULE.FUNCTIONAL_COLORS) == 3
    assert len(set(MODULE.FUNCTIONAL_COLORS)) == 3
    assert MODULE.EXPECTED_FAMILIES == (
        "head_on_corridor",
        "doorway_bottleneck",
        "crossing_flow",
        "blind_corner",
        "group_blocking",
        "overtaking",
        "opposite_streams",
        "temporary_blockage",
    )


def test_generate_method_figures_writes_pdf_and_svg_without_raster_images(
    tmp_path: Path,
) -> None:
    catalog = _write_catalog(tmp_path / "catalog.yaml")
    output_dir = tmp_path / "figures"
    outputs = MODULE.generate_method_figures(output_dir, catalog)

    expected_stems = {
        "system_architecture",
        "recovery_state_machine",
        "action_space_expert",
        "scenario_overview",
    }
    assert {path.stem for path in outputs} == expected_stems
    assert {path.suffix for path in outputs} == {".pdf", ".svg"}
    assert len(outputs) == 2 * len(expected_stems)

    for output in outputs:
        assert output.is_file()
        assert output.stat().st_size > 8_000
        payload = output.read_bytes()
        if output.suffix == ".pdf":
            assert payload.startswith(b"%PDF")
            assert b"/Subtype /Image" not in payload
            assert b"/Subtype /Type3" not in payload
        else:
            text = payload.decode("utf-8")
            assert text.startswith("<?xml")
            assert all(line == line.rstrip() for line in text.splitlines())
            assert "<image" not in text
            assert "#ffffff" in text.lower()
            assert "/definitely/not/read" not in text


def test_scenario_inventory_reads_only_family_and_density_metadata(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path / "catalog.yaml")
    families, densities = MODULE._load_scenario_inventory(catalog)
    assert tuple(family for family, _ in families) == MODULE.EXPECTED_FAMILIES
    assert densities == {"low": 1, "medium": 2, "high": 4}

    output = tmp_path / "scenario_overview.svg"
    MODULE.scenario_overview_figure(output, catalog)
    assert output.is_file()
    assert "/definitely/not/read" not in output.read_text(encoding="utf-8")


def test_scenario_inventory_rejects_semantic_drift(tmp_path: Path) -> None:
    payload = _minimal_catalog()
    densities = payload["densities"]
    assert isinstance(densities, dict)
    densities["high"] = 3
    catalog = _write_catalog(tmp_path / "bad_catalog.yaml", payload)

    try:
        MODULE._load_scenario_inventory(catalog)
    except ValueError as error:
        assert "unexpected density inventory" in str(error)
    else:  # pragma: no cover - explicit assertion gives a better failure message.
        raise AssertionError("density drift was accepted")


def test_method_generator_has_no_result_or_split_manifest_dependency() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "results.parquet",
        "summary.csv",
        "statistics.json",
        "scenarios/splits/",
        "moderate_v5_test.yaml",
        "pandas",
    )
    for token in forbidden:
        assert token not in source
