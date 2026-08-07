#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
PRESENTATION_PPTX="${PRESENTATION_PPTX:-${PROJECT_ROOT}/presentation/PGRR_report_zh.pptx}"
PRESENTATION_PDF="${PRESENTATION_PDF:-${PROJECT_ROOT}/presentation/PGRR_report_zh.pdf}"
PRESENTATION_NOTES="${PRESENTATION_NOTES:-${PROJECT_ROOT}/presentation/speaker_notes_zh.md}"

if ! command -v libreoffice >/dev/null 2>&1; then
    echo "ERROR: LibreOffice is required to export the PPTX as PDF" >&2
    exit 1
fi
if [[ ! -s "${PRESENTATION_PPTX}" ]]; then
    echo "ERROR: presentation PPTX is missing: ${PRESENTATION_PPTX}" >&2
    exit 1
fi

PROFILE_DIR="$(mktemp -d)"
cleanup_profile() {
    rm -r -- "${PROFILE_DIR}"
}
trap cleanup_profile EXIT
PROFILE_URI="file://${PROFILE_DIR}"

libreoffice "-env:UserInstallation=${PROFILE_URI}" --headless \
    --convert-to pdf --outdir "$(dirname -- "${PRESENTATION_PDF}")" \
    "${PRESENTATION_PPTX}" >/dev/null

GENERATED_PDF="$(dirname -- "${PRESENTATION_PDF}")/$(basename -- "${PRESENTATION_PPTX}" .pptx).pdf"
if [[ "${GENERATED_PDF}" != "${PRESENTATION_PDF}" ]]; then
    install -m 0644 "${GENERATED_PDF}" "${PRESENTATION_PDF}"
fi

env -u PYTHONPATH -u ROS_DISTRO conda run -n "${CONDA_ENV_NAME}" python \
    "${PROJECT_ROOT}/scripts/presentation/validate_deck.py" \
    --pptx "${PRESENTATION_PPTX}" \
    --pdf "${PRESENTATION_PDF}" \
    --notes "${PRESENTATION_NOTES}"

env -u PYTHONPATH -u ROS_DISTRO conda run -n "${CONDA_ENV_NAME}" python \
    "${PROJECT_ROOT}/scripts/presentation/make_contact_sheet.py" \
    --pdf "${PRESENTATION_PDF}" \
    --output "${PROJECT_ROOT}/presentation/contact_sheet.png"
