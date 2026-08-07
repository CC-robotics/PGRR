#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_BRANCH="teacher/reference"
STUDENT_BRANCH="student/reproduce"
ALLOW_SOURCE_DIRTY=0

usage() {
    printf '%s\n' \
        "Usage: scripts/teaching/make_student_branch.sh [--allow-source-dirty]" \
        "" \
        "Create ${STUDENT_BRANCH} from ${SOURCE_BRANCH} in an isolated Git worktree." \
        "The command refuses a different current branch or an already-existing" \
        "student branch. By default it also refuses a dirty source working tree." \
        "" \
        "  --allow-source-dirty  Build only from the committed source HEAD while" \
        "                        leaving tracked and untracked source files intact." \
        "" \
        "The command never checks out, stashes, resets, or writes files in the" \
        "caller's working tree."
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --allow-source-dirty)
            ALLOW_SOURCE_DIRTY=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'error: unsupported argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPOSITORY="$(git -C "${SCRIPT_DIR}/../.." rev-parse --show-toplevel)"
CALLER_BRANCH="$(git -C "${REPOSITORY}" symbolic-ref --quiet --short HEAD || true)"

if [[ "${CALLER_BRANCH}" != "${SOURCE_BRANCH}" ]]; then
    printf 'error: run from %s; current branch is %s\n' \
        "${SOURCE_BRANCH}" "${CALLER_BRANCH:-detached HEAD}" >&2
    exit 1
fi

if ! git -C "${REPOSITORY}" show-ref --verify --quiet "refs/heads/${SOURCE_BRANCH}"; then
    printf 'error: source branch does not exist: %s\n' "${SOURCE_BRANCH}" >&2
    exit 1
fi

SOURCE_HEAD="$(git -C "${REPOSITORY}" rev-parse "refs/heads/${SOURCE_BRANCH}^{commit}")"
CALLER_HEAD="$(git -C "${REPOSITORY}" rev-parse "HEAD^{commit}")"
if [[ "${CALLER_HEAD}" != "${SOURCE_HEAD}" ]]; then
    printf 'error: caller HEAD does not match %s\n' "${SOURCE_BRANCH}" >&2
    exit 1
fi

SOURCE_STATUS="$(git -C "${REPOSITORY}" status --porcelain=v1 --untracked-files=all)"
if [[ -n "${SOURCE_STATUS}" && "${ALLOW_SOURCE_DIRTY}" -ne 1 ]]; then
    printf '%s\n' \
        'error: source working tree is dirty; refusing by default' \
        'Re-run with --allow-source-dirty to use only the committed source HEAD.' >&2
    exit 1
fi
if [[ -n "${SOURCE_STATUS}" ]]; then
    printf 'warning: source working tree is dirty; using committed HEAD %s only\n' \
        "${SOURCE_HEAD}" >&2
fi

if git -C "${REPOSITORY}" show-ref --verify --quiet "refs/heads/${STUDENT_BRANCH}"; then
    printf 'error: student branch already exists: %s\n' "${STUDENT_BRANCH}" >&2
    printf '%s\n' 'Refusing to overwrite it. Review or delete it explicitly before retrying.' >&2
    exit 1
fi

TEMP_PARENT="${TMPDIR:-/tmp}"
WORKTREE="$(mktemp -d "${TEMP_PARENT%/}/pgrr-student.XXXXXX")"
WORKTREE_ADDED=0
BRANCH_CREATED=0
CREATED_BRANCH_TIP=""
SUCCESS=0

