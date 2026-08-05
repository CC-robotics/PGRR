#!/usr/bin/env python3
"""Generate booktabs LaTeX tables for the locked moderate benchmark."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from moderate_artifacts import (
        ALGORITHM_OUTCOMES,
        DENSITY_ORDER,
        EXCLUDED_OUTCOMES,
        METHODS,
        ROOT,
        ModerateArtifactError,
        display_method,
        latex_escape,
        load_moderate_artifacts,
        method_order,
        portable_path,
        wilson_interval,
    )
except ModuleNotFoundError:  # Imported as a namespace module by pytest.
    from scripts.paper.moderate_artifacts import (
        ALGORITHM_OUTCOMES,
        DENSITY_ORDER,
        EXCLUDED_OUTCOMES,
        METHODS,
        ROOT,
        ModerateArtifactError,
        display_method,
        latex_escape,
        load_moderate_artifacts,
        method_order,
        portable_path,
        wilson_interval,
    )


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _provenance(
    results_path: Path,
    summary_path: Path,
    statistics_path: Path,
    results: pd.DataFrame,
) -> str:
    commit = (
        str(results["project_commit"].iloc[0]) if "project_commit" in results else "not-recorded"
    )
    return (
        "% Generated exclusively from "
        f"{portable_path(results_path)}, {portable_path(summary_path)}, and "
        f"{portable_path(statistics_path)}; project_commit={commit}\n"
    )


def _valid(results: pd.DataFrame) -> pd.DataFrame:
    return results.loc[~results["outcome"].isin(EXCLUDED_OUTCOMES)].copy()


def _method_cell(method: str) -> str:
    label = latex_escape(display_method(method))
    return rf"\textbf{{{label}}}" if method == "pgrr" else label


def _percentage(count: int, total: int, *, digits: int = 1) -> str:
    return "--" if total <= 0 else f"{100.0 * count / total:.{digits}f}"


def _mean_sd(values: pd.Series, *, digits: int) -> str:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    finite = numeric[np.isfinite(numeric)]
    if finite.size == 0:
        return "--"
    mean = float(np.mean(finite))
    if finite.size == 1:
        return f"{mean:.{digits}f}"
    deviation = float(np.std(finite, ddof=1))
    return rf"{mean:.{digits}f} $\pm$ {deviation:.{digits}f}"


def _rate_ci(count: int, total: int) -> str:
    estimate, lower, upper = wilson_interval(count, total)
    if not all(math.isfinite(value) for value in (estimate, lower, upper)):
        return "--"
    return f"{100.0 * estimate:.1f} [{100.0 * lower:.1f}, {100.0 * upper:.1f}]"


def _p_value(value: float) -> str:
    return "$<0.001$" if value < 0.001 else f"{value:.3f}"


def _macro_p_value(value: float) -> str:
    return r"\ensuremath{<0.001}" if value < 0.001 else rf"\ensuremath{{={value:.3f}}}"


def main_results_table(
    results: pd.DataFrame,
    *,
    provenance: str,
    output: Path,
) -> None:
    """Render the complete five-method primary outcome table."""

    valid = _valid(results)
    rows: list[str] = []
    exclusions: list[str] = []
    for method in method_order(valid["source_policy"].unique()):
        all_rows = results.loc[results["source_policy"] == method]
        selected = valid.loc[valid["source_policy"] == method]
        successful = selected.loc[selected["outcome"] == "GOAL_REACHED"]
        total = len(selected)
        counts = {
            outcome: int((selected["outcome"] == outcome).sum()) for outcome in ALGORITHM_OUTCOMES
        }
        spl_entry = _mean_sd(selected["spl"], digits=3) if "spl" in selected else "--"
        time_entry = (
            _mean_sd(successful["navigation_time_s"], digits=1)
            if "navigation_time_s" in successful
            else "--"
        )
        excluded = len(all_rows) - total
        exclusions.append(f"{display_method(method)}: {excluded}")
        rows.append(
            f"{_method_cell(method)} & {total} & "
            f"{_rate_ci(counts['GOAL_REACHED'], total)} & "
            f"{_percentage(counts['COLLISION'], total)} & "
            f"{_percentage(counts['TIMEOUT'], total)} & "
            f"{_percentage(counts['PLANNER_FAILURE'], total)} & "
            f"{spl_entry} & {time_entry} & "
            f"{_mean_sd(selected['min_human_distance_m'], digits=2)} \\\\"
        )
    payload = provenance + (
        """\\begin{table*}[t]
