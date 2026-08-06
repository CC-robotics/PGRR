#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
REPORT_STAGE="${REPORT_STAGE:-pending}"
REPORT_RESULTS="${REPORT_RESULTS:-}"
REPORT_STATISTICS="${REPORT_STATISTICS:-}"
REPORT_EXPECTED_CONDITIONS="${REPORT_EXPECTED_CONDITIONS:-}"
ASSET_ARGS=(--stage "${REPORT_STAGE}" --output-dir "${PROJECT_ROOT}/report/generated")

if [[ "${REPORT_STAGE}" != "pending" ]]; then
    if [[ -z "${REPORT_RESULTS}" ]]; then
        echo "ERROR: REPORT_RESULTS is required for validation/test technical reports" >&2
        exit 2
    fi
    if [[ -z "${REPORT_STATISTICS}" ]]; then
        echo "ERROR: REPORT_STATISTICS is required for validation/test technical reports" >&2
        exit 2
    fi
    ASSET_ARGS+=(--results "${REPORT_RESULTS}" --statistics "${REPORT_STATISTICS}")
fi
if [[ -n "${REPORT_EXPECTED_CONDITIONS}" ]]; then
    ASSET_ARGS+=(--expected-conditions "${REPORT_EXPECTED_CONDITIONS}")
fi

env -u PYTHONPATH -u ROS_DISTRO -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
    conda run -n "${CONDA_ENV_NAME}" python \
    "${PROJECT_ROOT}/scripts/report/build_report_assets.py" "${ASSET_ARGS[@]}"

if ! env -u PYTHONPATH -u ROS_DISTRO conda run -n "${CONDA_ENV_NAME}" \
    tectonic --version >/dev/null 2>&1; then
    echo "ERROR: tectonic is required in the isolated offline environment" >&2
    exit 1
fi

(
    cd "${PROJECT_ROOT}/report"
    env -u PYTHONPATH -u ROS_DISTRO conda run -n "${CONDA_ENV_NAME}" \
        tectonic --keep-logs technical_report.tex
    install -m 0644 technical_report.pdf PGRR_technical_report_zh.pdf
)

env -u PYTHONPATH -u ROS_DISTRO conda run -n "${CONDA_ENV_NAME}" python \
    "${PROJECT_ROOT}/scripts/report/validate_report.py" \
    --pdf "${PROJECT_ROOT}/report/PGRR_technical_report_zh.pdf" \
    --data "${PROJECT_ROOT}/report/generated/report_data.json" \
    --log "${PROJECT_ROOT}/report/technical_report.log"
