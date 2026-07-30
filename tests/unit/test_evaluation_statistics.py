from __future__ import annotations

import numpy as np
from ramp_core.evaluation.statistics import (
    bootstrap_paired_difference,
    exact_mcnemar,
    paired_wilcoxon,
)


def test_paired_statistics_are_deterministic_and_preserve_direction() -> None:
    reference = np.array([0.0, 1.0, 2.0, 3.0])
    treatment = np.array([1.0, 2.0, 3.0, 4.0])
    first = bootstrap_paired_difference(reference, treatment, seed=7, samples=500)
    second = bootstrap_paired_difference(reference, treatment, seed=7, samples=500)
    assert first == second
    assert first.estimate == first.lower == first.upper == 1.0
    assert paired_wilcoxon(reference, reference)["pvalue_two_sided"] == 1.0


def test_exact_mcnemar_counts_discordant_pairs() -> None:
    result = exact_mcnemar(np.array([1, 1, 0, 0]), np.array([0, 0, 1, 0]))
    assert result["reference_only"] == 2
    assert result["treatment_only"] == 1
    assert result["discordant_pairs"] == 3
    assert result["pvalue_two_sided"] == 1.0
