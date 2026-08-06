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
PGRR_RELEASE_MODE="${PGRR_RELEASE_MODE:-1}"
EPISODE_MANIFEST="${MODERATE_ANALYSIS_DIR}/episode_manifest.parquet"
RUN_MANIFEST="${MODERATE_ANALYSIS_DIR}/run_manifest.json"
RESULTS="${MODERATE_ANALYSIS_DIR}/results.parquet"
SUMMARY="${MODERATE_ANALYSIS_DIR}/summary.csv"
STATISTICS="${MODERATE_ANALYSIS_DIR}/pairwise_statistics.json"
METHODS=(base standard heuristic bc_uniform pgrr)
release_args=()

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
    0) ;;
    1) release_args+=(--release) ;;
    *)
        echo "ERROR: PGRR_RELEASE_MODE must be 0 (development) or 1 (release)" >&2
        exit 2
        ;;
esac

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

cd "${PROJECT_ROOT}"
if [[ "${PGRR_RELEASE_MODE}" == "1" ]] && [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    echo "ERROR: release paper reproduction requires a clean Git worktree" >&2
    echo "Use PGRR_RELEASE_MODE=0 only for a development artifact rebuild." >&2
    exit 1
fi
for required in \
    "${EPISODE_MANIFEST}" \
    "${RUN_MANIFEST}" \
    "${FINAL_EVALUATION_CONFIG}" \
    "${MODERATE_BENCHMARK_CONFIG}" \
    "${MODERATE_TEST_SPLIT}" \
    "${MODERATE_CALIBRATION_REPORT}"; do
    if [[ ! -s "${required}" ]]; then
        echo "ERROR: missing completed final-run input: ${required}" >&2
        echo "This command only rebuilds artifacts; it never starts or resumes simulation." >&2
        exit 1
    fi
done

echo "[reproduce-paper] collecting the locked moderate-v5 run; no simulation will be launched"
offline python scripts/evaluate/offline_policy_ablation.py \
    --output outputs/final/offline_policy_ablation.csv
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
    --output "${MODERATE_ANALYSIS_DIR}/failure_analysis.md"
offline python scripts/paper/render_episode_media.py \
    --results "${RESULTS}" \
    --raw-dir data/raw \
    --method pgrr
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
offline_table_build_dir="$(mktemp -d)"
cleanup_offline_table_build() {
    rm -r -- "${offline_table_build_dir}"
}
trap cleanup_offline_table_build EXIT
offline python scripts/paper/make_tables.py \
    --results "${RESULTS}" \
    --summary "${SUMMARY}" \
    --statistics-json "${STATISTICS}" \
    --ablation outputs/final/offline_policy_ablation.csv \
    --output-dir "${offline_table_build_dir}"
for table_dir in paper/generated outputs/tables; do
    mkdir -p "${table_dir}"
    install -m 0644 \
        "${offline_table_build_dir}/offline_ablation.tex" \
        "${table_dir}/offline_ablation.tex"
    offline python scripts/paper/make_moderate_tables.py \
        --results "${RESULTS}" \
        --summary "${SUMMARY}" \
        --statistics "${STATISTICS}" \
        --expected-condition-count "${MODERATE_EXPECTED_CONDITIONS}" \
        --output-dir "${table_dir}"
done
clean_env \
    PROJECT_ROOT="${PROJECT_ROOT}" \
    CONDA_ENV_NAME="${CONDA_ENV_NAME}" \
    bash "${PROJECT_ROOT}/scripts/paper/build_paper.sh"
offline python scripts/paper/build_artifact_manifest.py \
    --config "${MODERATE_BENCHMARK_CONFIG}" \
    --evaluation-config "${FINAL_EVALUATION_CONFIG}" \
    --test-split "${MODERATE_TEST_SPLIT}" \
    --results "${RESULTS}" \
    --summary "${SUMMARY}" \
    --statistics "${STATISTICS}" \
    --calibration-report "${MODERATE_CALIBRATION_REPORT}" \
    --failure-analysis "${MODERATE_ANALYSIS_DIR}/failure_analysis.md" \
    --episode-manifest "${EPISODE_MANIFEST}" \
    --run-manifest "${RUN_MANIFEST}" \
    --output "${MODERATE_ANALYSIS_DIR}/artifact_manifest.json" \
    --command scripts/reproduce_paper.sh \
    "${release_args[@]}"

echo "[reproduce-paper] PASS: paper/main.pdf and ${MODERATE_ANALYSIS_DIR}/artifact_manifest.json"
