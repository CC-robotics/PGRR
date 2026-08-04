#!/usr/bin/env python3
"""Generate LaTeX tables exclusively from locked final result artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from make_figures import (
        EXCLUDED_OUTCOMES,
        ROOT,
        ArtifactError,
        _method_order,
        display_method,
        load_final_artifacts,
    )
except ModuleNotFoundError:  # Imported as a namespace module by pytest.
    from scripts.paper.make_figures import (
        EXCLUDED_OUTCOMES,
        ROOT,
        ArtifactError,
        _method_order,
        display_method,
        load_final_artifacts,
    )


def _latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _valid_rows(results: pd.DataFrame) -> pd.DataFrame:
    return results.loc[~results["outcome"].isin(EXCLUDED_OUTCOMES)].copy()


def _mean_std(values: pd.Series, *, digits: int) -> str:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    numeric = numeric[np.isfinite(numeric)]
    if numeric.size == 0:
        return "--"
    mean = float(np.mean(numeric))
    if numeric.size == 1:
        return f"{mean:.{digits}f}"
    standard_deviation = float(np.std(numeric, ddof=1))
    return f"{mean:.{digits}f} $\\pm$ {standard_deviation:.{digits}f}"


def _percentage(numerator: int, denominator: int) -> str:
    return "--" if denominator == 0 else f"{100.0 * numerator / denominator:.1f}"


def _p_value(value: float) -> str:
    return "$<0.001$" if value < 0.001 else f"{value:.3f}"


STATISTIC_METRIC_LABELS = {
    "goal_reached": "Goal reached",
    "collision": "Collision",
    "timeout": "Timeout",
    "successful_episode_duration_s": "Success time",
    "successful_path_length_m": "Success path",
    "spl": "SPL",
    "min_human_distance_m": "Min. human distance",
    "personal_space_violation_ratio": "Personal-space violation",
    "discomfort_time_s": "Discomfort time",
    "emergency_stop_count": "Emergency stops",
    "recovery_trigger_count": "Recovery triggers",
    "intervention_ratio": "Intervention ratio",
    "mean_abs_angular_jerk_rad_s3": "Angular jerk",
}


# Scale, decimals, and display unit for PGRR-minus-DWB paired differences.  Rates
# are rendered as percentage-point differences rather than unitless fractions.
STATISTIC_FORMATS: dict[str, tuple[float, int, str]] = {
    "goal_reached": (100.0, 1, r"\,\mathrm{pp}"),
    "collision": (100.0, 1, r"\,\mathrm{pp}"),
    "timeout": (100.0, 1, r"\,\mathrm{pp}"),
    "successful_episode_duration_s": (1.0, 1, r"\,\mathrm{s}"),
    "successful_path_length_m": (1.0, 2, r"\,\mathrm{m}"),
    "spl": (1.0, 3, ""),
    "min_human_distance_m": (1.0, 3, r"\,\mathrm{m}"),
    "personal_space_violation_ratio": (100.0, 1, r"\,\mathrm{pp}"),
    "discomfort_time_s": (1.0, 2, r"\,\mathrm{s}"),
    "emergency_stop_count": (1.0, 2, r"\,\mathrm{ep.}^{-1}"),
    "recovery_trigger_count": (1.0, 2, r"\,\mathrm{ep.}^{-1}"),
    "intervention_ratio": (100.0, 1, r"\,\mathrm{pp}"),
    "mean_abs_angular_jerk_rad_s3": (1.0, 3, r"\,\mathrm{rad}\,\mathrm{s}^{-3}"),
}


def _display_statistic_metric(metric: object) -> str:
    key = str(metric).strip().lower()
    return STATISTIC_METRIC_LABELS.get(key, key.replace("_", " "))


def _display_comparison(comparison: object) -> str:
    key = str(comparison).strip().lower().replace("_", " ")
    if key in {
        "base vs bc",
        "dwb vs bc",
        "base vs pgrr",
        "dwb vs pgrr",
        "base vs dagger",
        "dwb vs dagger",
        "base vs triggered dagger",
        "dwb vs triggered dagger",
    }:
        return "DWB vs PGRR"
    return str(comparison)


def _method_cell(method: object) -> str:
    """Return a restrained visual cue for the proposed method."""

    label = _latex_escape(display_method(method))
    return rf"\textbf{{{label}}}" if label == "PGRR" else label


def _difference_interval(row: Any) -> str:
    """Format an estimate and CI with the metric's scientifically meaningful unit."""

    metric = str(row.metric).strip().lower()
    scale, digits, unit = STATISTIC_FORMATS.get(metric, (1.0, 3, ""))
    estimate = scale * float(row.estimate)
    lower = scale * float(row.ci_low)
    upper = scale * float(row.ci_high)
    return (
        rf"${estimate:+.{digits}f}\;"
        rf"[{lower:+.{digits}f},\,{upper:+.{digits}f}]{unit}$"
    )


