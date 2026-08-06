#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ramp-offline}"
MODERATE_ANALYSIS_DIR="${MODERATE_ANALYSIS_DIR:-outputs/moderate/final}"
MODERATE_EXPECTED_CONDITIONS="${MODERATE_EXPECTED_CONDITIONS:-120}"
FINAL_EVALUATION_CONFIG="${FINAL_EVALUATION_CONFIG:-configs/final/ei_gazebo.yaml}"
MODERATE_BENCHMARK_CONFIG="${MODERATE_BENCHMARK_CONFIG:-configs/experiments/scenario_catalog_moderate_v5.yaml}"
MODERATE_TEST_SPLIT="${MODERATE_TEST_SPLIT:-scenarios/splits/moderate_v5_test.yaml}"
MODERATE_CALIBRATION_REPORT="${MODERATE_CALIBRATION_REPORT:-outputs/moderate/v5_validation/calibration_report.json}"
PGRR_RELEASE_MODE="${PGRR_RELEASE_MODE:-0}"
PGRR_RECOLLECT_RAW="${PGRR_RECOLLECT_RAW:-0}"

EPISODE_MANIFEST="${MODERATE_ANALYSIS_DIR}/episode_manifest.parquet"
RUN_MANIFEST="${MODERATE_ANALYSIS_DIR}/run_manifest.json"
RESULTS="${MODERATE_ANALYSIS_DIR}/results.parquet"
SUMMARY="${MODERATE_ANALYSIS_DIR}/summary.csv"
STATISTICS="${MODERATE_ANALYSIS_DIR}/pairwise_statistics.json"
FAILURE_ANALYSIS="${MODERATE_ANALYSIS_DIR}/failure_analysis.md"
METHODS=(base standard heuristic bc_uniform pgrr)
OFFLINE_ABLATION="${MODERATE_ANALYSIS_DIR}/offline_policy_ablation.csv"
OFFLINE_ABLATION_SIDECAR="${MODERATE_ANALYSIS_DIR}/offline_policy_ablation.json"
OFFLINE_ABLATION_DATASET="data/interim/multiscenario_safety_aligned_validation.h5"
FINAL_MEDIA_DIR="${MODERATE_ANALYSIS_DIR}/media"
FINAL_KEYFRAMES_PDF="${FINAL_MEDIA_DIR}/pgrr_representative_telemetry_keyframes.pdf"
FINAL_KEYFRAMES_PNG="${FINAL_MEDIA_DIR}/pgrr_representative_telemetry_keyframes.png"
FINAL_VIDEO="${FINAL_MEDIA_DIR}/pgrr_representative_telemetry.mp4"
REPORT_DATA="report/generated/report_data.json"
REPORT_PDF="report/PGRR_technical_report_zh.pdf"
PRESENTATION_PPTX="presentation/PGRR_report_zh.pptx"
PRESENTATION_PDF="presentation/PGRR_report_zh.pdf"
PRESENTATION_NOTES="presentation/speaker_notes_zh.md"
PRESENTATION_CONTACT_SHEET="presentation/contact_sheet.png"

if (($#)); then
    echo "Usage: scripts/reproduce_paper.sh" >&2
    exit 2
fi
if [[ ! -f "${PROJECT_ROOT}/pyproject.toml" ]]; then
    echo "ERROR: repository root could not be resolved from ${BASH_SOURCE[0]}" >&2
    exit 1
fi
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda is required for the ramp-offline environment" >&2
    exit 1
fi
case "${PGRR_RELEASE_MODE}" in
    0 | 1) ;;
    *)
        echo "ERROR: PGRR_RELEASE_MODE must be 0 (development rebuild) or 1 (release validation)" >&2
        exit 2
        ;;
esac
case "${PGRR_RECOLLECT_RAW}" in
    0 | 1) ;;
    *)
        echo "ERROR: PGRR_RECOLLECT_RAW must be 0 (published inputs) or 1 (raw recollection)" >&2
        exit 2
        ;;
esac
if [[ "${MODERATE_ANALYSIS_DIR}" != "outputs/moderate/final" ]]; then
    echo "ERROR: final reproduction only accepts outputs/moderate/final" >&2
    echo "Validation, pilot, smoke, calibration, and historical outputs/final are forbidden." >&2
    exit 2
