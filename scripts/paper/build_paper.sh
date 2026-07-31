#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"

env -u PYTHONPATH conda run -n "${CONDA_ENV_NAME}" \
    python "${PROJECT_ROOT}/scripts/paper/make_figures.py"
env -u PYTHONPATH conda run -n "${CONDA_ENV_NAME}" \
    python "${PROJECT_ROOT}/scripts/paper/make_tables.py"

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
if grep -Eq "undefined references|Citation .* undefined|Reference .* undefined" main.log; then
    echo "ERROR: unresolved paper reference or citation" >&2
    exit 1
fi
if grep -q "Overfull \\hbox" main.log; then
    echo "ERROR: paper contains an overfull box" >&2
    exit 1
fi
echo "Paper PASS: ${PROJECT_ROOT}/paper/main.pdf"
