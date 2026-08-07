#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"

required_artifacts=(
    paper/generated/offline_ablation.tex
    paper/generated/moderate_result_macros.tex
    paper/generated/moderate_main_results.tex
    paper/generated/moderate_density_results.tex
    paper/generated/moderate_recovery_metrics.tex
    paper/generated/moderate_pairwise_statistics.tex
    paper/figures/system_architecture.pdf
    paper/figures/action_space_expert.pdf
    paper/figures/moderate_outcomes_and_density.pdf
    paper/figures/moderate_family_success.pdf
    paper/figures/moderate_paired_effects.pdf
    paper/figures/moderate_safety_efficiency.pdf
    paper/figures/moderate_matched_base_pgrr_trajectory.pdf
    paper/figures/moderate_pgrr_recovery_timeline.pdf
)
for artifact in "${required_artifacts[@]}"; do
    if [[ ! -s "${PROJECT_ROOT}/${artifact}" ]]; then
        echo "ERROR: missing generated moderate benchmark paper artifact: ${artifact}" >&2
        echo "Run 'make statistics figures tables' after the complete final run." >&2
        exit 1
    fi
done

cd "${PROJECT_ROOT}/paper"
if command -v latexmk >/dev/null 2>&1; then
    latexmk -pdf -interaction=nonstopmode main.tex
elif conda run -n "${CONDA_ENV_NAME}" tectonic --version >/dev/null 2>&1; then
    env -u PYTHONPATH conda run -n "${CONDA_ENV_NAME}" \
        tectonic --keep-logs main.tex
else
    echo "ERROR: install latexmk or the declared ramp-offline tectonic dependency" >&2
    exit 1
fi

test -s main.pdf
if ! command -v pdfinfo >/dev/null 2>&1; then
    echo "ERROR: pdfinfo is required to enforce the conference page limit" >&2
    exit 1
fi
paper_pages="$(pdfinfo main.pdf | awk '/^Pages:/ {print $2}')"
if [[ "${paper_pages}" != "8" ]]; then
    echo "ERROR: conference paper must contain exactly 8 pages; found ${paper_pages:-unknown}" >&2
    exit 1
fi
if grep -Eq "undefined references|Citation .* undefined|Reference .* undefined" main.log; then
    echo "ERROR: unresolved paper reference or citation" >&2
    exit 1
fi
if grep -Fq 'Overfull \hbox' main.log; then
    echo "ERROR: paper contains an overfull box" >&2
    exit 1
fi
if command -v pdffonts >/dev/null 2>&1; then
    if pdffonts main.pdf | tail -n +3 | grep -q "Type 3"; then
        echo "ERROR: paper contains Type 3 bitmap fonts" >&2
        exit 1
    fi
    if pdffonts main.pdf | awk 'NR > 2 && $4 == "no" { found = 1 } END { exit !found }'; then
        echo "ERROR: paper contains an unembedded font" >&2
        exit 1
    fi
fi
echo "Paper PASS: ${PROJECT_ROOT}/paper/main.pdf"