cleanup() {
    local status=$?
    local current_tip=""
    trap - EXIT INT TERM
    if [[ "${WORKTREE_ADDED}" -eq 1 ]]; then
        git -C "${REPOSITORY}" worktree remove --force "${WORKTREE}" >/dev/null 2>&1 || true
    else
        rmdir "${WORKTREE}" >/dev/null 2>&1 || true
    fi
    if [[ "${SUCCESS}" -ne 1 && "${BRANCH_CREATED}" -eq 1 ]]; then
        current_tip="$(git -C "${REPOSITORY}" rev-parse --verify \
            "refs/heads/${STUDENT_BRANCH}^{commit}" 2>/dev/null || true)"
        if [[ -n "${CREATED_BRANCH_TIP}" && "${current_tip}" == "${CREATED_BRANCH_TIP}" ]]; then
            git -C "${REPOSITORY}" update-ref -d \
                "refs/heads/${STUDENT_BRANCH}" "${current_tip}" >/dev/null 2>&1 || true
        elif [[ -n "${current_tip}" ]]; then
            printf 'warning: leaving %s intact because its tip changed unexpectedly\n' \
                "${STUDENT_BRANCH}" >&2
        fi
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

git -C "${REPOSITORY}" worktree add -b "${STUDENT_BRANCH}" "${WORKTREE}" "${SOURCE_HEAD}"
WORKTREE_ADDED=1
BRANCH_CREATED=1
CREATED_BRANCH_TIP="${SOURCE_HEAD}"

python3 "${WORKTREE}/teaching/student_templates/apply_student_tasks.py" "${WORKTREE}"

# These checks validate the starter files without running deliberately failing
# assignment tests or any simulator process.
python3 -m compileall -q \
    "${WORKTREE}/packages/ramp_core/ramp_core" \
    "${WORKTREE}/packages/ramp_ml/ramp_ml" \
    "${WORKTREE}/scripts/evaluate/offline_policy_ablation.py" \
    "${WORKTREE}/scripts/paper/make_figures.py"
if command -v ruff >/dev/null 2>&1; then
    ruff check \
        "${WORKTREE}/packages/ramp_core/ramp_core/planning/astar.py" \
        "${WORKTREE}/packages/ramp_core/ramp_core/action_space.py" \
        "${WORKTREE}/packages/ramp_core/ramp_core/failure/rules.py" \
        "${WORKTREE}/packages/ramp_core/ramp_core/planning/costs.py" \
        "${WORKTREE}/packages/ramp_ml/ramp_ml/bc.py" \
        "${WORKTREE}/scripts/evaluate/offline_policy_ablation.py" \
        "${WORKTREE}/scripts/paper/make_figures.py" \
        "${WORKTREE}/tests/student/test_student_tasks.py"
fi

git -C "${WORKTREE}" add \
    packages/ramp_core/ramp_core/planning/astar.py \
    packages/ramp_core/ramp_core/action_space.py \
    packages/ramp_core/ramp_core/failure/rules.py \
    packages/ramp_core/ramp_core/planning/costs.py \
    packages/ramp_ml/ramp_ml/bc.py \
    scripts/evaluate/offline_policy_ablation.py \
    scripts/paper/make_figures.py \
    tests/student/test_student_tasks.py
git -C "${WORKTREE}" commit -m "teaching: create PGRR student reproduction tasks"
CREATED_BRANCH_TIP="$(git -C "${WORKTREE}" rev-parse "HEAD^{commit}")"

FINAL_CALLER_BRANCH="$(git -C "${REPOSITORY}" symbolic-ref --quiet --short HEAD || true)"
FINAL_CALLER_HEAD="$(git -C "${REPOSITORY}" rev-parse "HEAD^{commit}")"
if [[ "${FINAL_CALLER_BRANCH}" != "${SOURCE_BRANCH}" || "${FINAL_CALLER_HEAD}" != "${SOURCE_HEAD}" ]]; then
    printf '%s\n' \
        'error: caller branch or committed HEAD changed unexpectedly; refusing success' >&2
    exit 1
fi

SUCCESS=1
printf 'Created %s at %s\n' \
    "${STUDENT_BRANCH}" "$(git -C "${WORKTREE}" rev-parse --short HEAD)"
printf 'Caller remains on %s at %s. Inspect with: git log %s -1 --stat\n' \
    "${SOURCE_BRANCH}" "${SOURCE_HEAD:0:12}" "${STUDENT_BRANCH}"
