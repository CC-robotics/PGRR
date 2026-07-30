"""Small, deterministic statistical helpers used by evaluation scripts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy.stats import binomtest, wilcoxon  # type: ignore[import-untyped]


@dataclass(frozen=True)
class ConfidenceInterval:
    """A point estimate and percentile confidence interval."""

    estimate: float
    lower: float
    upper: float


def bootstrap_paired_difference(
    reference: ArrayLike,
    treatment: ArrayLike,
    *,
    seed: int,
    samples: int = 10_000,
    confidence: float = 0.95,
) -> ConfidenceInterval:
    """Bootstrap the mean paired difference ``treatment - reference``.

    Resampling is over episode pairs, preserving the paired experiment design.
    """
    reference_array = np.asarray(reference, dtype=np.float64)
    treatment_array = np.asarray(treatment, dtype=np.float64)
    if (
        reference_array.ndim != 1
        or treatment_array.ndim != 1
        or reference_array.shape != treatment_array.shape
    ):
        raise ValueError("reference and treatment must be equally shaped one-dimensional arrays")
    if reference_array.size == 0 or samples <= 0 or not 0.0 < confidence < 1.0:
        raise ValueError("non-empty inputs, positive samples, and 0 < confidence < 1 required")
    if not np.isfinite(reference_array).all() or not np.isfinite(treatment_array).all():
        raise ValueError("paired inputs must be finite")
    differences = treatment_array - reference_array
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, differences.size, size=(samples, differences.size))
    distribution = differences[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(distribution, [alpha, 1.0 - alpha])
    return ConfidenceInterval(float(differences.mean()), float(lower), float(upper))


def exact_mcnemar(reference: ArrayLike, treatment: ArrayLike) -> dict[str, float | int]:
    """Run the exact paired McNemar test on two binary outcome arrays."""
    reference_array = np.asarray(reference, dtype=np.int8)
    treatment_array = np.asarray(treatment, dtype=np.int8)
    if (
        reference_array.ndim != 1
        or treatment_array.ndim != 1
        or reference_array.shape != treatment_array.shape
    ):
        raise ValueError("reference and treatment must be equally shaped one-dimensional arrays")
    if (
        reference_array.size == 0
        or not np.isin(reference_array, (0, 1)).all()
        or not np.isin(treatment_array, (0, 1)).all()
    ):
        raise ValueError("non-empty binary arrays required")
    reference_only = int(np.sum((reference_array == 1) & (treatment_array == 0)))
    treatment_only = int(np.sum((reference_array == 0) & (treatment_array == 1)))
    discordant = reference_only + treatment_only
    pvalue = (
        1.0
        if discordant == 0
        else float(binomtest(min(reference_only, treatment_only), discordant, 0.5).pvalue)
    )
    return {
        "reference_only": reference_only,
        "treatment_only": treatment_only,
        "discordant_pairs": discordant,
        "pvalue_two_sided": pvalue,
    }


def paired_wilcoxon(reference: ArrayLike, treatment: ArrayLike) -> dict[str, float | int]:
    """Run a two-sided paired Wilcoxon test, including the all-ties case."""
    reference_array = np.asarray(reference, dtype=np.float64)
    treatment_array = np.asarray(treatment, dtype=np.float64)
    if (
        reference_array.ndim != 1
        or treatment_array.ndim != 1
        or reference_array.shape != treatment_array.shape
    ):
        raise ValueError("reference and treatment must be equally shaped one-dimensional arrays")
    if (
        reference_array.size == 0
        or not np.isfinite(reference_array).all()
        or not np.isfinite(treatment_array).all()
    ):
        raise ValueError("non-empty finite arrays required")
    nonzero = int(np.count_nonzero(treatment_array - reference_array))
    if nonzero == 0:
        return {"statistic": 0.0, "pvalue_two_sided": 1.0, "nonzero_pairs": 0}
    result = wilcoxon(
        treatment_array, reference_array, alternative="two-sided", zero_method="wilcox"
    )
    return {
        "statistic": float(result.statistic),
        "pvalue_two_sided": float(result.pvalue),
        "nonzero_pairs": nonzero,
    }