def _effect_value(row: Any) -> str:
    """Name the effect-size estimator instead of presenting an ambiguous number."""

    value = float(row.effect_size)
    test = str(row.test).strip().lower()
    if "mcnemar" in test:
        return rf"$\mathrm{{OR}}_H={value:.3g}$"
    return rf"$r_{{\mathrm{{rb}}}}={value:+.3f}$"


def _provenance(results_path: Path, summary_path: Path, commit: str) -> str:
    return (
        "% Generated only from "
        f"{results_path.as_posix()} and {summary_path.as_posix()}; "
        f"project_commit={commit}\n"
    )


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


ABLATION_COLUMNS = (
    "model",
    "action_mask",
    "checkpoint",
    "checkpoint_sha256",
    "dataset",
    "dataset_sha256",
    "parameter_count",
    "sample_count",
    "top1_accuracy",
    "top3_accuracy",
    "invalid_action_rate",
    "expert_cost_regret",
    "near_optimal_rate",
    "catastrophic_action_rate",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_offline_ablation(path: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    """Validate the immutable offline ablation and every referenced hash."""

    sidecar_path = path.with_suffix(".json")
    missing = [str(candidate) for candidate in (path, sidecar_path) if not candidate.is_file()]
    if missing:
        raise ArtifactError("missing locked offline ablation artifact(s): " + ", ".join(missing))
    try:
        frame = pd.read_csv(path)
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, pd.errors.ParserError) as error:
        raise ArtifactError(f"failed to read offline ablation artifacts: {error}") from error
    if not isinstance(sidecar, dict) or sidecar.get("schema_version") != 1:
        raise ArtifactError(f"{sidecar_path} is not a schema-version 1 object")
    if set(frame.columns) != set(ABLATION_COLUMNS):
        missing_columns = sorted(set(ABLATION_COLUMNS) - set(frame.columns))
        unexpected = sorted(set(frame.columns) - set(ABLATION_COLUMNS))
        raise ArtifactError(
            f"{path} has wrong columns; missing={missing_columns}, unexpected={unexpected}"
        )
    declared_hash = str(sidecar.get("output_sha256", ""))
    observed_hash = _sha256(path)
    if observed_hash != declared_hash:
        raise ArtifactError(
            "offline ablation CSV hash mismatch: "
            f"declared {declared_hash}, observed {observed_hash}"
        )

    expected_models = {"Uniform BC", "Margin-weighted BC", "Triggered DAgger"}
    expected_masks = {"enabled", "disabled_offline"}
    if set(frame["model"]) != expected_models or set(frame["action_mask"]) != expected_masks:
        raise ArtifactError(f"{path} does not contain the declared three-model/two-mask ablation")
    combinations = frame.groupby(["model", "action_mask"], dropna=False).size()
    if len(frame) != 6 or len(combinations) != 6 or not (combinations == 1).all():
        raise ArtifactError(f"{path} must contain exactly one row for each of six ablation cells")

    numeric_columns = (
        "parameter_count",
        "sample_count",
        "top1_accuracy",
        "top3_accuracy",
        "invalid_action_rate",
        "expert_cost_regret",
        "near_optimal_rate",
        "catastrophic_action_rate",
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ArtifactError(f"{path} contains non-finite {column}")
    for column in (
        "top1_accuracy",
        "top3_accuracy",
        "invalid_action_rate",
        "near_optimal_rate",
        "catastrophic_action_rate",
    ):
        if ((frame[column] < 0.0) | (frame[column] > 1.0)).any():
            raise ArtifactError(f"{path} contains {column} outside [0, 1]")
    if (frame["expert_cost_regret"] < 0.0).any() or (frame["parameter_count"] <= 0).any():
        raise ArtifactError(f"{path} contains a negative regret or non-positive parameter count")

    sample_counts = set(frame["sample_count"].astype(int))
    if sample_counts != {int(sidecar.get("sample_count", -1))}:
        raise ArtifactError(f"{path} sample count disagrees with {sidecar_path}")
    datasets = set(frame["dataset"].astype(str))
    dataset_hashes = set(frame["dataset_sha256"].astype(str))
    if datasets != {str(sidecar.get("dataset"))} or dataset_hashes != {
        str(sidecar.get("dataset_sha256"))
    }:
        raise ArtifactError(f"{path} dataset provenance disagrees with {sidecar_path}")
    note = str(sidecar.get("note", "")).lower()
    if "offline" not in note or "never executed" not in note:
        raise ArtifactError(f"{sidecar_path} does not state the mask-disabled execution caveat")

    artifact_root = path.resolve().parents[2]
    referenced = frame[["checkpoint", "checkpoint_sha256"]].drop_duplicates()
    for row in referenced.itertuples(index=False):
        checkpoint = artifact_root / str(row.checkpoint)
        if not checkpoint.is_file():
            raise ArtifactError(f"missing ablation checkpoint: {checkpoint}")
        if _sha256(checkpoint) != str(row.checkpoint_sha256):
            raise ArtifactError(f"checkpoint hash mismatch: {checkpoint}")
    dataset = artifact_root / next(iter(datasets))
    if not dataset.is_file():
        raise ArtifactError(f"missing ablation dataset: {dataset}")
    if _sha256(dataset) != next(iter(dataset_hashes)):
        raise ArtifactError(f"dataset hash mismatch: {dataset}")
    return frame, sidecar


def main_results_table(
    results: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    results_path: Path,
    summary_path: Path,
    output: Path,
) -> None:
    valid = _valid_rows(results)
    method_summary = summary.loc[summary["row_type"] == "method_summary"].copy()
    excluded_attempts: dict[str, int] = {}
    if "excluded_attempt_count" in method_summary.columns:
        for row in method_summary.itertuples(index=False):
            value = getattr(row, "excluded_attempt_count", np.nan)
            if pd.notna(value):
                excluded_attempts[str(row.method)] = int(value)
    rows: list[str] = []
    for method in _method_order(results["method"].unique()):
        complete = results.loc[results["method"] == method]
        selected = valid.loc[valid["method"] == method]
        successful = selected.loc[selected["outcome"] == "GOAL_REACHED"]
        episode_count = len(selected)
        excluded = excluded_attempts.get(str(method), len(complete) - episode_count)
        if display_method(method) == "PGRR" and rows:
            rows.append(r"\addlinespace[2pt]")
        rows.append(
            f"{_method_cell(method)} & {episode_count} & "
            f"{_percentage(int((selected['outcome'] == 'GOAL_REACHED').sum()), episode_count)} & "
            f"{_percentage(int((selected['outcome'] == 'COLLISION').sum()), episode_count)} & "
            f"{_percentage(int((selected['outcome'] == 'TIMEOUT').sum()), episode_count)} & "
            f"{_mean_std(selected['spl'], digits=3)} & "
            f"{_mean_std(successful['navigation_time_s'], digits=1)} & "
            f"{_mean_std(selected['min_human_distance_m'], digits=2)} & {excluded} \\\\"
        )
    commit = str(results["project_commit"].iloc[0])
    payload = _provenance(results_path, summary_path, commit) + (
        """\\begin{table*}[t]
\\caption{Closed-loop navigation outcomes on the locked manifest.}
\\label{tab:main-results}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{4.0pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}lrrrrrrrr@{}}
\\toprule
Method & $n$ & Success $\\uparrow$ (\\%) & Collision $\\downarrow$ (\\%)
& Timeout $\\downarrow$ (\\%) & SPL $\\uparrow$ & Time $\\downarrow$ (s)
& $d_{\\min}\\uparrow$ (m) & Excl. \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} DWB and PGRR use the same
$n=24$ family--density episodes; Standard and Heuristic use the common high-density subset
($n=8$). Rates are computed over valid episodes. SPL and $d_{\\min}$ use all valid episodes;
Time uses successful episodes only. Continuous entries are mean $\\pm$ sample SD when at least
two observations exist. Excl. counts retained simulator/reset failures that were retried and
excluded from algorithm rates. Bold identifies the proposed method.}
\\end{table*}
"""
    )
    _write(output, payload)


def density_results_table(
    results: pd.DataFrame,
    *,
    results_path: Path,
    summary_path: Path,
    output: Path,
) -> None:
    valid = _valid_rows(results)
    density_priority = {"low": 0, "medium": 1, "high": 2}
    densities = sorted(
        map(str, valid["density"].unique()),
        key=lambda value: (density_priority.get(value.lower(), 3), value),
    )
    rows: list[str] = []
    for density_index, density in enumerate(densities):
        if density_index:
            rows.append(r"\addlinespace[2pt]")
        for method in _method_order(valid["method"].unique()):
            selected = valid.loc[(valid["density"] == density) & (valid["method"] == method)]
            episode_count = len(selected)
            if episode_count == 0:
                continue
            successes = int((selected["outcome"] == "GOAL_REACHED").sum())
            rows.append(
                f"{_latex_escape(density.title())} & {_method_cell(method)} & "
                f"{episode_count} & "
                f"{_percentage(successes, episode_count)} & "
                f"{_percentage(int((selected['outcome'] == 'COLLISION').sum()), episode_count)} & "
                f"{_percentage(int((selected['outcome'] == 'TIMEOUT').sum()), episode_count)} \\\\"
            )
    commit = str(results["project_commit"].iloc[0])
    payload = _provenance(results_path, summary_path, commit) + (
        """\\begin{table}[t]
\\caption{Terminal outcomes by crowd density on the locked manifest.}
\\label{tab:density-results}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{3.5pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}llrrrr@{}}
\\toprule
Density & Method & $n$ & Succ. $\\uparrow$ (\\%) & Coll. $\\downarrow$ (\\%)
& Timeout $\\downarrow$ (\\%) \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\columnwidth}{\\footnotesize \\emph{Note.} Each rate uses the valid episodes
shown in $n$. Bold identifies the proposed method.}
\\end{table}
"""
    )
    _write(output, payload)


def recovery_metrics_table(
    results: pd.DataFrame,
    *,
    results_path: Path,
    summary_path: Path,
    output: Path,
) -> None:
    valid = _valid_rows(results)
    rows: list[str] = []
    for method in _method_order(valid["method"].unique()):
        selected = valid.loc[valid["method"] == method]
        if display_method(method) == "PGRR" and rows:
            rows.append(r"\addlinespace[2pt]")
        rows.append(
            f"{_method_cell(method)} & {len(selected)} & "
            f"{_mean_std(selected['recovery_trigger_count'], digits=1)} & "
            f"{_mean_std(100.0 * selected['recovery_success_rate'], digits=1)} & "
            f"{_mean_std(selected['recovery_duration_s'], digits=1)} & "
            f"{_mean_std(100.0 * selected['intervention_ratio'], digits=1)} & "
            f"{_mean_std(selected['emergency_stop_count'], digits=1)} \\\\"
        )
    commit = str(results["project_commit"].iloc[0])
    payload = _provenance(results_path, summary_path, commit) + (
        """\\begin{table*}[t]
\\caption{Recovery behavior on valid episodes from the locked manifest.}
\\label{tab:recovery-metrics}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{4.5pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}lrrrrrr@{}}
\\toprule
Method & $n$ & Triggers (ep.$^{-1}$) & Recovery success (\\%)
& Recovery time (s/ep.) & Intervention (\\%) & Emergency stops (ep.$^{-1}$) \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} Entries are episode-level mean
$\\pm$ sample SD. Recovery time is the cumulative time spent in recovery per episode. Undefined
success rates for methods with no recovery trigger are shown as dashes. Bold identifies the
proposed method.}
\\end{table*}
"""
    )
    _write(output, payload)


def statistical_results_table(
    results: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    results_path: Path,
    summary_path: Path,
    output: Path,
) -> None:
    comparisons = list(dict.fromkeys(_display_comparison(value) for value in summary["comparison"]))
    comparison_text = " / ".join(comparisons)
    rows: list[str] = []
    previous_test: str | None = None
    for row in summary.itertuples(index=False):
        test_key = "McNemar" if "mcnemar" in str(row.test).lower() else "Wilcoxon"
        if previous_test is not None and test_key != previous_test:
            rows.append(r"\addlinespace[2pt]")
        rows.append(
            f"{_latex_escape(_display_statistic_metric(row.metric))} & {test_key} & "
            f"{_difference_interval(row)} & {_p_value(float(row.p_value))} & "
            f"{_p_value(float(row.p_value_holm))} & {_effect_value(row)} & "
            f"{int(row.n_pairs)} \\\\"
        )
        previous_test = test_key
    commit = str(results["project_commit"].iloc[0])
    payload = _provenance(results_path, summary_path, commit) + (
        """\\begin{table*}[t]
\\caption{Paired PGRR--DWB comparisons on the locked manifest.}
\\label{tab:statistical-results}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{4.0pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}llrrrrr@{}}
\\toprule
Metric & Test & $\\Delta$ [95\\% CI] & $p_{\\mathrm{raw}}$ & $p_{\\mathrm{Holm}}$
& Effect size & $n_{\\mathrm{pairs}}$ \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} All differences are PGRR minus DWB
and use 95\\% percentile-bootstrap intervals; rate differences are in percentage points (pp).
Binary endpoints use exact McNemar tests and the Haldane-corrected matched odds ratio
$\\mathrm{OR}_H$; continuous endpoints use Wilcoxon signed-rank tests and matched
rank-biserial correlation $r_{\\mathrm{rb}}$. Holm correction covers all endpoints in this
table. The paired sample size varies for success-conditional metrics. Comparison set:
"""
        + _latex_escape(comparison_text)
        + ".}"
        + """
\\end{table*}
"""
    )
    _write(output, payload)


def offline_ablation_table(
    ablation: pd.DataFrame,
    sidecar: dict[str, object],
    *,
    ablation_path: Path,
    output: Path,
) -> None:
    model_order = {"Uniform BC": 0, "Margin-weighted BC": 1, "Triggered DAgger": 2}
    mask_order = {"enabled": 0, "disabled_offline": 1}
    ordered = ablation.assign(
        _model_order=ablation["model"].map(model_order),
        _mask_order=ablation["action_mask"].map(mask_order),
    ).sort_values(["_model_order", "_mask_order"])
    rows: list[str] = []
    previous_model: str | None = None
    for row in ordered.itertuples(index=False):
        mask_label = "Enabled" if row.action_mask == "enabled" else r"Disabled$^{\dagger}$"
        if previous_model is not None and row.model != previous_model:
            rows.append(r"\addlinespace[2pt]")
        regret_value = float(row.expert_cost_regret)
        if regret_value < 10_000.0:
            regret = f"{regret_value:.3f}"
        else:
            coefficient, exponent = f"{regret_value:.2e}".split("e")
            regret = rf"${coefficient}\times 10^{{{int(exponent)}}}$"
        model_label = _latex_escape(row.model)
        if row.model == "Triggered DAgger":
            model_label = rf"\textbf{{{model_label}}}"
        rows.append(
            f"{model_label} & {mask_label} & "
            f"{100.0 * float(row.top1_accuracy):.1f} & "
            f"{100.0 * float(row.top3_accuracy):.1f} & "
            f"{100.0 * float(row.invalid_action_rate):.1f} & {regret} & "
            f"{100.0 * float(row.near_optimal_rate):.1f} & "
            f"{100.0 * float(row.catastrophic_action_rate):.1f} \\\\"
        )
        previous_model = str(row.model)
    sample_count = int(sidecar["sample_count"])
    payload = (
        f"% Generated only from {ablation_path.as_posix()}; "
        f"sha256={_sha256(ablation_path)}\n"
        """\\begin{table*}[t]
\\caption{Offline policy ablation on """
        + str(sample_count)
        + """ scenario-disjoint validation states.}
\\label{tab:offline-ablation}
\\centering
\\footnotesize
\\setlength{\\tabcolsep}{4.0pt}
\\renewcommand{\\arraystretch}{1.08}
\\begin{tabular}{@{}llrrrrrr@{}}
\\toprule
Model & Planning mask & Top-1 (\\%) & Top-3 (\\%) & Invalid (\\%) & Cost regret
& Near-opt. (\\%) & Catastrophic (\\%) \\\\
\\midrule
"""
        + "\n".join(rows)
        + """
\\bottomrule
\\end{tabular}
\\vspace{2pt}

\\parbox{0.98\\textwidth}{\\footnotesize \\emph{Note.} Regret is measured in expert-cost
units; its hard invalid-action penalty dominates mask-disabled rows. $^{\\dagger}$ Disabled-mask
rows are counterfactual offline proposals and were never executed in closed loop. ``Catastrophic''
denotes selection of a hard-penalty action. Bold identifies the selected policy.}
\\end{table*}
"""
    )
    _write(output, payload)


def _macro(name: str, value: str) -> str:
    return f"\\providecommand{{\\{name}}}{{{value}}}"


def _finite_mean(values: pd.Series, label: str) -> float:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    finite = numeric[np.isfinite(numeric)]
    if finite.size == 0:
        raise ArtifactError(f"cannot generate result macro: {label} has no finite values")
    return float(np.mean(finite))


def _holm_macro(value: float) -> str:
    if value < 0.001:
        return r"\ensuremath{<0.001}"
    return f"{value:.3f}"


def result_macros(
    results: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    results_path: Path,
    summary_path: Path,
    output: Path,
) -> None:
    """Generate stable manuscript macros; absent primary evidence is fatal."""

    method_keys = {
        str(method).lower().replace("_", " ").strip(): str(method)
        for method in results["method"].unique()
    }
    try:
        base_method = next(
            method_keys[key]
            for key in ("base", "dwb", "classical dwb", "classical planner")
            if key in method_keys
        )
        pgrr_method = next(
            method_keys[key]
            for key in ("bc", "behavior cloning", "behaviour cloning")
            if key in method_keys
        )
    except StopIteration as error:
        raise ArtifactError(
            "cannot generate result macros without one base and one BC method"
        ) from error

    valid = _valid_rows(results)
    base_all = results.loc[results["method"] == base_method]
    pgrr_all = results.loc[results["method"] == pgrr_method]
    base = valid.loc[valid["method"] == base_method]
    pgrr = valid.loc[valid["method"] == pgrr_method]
    if len(base_all) != 24 or len(pgrr_all) != 24:
        raise ArtifactError("result macros require the locked 24-pair base/BC evaluation")

    lines = [
        "% Automatically generated. Do not hand-edit numerical claims.",
        _provenance(results_path, summary_path, str(results["project_commit"].iloc[0])).rstrip(),
        _macro("PGRRTotalEpisodeCount", str(len(results))),
        _macro("PGRRMainPairCount", str(len(base_all))),
        _macro(
            "PGRRHighDensityPairCount",
            str(
                len(
                    results.loc[
                        results["method"]
                        .astype(str)
                        .str.lower()
                        .str.replace("_", " ", regex=False)
                        .isin({"standard", "standard recovery"})
                        & results["density"].astype(str).str.lower().eq("high")
                    ]
                )
            ),
        ),
        _macro("PGRRBaseValidEpisodeCount", str(len(base))),
        _macro("PGRRValidEpisodeCount", str(len(pgrr))),
    ]

    for prefix, selected in (("PGRRBase", base), ("PGRR", pgrr)):
        denominator = len(selected)
        if denominator == 0:
            raise ArtifactError(f"cannot generate result macros for empty method {prefix}")
        for suffix, outcome in (
            ("SuccessRate", "GOAL_REACHED"),
            ("CollisionRate", "COLLISION"),
            ("TimeoutRate", "TIMEOUT"),
        ):
            rate = 100.0 * float((selected["outcome"] == outcome).mean())
            lines.append(_macro(prefix + suffix, f"{rate:.1f}\\%"))
        successful = selected.loc[selected["outcome"] == "GOAL_REACHED"]
        lines.extend(
            (
                _macro(prefix + "MeanSPL", f"{_finite_mean(selected['spl'], prefix + ' SPL'):.3f}"),
                _macro(
                    prefix + "SuccessfulTime",
                    f"{_finite_mean(successful['navigation_time_s'], prefix + ' time'):.1f}~s",
                ),
                _macro(
                    prefix + "MinHumanDistance",
                    f"{_finite_mean(selected['min_human_distance_m'], prefix + ' distance'):.3f}~m",
                ),
            )
        )

    paired_metrics = {
        "goal_reached": ("Success", 100.0, r"\,\mathrm{pp}", 1),
        "collision": ("Collision", 100.0, r"\,\mathrm{pp}", 1),
        "timeout": ("Timeout", 100.0, r"\,\mathrm{pp}", 1),
        "successful_episode_duration_s": ("SuccessfulTime", 1.0, r"\,\mathrm{s}", 1),
        "min_human_distance_m": ("MinHumanDistance", 1.0, r"\,\mathrm{m}", 3),
    }
    for metric, (prefix, scale, unit, digits) in paired_metrics.items():
        comparison = summary["comparison"].astype(str).str.lower()
        main_comparison = comparison.str.contains(
            r"\b(?:base|dwb)\b", regex=True
        ) & comparison.str.contains(
            r"\b(?:bc|pgrr|dagger)\b|behavior cloning|behaviour cloning|triggered dagger",
            regex=True,
        )
        matches = summary.loc[
            (summary["metric"].astype(str).str.lower() == metric) & main_comparison
        ]
        if len(matches) != 1:
            raise ArtifactError(
                f"result macros require exactly one paired summary row for {metric}; "
                f"found {len(matches)}"
            )
        row = matches.iloc[0]
        estimate = scale * float(row["estimate"])
        lower = scale * float(row["ci_low"])
        upper = scale * float(row["ci_high"])
        lines.extend(
            (
                _macro(
                    "PGRR" + prefix + "Difference",
                    f"\\ensuremath{{{estimate:+.{digits}f}{unit}}}",
                ),
                _macro(
                    "PGRR" + prefix + "CILow",
                    f"\\ensuremath{{{lower:+.{digits}f}{unit}}}",
                ),
                _macro(
                    "PGRR" + prefix + "CIHigh",
                    f"\\ensuremath{{{upper:+.{digits}f}{unit}}}",
                ),
                _macro("PGRR" + prefix + "HolmP", _holm_macro(float(row["p_value_holm"]))),
            )
        )
    _write(output, "\n".join(lines) + "\n")


def generate_tables(
    results_path: Path,
    summary_path: Path,
    output_dir: Path,
    statistics_path: Path | None = ROOT / "outputs/final/statistics.json",
    ablation_path: Path = ROOT / "outputs/final/offline_policy_ablation.csv",
) -> list[Path]:
    results, summary = load_final_artifacts(results_path, summary_path, statistics_path)
    raw_summary = pd.read_csv(summary_path)
    ablation, ablation_sidecar = load_offline_ablation(ablation_path)
    outputs = [
        output_dir / "main_results.tex",
        output_dir / "density_results.tex",
        output_dir / "recovery_metrics.tex",
        output_dir / "statistical_results.tex",
        output_dir / "offline_ablation.tex",
        output_dir / "result_macros.tex",
    ]
    main_results_table(
        results,
        raw_summary,
        results_path=results_path,
        summary_path=summary_path,
        output=outputs[0],
    )
    density_results_table(
        results,
        results_path=results_path,
        summary_path=summary_path,
        output=outputs[1],
    )
    recovery_metrics_table(
        results,
        results_path=results_path,
        summary_path=summary_path,
        output=outputs[2],
    )
    statistical_results_table(
        results,
        summary,
        results_path=results_path,
        summary_path=summary_path,
        output=outputs[3],
    )
    offline_ablation_table(
        ablation,
        ablation_sidecar,
        ablation_path=ablation_path,
        output=outputs[4],
    )
    result_macros(
        results,
        summary,
        results_path=results_path,
        summary_path=summary_path,
        output=outputs[5],
    )
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=ROOT / "outputs/final/results.parquet",
        help="Locked episode-level results Parquet (default: outputs/final/results.parquet)",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "outputs/final/summary.csv",
        help="Locked statistical summary CSV (default: outputs/final/summary.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "paper/generated",
        help="Destination for generated LaTeX (default: paper/generated)",
    )
    parser.add_argument(
        "--statistics-json",
        type=Path,
        default=ROOT / "outputs/final/statistics.json",
        help="Optional authoritative statistics JSON; cross-checked when present",
    )
    parser.add_argument(
        "--ablation",
        type=Path,
        default=ROOT / "outputs/final/offline_policy_ablation.csv",
        help=(
            "Locked offline policy ablation CSV "
            "(default: outputs/final/offline_policy_ablation.csv)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_tables(
            args.results,
            args.summary,
            args.output_dir,
            args.statistics_json,
            args.ablation,
        )
    except (ArtifactError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