fi
if [[ "${MODERATE_EXPECTED_CONDITIONS}" != "120" ]]; then
    echo "ERROR: final reproduction requires exactly 120 paired conditions per method" >&2
    exit 2
fi
if [[ "${FINAL_EVALUATION_CONFIG}" != "configs/final/ei_gazebo.yaml" ]] \
    || [[ "${MODERATE_BENCHMARK_CONFIG}" != "configs/experiments/scenario_catalog_moderate_v5.yaml" ]] \
    || [[ "${MODERATE_TEST_SPLIT}" != "scenarios/splits/moderate_v5_test.yaml" ]] \
    || [[ "${MODERATE_CALIBRATION_REPORT}" != "outputs/moderate/v5_validation/calibration_report.json" ]]; then
    echo "ERROR: final reproduction inputs must match the frozen moderate-v5 test protocol" >&2
    exit 2
fi

clean_env() {
    env \
        -u AMENT_PREFIX_PATH \
        -u CMAKE_PREFIX_PATH \
        -u COLCON_PREFIX_PATH \
        -u CONDA_DEFAULT_ENV \
        -u CONDA_PREFIX \
        -u CONDA_PROMPT_MODIFIER \
        -u LD_LIBRARY_PATH \
        -u PYTHONHOME \
        -u PYTHONPATH \
        -u RMW_IMPLEMENTATION \
        -u ROS_DOMAIN_ID \
        -u ROS_DISTRO \
        -u ROS_LOCALHOST_ONLY \
        -u ROS_PYTHON_VERSION \
        -u ROS_VERSION \
        -u VIRTUAL_ENV \
        CONDA_SHLVL=0 \
        "$@"
}

offline() {
    clean_env conda run --no-capture-output -n "${CONDA_ENV_NAME}" "$@"
}

require_file() {
    local path="$1"
    local label="$2"
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: missing ${label}: ${path}" >&2
        exit 1
    fi
}

require_pdf_pages() {
    local path="$1"
    local expected="$2"
    local label="$3"
    local observed
    require_file "${path}" "${label}"
    if ! command -v pdfinfo >/dev/null 2>&1; then
        echo "ERROR: pdfinfo is required to validate ${label}" >&2
        exit 1
    fi
    observed="$(pdfinfo "${path}" | awk '/^Pages:/ {print $2}')"
    if [[ "${observed}" != "${expected}" ]]; then
        echo "ERROR: ${label} must contain exactly ${expected} pages; found ${observed:-unknown}" >&2
        exit 1
    fi
}

require_pdf_page_range() {
    local path="$1"
    local minimum="$2"
    local maximum="$3"
    local label="$4"
    local observed
    require_file "${path}" "${label}"
    if ! command -v pdfinfo >/dev/null 2>&1; then
        echo "ERROR: pdfinfo is required to validate ${label}" >&2
        exit 1
    fi
    observed="$(pdfinfo "${path}" | awk '/^Pages:/ {print $2}')"
    if [[ ! "${observed}" =~ ^[0-9]+$ ]] \
        || ((observed < minimum || observed > maximum)); then
        echo "ERROR: ${label} must contain ${minimum}--${maximum} pages; found ${observed:-unknown}" >&2
        exit 1
    fi
}

manifest_command=(
    python scripts/paper/build_artifact_manifest.py
    --config "${MODERATE_BENCHMARK_CONFIG}"
    --evaluation-config "${FINAL_EVALUATION_CONFIG}"
    --test-split "${MODERATE_TEST_SPLIT}"
    --results "${RESULTS}"
    --summary "${SUMMARY}"
    --statistics "${STATISTICS}"
    --calibration-report "${MODERATE_CALIBRATION_REPORT}"
    --failure-analysis "${FAILURE_ANALYSIS}"
    --episode-manifest "${EPISODE_MANIFEST}"
    --run-manifest "${RUN_MANIFEST}"
    --offline-ablation "${OFFLINE_ABLATION}"
    --offline-ablation-dataset "${OFFLINE_ABLATION_DATASET}"
    --media-keyframes-pdf "${FINAL_KEYFRAMES_PDF}"
    --media-keyframes-png "${FINAL_KEYFRAMES_PNG}"
    --video "${FINAL_VIDEO}"
    --paper paper/main.pdf
    --report "${REPORT_PDF}"
    --report-data "${REPORT_DATA}"
    --presentation-pptx "${PRESENTATION_PPTX}"
    --presentation-pdf "${PRESENTATION_PDF}"
    --presentation-notes "${PRESENTATION_NOTES}"
    --presentation-contact-sheet "${PRESENTATION_CONTACT_SHEET}"
    --output "${MODERATE_ANALYSIS_DIR}/artifact_manifest.json"
    --command scripts/reproduce_paper.sh
)