\\caption{Closed-loop results on the complete moderate paired manifest.}
\\label{tab:moderate-main-results}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{3.3pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}lrrrrrrrr@{}}
\\toprule
Method & $n$ & Success [95\\% CI] $\\uparrow$ (\\%) & Collision $\\downarrow$ (\\%)
& Timeout $\\downarrow$ (\\%) & Planner fail. $\\downarrow$ (\\%) & SPL $\\uparrow$
& Goal time $\\downarrow$ (s) & $d_{\\min}\\uparrow$ (m) \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} All methods use identical
scenario--density--seed conditions. Success intervals are two-sided 95\\% Wilson intervals.
Collision, timeout, and planner failure are reported as distinct terminal outcomes and are not
merged or omitted. SPL and $d_{\\min}$ use all valid episodes; goal time is conditional on
goal reaching. Continuous entries are mean $\\pm$ sample SD. Simulator/reset rows are excluded
from algorithm rates but retained in the artifacts (counts: """
        + latex_escape("; ".join(exclusions))
        + "). Bold identifies the proposed method.}"
        + """
\\end{table*}
"""
    )
    _write(output, payload)


def density_results_table(
    results: pd.DataFrame,
    *,
    provenance: str,
    output: Path,
) -> None:
    """Render terminal outcomes for every method and crowd density."""

    valid = _valid(results)
    densities = [density for density in DENSITY_ORDER if density in set(valid["density"])]
    rows: list[str] = []
    for density_index, density in enumerate(densities):
        if density_index:
            rows.append(r"\addlinespace[2pt]")
        for method in method_order(valid["source_policy"].unique()):
            selected = valid.loc[(valid["density"] == density) & (valid["source_policy"] == method)]
            total = len(selected)
            if total == 0:
                continue
            rows.append(
                f"{latex_escape(density.title())} & {_method_cell(method)} & {total} & "
                f"{_percentage(int((selected['outcome'] == 'GOAL_REACHED').sum()), total)} & "
                f"{_percentage(int((selected['outcome'] == 'COLLISION').sum()), total)} & "
                f"{_percentage(int((selected['outcome'] == 'TIMEOUT').sum()), total)} & "
                f"{_percentage(int((selected['outcome'] == 'PLANNER_FAILURE').sum()), total)} \\\\"
            )
    payload = provenance + (
        """\\begin{table*}[t]
\\caption{Terminal outcomes by crowd density on the moderate paired manifest.}
\\label{tab:moderate-density-results}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{4.2pt}
\\renewcommand{\\arraystretch}{1.06}
\\begin{tabular}{@{}llrrrrr@{}}
\\toprule
Density & Method & $n$ & Success $\\uparrow$ (\\%) & Collision $\\downarrow$ (\\%)
& Timeout $\\downarrow$ (\\%) & Planner fail. $\\downarrow$ (\\%) \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} Each percentage uses the valid
episode count shown in $n$. The four terminal-outcome columns sum to 100\\% within rounding.
Bold identifies the proposed method.}
\\end{table*}
"""
    )
    _write(output, payload)


def recovery_metrics_table(
    results: pd.DataFrame,
    *,
    provenance: str,
    output: Path,
) -> None:
    """Render recovery behavior for all methods without imputing undefined rates."""

    required = {
        "recovery_trigger_count",
        "recovery_success_rate",
        "recovery_duration_s",
        "intervention_ratio",
        "emergency_stop_count",
    }
    missing = sorted(required - set(results.columns))
    if missing:
        raise ModerateArtifactError("recovery table requires columns: " + ", ".join(missing))
    valid = _valid(results)
    rows: list[str] = []
    for method in method_order(valid["source_policy"].unique()):
        selected = valid.loc[valid["source_policy"] == method]
        rows.append(
            f"{_method_cell(method)} & {len(selected)} & "
            f"{_mean_sd(selected['recovery_trigger_count'], digits=2)} & "
            f"{_mean_sd(100.0 * selected['recovery_success_rate'], digits=1)} & "
            f"{_mean_sd(selected['recovery_duration_s'], digits=2)} & "
            f"{_mean_sd(100.0 * selected['intervention_ratio'], digits=1)} & "
            f"{_mean_sd(selected['emergency_stop_count'], digits=2)} \\\\"
        )
    payload = provenance + (
        """\\begin{table*}[t]