cd "${PROJECT_ROOT}"

# Release mode is intentionally validate-only.  It runs before every command
# that could generate or mutate an artifact, so a clean archive cannot make
# itself dirty and then fail its own release gate.
if [[ "${PGRR_RELEASE_MODE}" == "1" ]]; then
    echo "[reproduce-paper] validating the clean release bundle; no files will be generated"
    offline "${manifest_command[@]}" --release --validate-only
    offline python scripts/bootstrap/privacy_audit.py
    if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
        echo "ERROR: release validation changed the Git worktree" >&2
        exit 1
    fi
    echo "[reproduce-paper] RELEASE VALIDATION PASS: manifest and privacy gates passed"
    exit 0
fi

for required in \
    "${EPISODE_MANIFEST}" \
    "${RUN_MANIFEST}" \
    "${FINAL_EVALUATION_CONFIG}" \
    "${MODERATE_BENCHMARK_CONFIG}" \
    "${MODERATE_TEST_SPLIT}" \
    "${MODERATE_CALIBRATION_REPORT}" \
    "${OFFLINE_ABLATION_DATASET}"; do
    require_file "${required}" "completed final-run input"
done

if [[ "${PGRR_RECOLLECT_RAW}" == "1" ]]; then
    if [[ ! -d data/raw ]]; then
        echo "ERROR: PGRR_RECOLLECT_RAW=1 requires data/raw" >&2
        exit 1
    fi
    echo "[reproduce-paper] recollecting locked raw streams; no simulation will be launched"
    offline python scripts/evaluate/offline_policy_ablation.py \
        --dataset "${OFFLINE_ABLATION_DATASET}" \
        --output "${OFFLINE_ABLATION}"
    offline python scripts/evaluate/collect_results.py \
        --manifest "${EPISODE_MANIFEST}" \
        --run-manifest "${RUN_MANIFEST}" \
        --raw-dir data/raw \
        --results "${RESULTS}" \
        --summary "${MODERATE_ANALYSIS_DIR}/collector_summary.csv" \
        --statistics "${MODERATE_ANALYSIS_DIR}/collector_statistics.json" \
        --reference-policy base \
        --treatment-policy pgrr \
        --bootstrap-seed 20260804
    offline python scripts/evaluate/summarize_moderate.py \
        --results "${RESULTS}" \
        --output-dir "${MODERATE_ANALYSIS_DIR}" \
        --methods "${METHODS[@]}" \
        --main-method pgrr \
        --reference-method base \
        --bootstrap-samples 10000 \
        --bootstrap-seed 20260804
    offline python scripts/evaluate/failure_analysis.py \
        --results "${RESULTS}" \
        --output "${FAILURE_ANALYSIS}"

    artifact_staging_dir="$(mktemp -d)"
    cleanup_artifact_staging() {
        rm -r -- "${artifact_staging_dir}"
    }
    trap cleanup_artifact_staging EXIT
    media_figure_build_dir="${artifact_staging_dir}/media/figures"
    media_video_build_dir="${artifact_staging_dir}/media/videos"
    mkdir -p "${media_figure_build_dir}" "${media_video_build_dir}"
    offline python scripts/paper/render_episode_media.py \
        --results "${RESULTS}" \
        --raw-dir data/raw \
        --method pgrr \
        --figure-dir "${media_figure_build_dir}" \
        --video-dir "${media_video_build_dir}"
    mapfile -t media_pdfs < <(find "${media_figure_build_dir}" -maxdepth 1 -type f -name '*_telemetry_keyframes.pdf' -print)
    mapfile -t media_pngs < <(find "${media_figure_build_dir}" -maxdepth 1 -type f -name '*_telemetry_keyframes.png' -print)
    mapfile -t media_videos < <(find "${media_video_build_dir}" -maxdepth 1 -type f -name '*_telemetry.mp4' -print)
    if [[ "${#media_pdfs[@]}" -ne 1 || "${#media_pngs[@]}" -ne 1 || "${#media_videos[@]}" -ne 1 ]]; then
        echo "ERROR: final media rendering must produce exactly one PDF, PNG, and MP4" >&2
        exit 1
    fi
    mkdir -p "${FINAL_MEDIA_DIR}"
    install -m 0644 "${media_pdfs[0]}" "${FINAL_KEYFRAMES_PDF}"
    install -m 0644 "${media_pngs[0]}" "${FINAL_KEYFRAMES_PNG}"
    install -m 0644 "${media_videos[0]}" "${FINAL_VIDEO}"
else
    echo "[reproduce-paper] using published result/statistics/failure/media artifacts"
    for published in \
        "${RESULTS}" \
        "${SUMMARY}" \
        "${STATISTICS}" \
        "${FAILURE_ANALYSIS}" \
        "${OFFLINE_ABLATION}" \
        "${OFFLINE_ABLATION_SIDECAR}" \
        "${FINAL_KEYFRAMES_PDF}" \
        "${FINAL_KEYFRAMES_PNG}" \
        "${FINAL_VIDEO}"; do
        require_file "${published}" "published final artifact"
    done
fi

for figure_dir in paper/figures outputs/figures; do
    offline python scripts/paper/make_method_figures.py \
        --output-dir "${figure_dir}"
    offline python scripts/paper/make_moderate_figures.py \
        --results "${RESULTS}" \
        --summary "${SUMMARY}" \
        --statistics "${STATISTICS}" \
        --expected-condition-count "${MODERATE_EXPECTED_CONDITIONS}" \
        --output-dir "${figure_dir}"
done
for table_dir in paper/generated outputs/tables; do
    offline python scripts/paper/make_moderate_tables.py \
        --results "${RESULTS}" \
        --summary "${SUMMARY}" \
        --statistics "${STATISTICS}" \
        --ablation "${OFFLINE_ABLATION}" \
        --expected-condition-count "${MODERATE_EXPECTED_CONDITIONS}" \
        --output-dir "${table_dir}"
done

clean_env \
    PROJECT_ROOT="${PROJECT_ROOT}" \
    CONDA_ENV_NAME="${CONDA_ENV_NAME}" \
    bash "${PROJECT_ROOT}/scripts/paper/build_paper.sh"
require_pdf_pages "paper/main.pdf" 8 "conference paper"

echo "[reproduce-paper] building the locked-test technical report"
clean_env \
    REPORT_STAGE=test \
    REPORT_RESULTS="${PROJECT_ROOT}/${RESULTS}" \
    REPORT_STATISTICS="${PROJECT_ROOT}/${STATISTICS}" \
    REPORT_EXPECTED_CONDITIONS=120 \
    CONDA_ENV_NAME="${CONDA_ENV_NAME}" \
    bash "${PROJECT_ROOT}/scripts/report/build_report.sh"
require_pdf_page_range "${REPORT_PDF}" 30 40 "technical report"

echo "[reproduce-paper] building the locked-test 30-slide presentation bundle"
offline python scripts/presentation/build_deck.py \
    --stage test \
    --report-data "${REPORT_DATA}" \
    --output "${PRESENTATION_PPTX}" \
    --notes "${PRESENTATION_NOTES}"
clean_env \
    PRESENTATION_PPTX="${PROJECT_ROOT}/${PRESENTATION_PPTX}" \
    PRESENTATION_PDF="${PROJECT_ROOT}/${PRESENTATION_PDF}" \
    PRESENTATION_NOTES="${PROJECT_ROOT}/${PRESENTATION_NOTES}" \
    CONDA_ENV_NAME="${CONDA_ENV_NAME}" \
    bash "${PROJECT_ROOT}/scripts/presentation/render_pdf.sh"
require_pdf_pages "${PRESENTATION_PDF}" 30 "presentation PDF"
for presentation_artifact in \
    "${PRESENTATION_PPTX}" \
    "${PRESENTATION_NOTES}" \
    "${PRESENTATION_CONTACT_SHEET}"; do
    require_file "${presentation_artifact}" "presentation artifact"
done

offline "${manifest_command[@]}"

echo "[reproduce-paper] DEVELOPMENT REBUILD PASS: artifacts rebuilt and structurally validated"
echo "[reproduce-paper] This is not a privacy/release PASS; run PGRR_RELEASE_MODE=1 on a clean tree."