\\caption{Recovery behavior on valid moderate-benchmark episodes.}
\\label{tab:moderate-recovery-results}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{4.0pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}lrrrrrr@{}}
\\toprule
Method & $n$ & Triggers (ep.$^{-1}$) & Recovery success (\\%)
& Recovery time (s/ep.) & Intervention (\\%) & E-stops (ep.$^{-1}$) \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} Entries are episode-level mean
$\\pm$ sample SD. Undefined recovery-success values for episodes or methods with no trigger are
shown as dashes; they are not replaced by zeros. Bold identifies the proposed method.}
\\end{table*}
"""
    )
    _write(output, payload)


def _statistic_row(
    comparator: str,
    metric: str,
    analysis: Mapping[str, Any],
    *,
    binary: bool,
) -> str:
    interval = analysis["difference_treatment_minus_reference"]
    assert isinstance(interval, Mapping)
    scale = 100.0 if binary else 1.0
    digits = 1 if binary else 3
    unit = " pp" if binary else ""
    estimate = scale * float(interval["estimate"])
    lower = scale * float(interval["lower"])
    upper = scale * float(interval["upper"])
    test_key = "mcnemar_exact" if binary else "wilcoxon"
    effect_key = "matched_odds_ratio_haldane" if binary else None
    test = analysis[test_key]
    assert isinstance(test, Mapping)
    if binary:
        effect = rf"$\mathrm{{OR}}_H={float(test[effect_key]):.3g}$"
        test_name = "McNemar"
    else:
        effect_payload = analysis["effect_size"]
        assert isinstance(effect_payload, Mapping)
        effect = rf"$r_{{\mathrm{{rb}}}}={float(effect_payload['rank_biserial_correlation']):+.3f}$"
        test_name = "Wilcoxon"
    return (
        f"{latex_escape(display_method(comparator))} & {latex_escape(metric)} & {test_name} & "
        rf"${estimate:+.{digits}f}\;[{lower:+.{digits}f},\,{upper:+.{digits}f}]"
        f"{latex_escape(unit)}$ & {_p_value(float(test['pvalue_raw']))} & "
        f"{_p_value(float(test['pvalue_holm']))} & {effect} & "
        f"{int(analysis['pair_count'])} \\\\"
    )


def pairwise_statistics_table(
    statistics: Mapping[str, Any],
    *,
    provenance: str,
    output: Path,
) -> None:
    """Render selected endpoints for PGRR against every registered baseline."""

    comparisons = statistics["comparisons"]
    assert isinstance(comparisons, Mapping)
    rows: list[str] = []
    for comparator_index, comparator in enumerate(statistics["comparators"]):
        if comparator_index:
            rows.append(r"\addlinespace[2pt]")
        comparison = comparisons[comparator]
        assert isinstance(comparison, Mapping)
        binary = comparison["binary_outcomes"]
        continuous = comparison["continuous_metrics"]
        assert isinstance(binary, Mapping) and isinstance(continuous, Mapping)
        for key, label in (
            ("goal_reached", "Goal reached"),
            ("collision", "Collision"),
            ("timeout", "Timeout"),
        ):
            analysis = binary[key]
            assert isinstance(analysis, Mapping)
            rows.append(_statistic_row(str(comparator), label, analysis, binary=True))
        for key, label in (("spl", "SPL"), ("min_human_distance_m", "Min. human distance")):
            analysis = continuous.get(key)
            if not isinstance(analysis, Mapping) or analysis.get("status") != "ok":
                continue
            rows.append(_statistic_row(str(comparator), label, analysis, binary=False))
    hypothesis_count = int(
        statistics["global_multiple_comparison"]["hypothesis_count"]  # type: ignore[index]
    )
    payload = provenance + (
        """\\begin{table*}[t]
\\caption{Paired PGRR-minus-baseline comparisons on the complete moderate manifest.}
\\label{tab:moderate-pairwise-results}
\\centering
\\scriptsize
\\setlength{\\tabcolsep}{2.8pt}
\\renewcommand{\\arraystretch}{1.05}
\\begin{tabular}{@{}lllrrrrr@{}}
\\toprule
Baseline & Endpoint & Test & $\\Delta$ [95\\% CI] & $p_{\\mathrm{raw}}$
& $p_{\\mathrm{Holm}}$ & Effect & $n_{\\mathrm{pairs}}$ \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\scriptsize \\emph{Note.} Differences are PGRR minus the
named baseline. Binary-rate differences use percentage points (pp), episode-pair bootstrap
95\\% CIs, exact McNemar tests, and Haldane-corrected matched odds ratios
$\\mathrm{OR}_H$. Continuous endpoints use paired bootstrap CIs, Wilcoxon signed-rank tests,
and rank-biserial correlation $r_{\\mathrm{rb}}$. The reported Holm value belongs to one
global family of """
        + str(hypothesis_count)
        + " preregistered binary and continuous tests across all four baselines.}"
        + """
\\end{table*}
"""
    )
    _write(output, payload)


def result_macros(
    results: pd.DataFrame,
    statistics: Mapping[str, Any],
    *,
    provenance: str,
    output: Path,
) -> None:
    """Write compact macros for numerical claims in the moderate-results prose."""

    valid = _valid(results)
    lines = ["% Automatically generated; do not hand-edit numerical claims.", provenance.rstrip()]
    condition_count = len(results.loc[results["source_policy"] == "pgrr"])
    lines.append(rf"\providecommand{{\ModeratePairCount}}{{{condition_count}}}")
    lines.append(rf"\providecommand{{\ModerateMethodCount}}{{{len(METHODS)}}}")
    lines.append(rf"\providecommand{{\ModerateEpisodeCount}}{{{len(results)}}}")
    lines.append(rf"\providecommand{{\ModerateValidEpisodeCount}}{{{len(valid)}}}")
    lines.append(
        rf"\providecommand{{\ModerateExcludedEpisodeCount}}{{{len(results) - len(valid)}}}"
    )
    for method, prefix in (("base", "ModerateBase"), ("pgrr", "ModeratePGRR")):
        selected = valid.loc[valid["source_policy"] == method]
        total = len(selected)
        lines.append(rf"\providecommand{{\{prefix}ValidEpisodeCount}}{{{total}}}")
        for suffix, outcome in (
            ("SuccessRate", "GOAL_REACHED"),
            ("CollisionRate", "COLLISION"),
            ("TimeoutRate", "TIMEOUT"),
        ):
            count = int((selected["outcome"] == outcome).sum())
            rate = 100.0 * count / total if total else math.nan
            value = "--" if not math.isfinite(rate) else f"{rate:.1f}\\%"
            lines.append(rf"\providecommand{{\{prefix}{suffix}}}{{{value}}}")
    base_comparison = statistics["comparisons"]["base"]  # type: ignore[index]
    lines.append(
        rf"\providecommand{{\ModerateBasePGRRValidPairCount}}"
        rf"{{{int(base_comparison['valid_pair_count'])}}}"
    )
    for endpoint, suffix in (
        ("goal_reached", "SuccessDifference"),
        ("collision", "CollisionDifference"),
        ("timeout", "TimeoutDifference"),
    ):
        analysis = base_comparison["binary_outcomes"][endpoint]
        interval = analysis["difference_treatment_minus_reference"]
        estimate = 100.0 * float(interval["estimate"])
        lower = 100.0 * float(interval["lower"])
        upper = 100.0 * float(interval["upper"])
        lines.append(
            rf"\providecommand{{\ModeratePGRR{suffix}}}"
            rf"{{\ensuremath{{{estimate:+.1f}\,[{lower:+.1f},\,{upper:+.1f}]\,\mathrm{{pp}}}}}}"
        )
        test = analysis["mcnemar_exact"]
        lines.append(
            rf"\providecommand{{\ModeratePGRR{suffix}HolmP}}"
            rf"{{{_macro_p_value(float(test['pvalue_holm']))}}}"
        )
    _write(output, "\n".join(lines) + "\n")


def generate_moderate_tables(
    results_path: Path,
    summary_path: Path,
    statistics_path: Path,
    output_dir: Path,
    *,
    expected_condition_count: int,
) -> list[Path]:
    """Validate the three inputs and generate all moderate LaTeX tables."""

    results, _, statistics = load_moderate_artifacts(
        results_path,
        summary_path,
        statistics_path,
        expected_condition_count=expected_condition_count,
    )
    provenance = _provenance(results_path, summary_path, statistics_path, results)
    outputs = [
        output_dir / "moderate_main_results.tex",
        output_dir / "moderate_density_results.tex",
        output_dir / "moderate_recovery_metrics.tex",
        output_dir / "moderate_pairwise_statistics.tex",
        output_dir / "moderate_result_macros.tex",
    ]
    main_results_table(results, provenance=provenance, output=outputs[0])
    density_results_table(results, provenance=provenance, output=outputs[1])
    recovery_metrics_table(results, provenance=provenance, output=outputs[2])
    pairwise_statistics_table(statistics, provenance=provenance, output=outputs[3])
    result_macros(results, statistics, provenance=provenance, output=outputs[4])
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--statistics", type=Path, required=True)
    parser.add_argument(
        "--expected-condition-count",
        type=int,
        required=True,
        help=(
            "Exact preregistered test conditions per method; publication generation "
            "fails otherwise."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "paper/generated")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_moderate_tables(
            args.results,
            args.summary,
            args.statistics,
            args.output_dir,
            expected_condition_count=args.expected_condition_count,
        )
    except (ModerateArtifactError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
