# Safe GitHub publication

Publish only from an isolated repository reconstructed from the exact final
commit. Do not push the research worktree, its tags, its existing student
branch, or any historical refs. Historical trees predate the portable metadata
cleanup even when the current tree passes the privacy audit.

## 1. Freeze an exact source snapshot

Run after the final PDF, technical report, presentation, results, README, and
checkpoints have been committed on `teacher/reference`:

```bash
set -Eeuo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
SOURCE_COMMIT="$(git -C "${PROJECT_ROOT}" rev-parse teacher/reference^{commit})"
PUBLISH_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/pgrr-publish.XXXXXX")"

git -C "${PROJECT_ROOT}" archive --format=tar "${SOURCE_COMMIT}" |
  tar -xf - -C "${PUBLISH_ROOT}"

git -C "${PUBLISH_ROOT}" init -q -b teacher/reference
git -C "${PUBLISH_ROOT}" config user.name "Charles Chen"
git -C "${PUBLISH_ROOT}" config user.email "charles.chen@example.invalid"
git -C "${PUBLISH_ROOT}" config commit.gpgsign false
git -C "${PUBLISH_ROOT}" add -A
GIT_AUTHOR_NAME="Charles Chen" \
GIT_AUTHOR_EMAIL="charles.chen@example.invalid" \
GIT_COMMITTER_NAME="Charles Chen" \
GIT_COMMITTER_EMAIL="charles.chen@example.invalid" \
  git -C "${PUBLISH_ROOT}" commit -q \
    -m "feat: publish PGRR reproducible research artifact"
```

`git archive` deliberately excludes the original `.git` directory, ignored
runtime files, untracked logs, credentials, reflogs, and old objects.

## 2. Create the teaching branch from the clean root

The teaching script requires the source branch name `teacher/reference`. Run it
before renaming the clean root to `main`:

```bash
(
  cd "${PUBLISH_ROOT}"
  scripts/teaching/make_student_branch.sh
)
git -C "${PUBLISH_ROOT}" branch -m teacher/reference main
```

The resulting publication graph must contain one root commit on `main` and one
additional child commit on `student/reproduce`. Validate it before configuring a
remote:

```bash
conda run -n ramp-offline python \
  "${PUBLISH_ROOT}/scripts/bootstrap/audit_release_git.py" "${PUBLISH_ROOT}"
```

## 3. Audit both exact branch trees

Pass known private values dynamically; do not weaken the alias allowlist:

```bash
private_name="$(git config --global --get user.name || true)"
private_email="$(git config --global --get user.email || true)"
private_home="$(getent passwd "$(id -u)" | cut -d: -f6)"
private_host="$(hostname)"
export PGRR_PRIVACY_FORBIDDEN
PGRR_PRIVACY_FORBIDDEN="$(printf '%s:%s:%s:%s' \
  "${private_name}" "${private_email}" "${private_home}" "${private_host}")"

for ref in main student/reproduce; do
  audit_tree="$(mktemp -d "${TMPDIR:-/tmp}/pgrr-${ref//\//-}.XXXXXX")"
  git -C "${PUBLISH_ROOT}" archive --format=tar "${ref}" |
    tar -xf - -C "${audit_tree}"
  conda run -n ramp-offline python \
    "${PUBLISH_ROOT}/scripts/bootstrap/privacy_audit.py" \
    "${audit_tree}" --all-files
done
```

The privacy audit fails closed when `pdfinfo`, `pdftotext`, Pillow, or HDF5
support is unavailable. For Office ZIP files it scans every XML and relationship
member, URL-decodes external targets, restricts creator and last-modifier
identities, scans embedded media metadata and printable strings, and rejects
encrypted, malformed, missing-core, duplicate, or unsafe members.

Useful manual metadata views are:

```bash
pdfinfo presentation/PGRR_report_zh.pdf
pdftotext -enc UTF-8 presentation/PGRR_report_zh.pdf - >/dev/null
unzip -p presentation/PGRR_report_zh.pptx docProps/core.xml
unzip -Z1 presentation/PGRR_report_zh.pptx | sort
```

## 4. Protect the remote with exact leases

At the time of this audit, GitHub has only `main`, at the exact object below,
and no `student/reproduce`. Re-read both immediately before publishing. A
different value is a hard stop for review, not a reason to update the expected
value automatically.

```bash
REPOSITORY_URL="https://github.com/CC-robotics/PGRR.git"
EXPECTED_MAIN="be7524fce4a848673f1ebd69028029241e8ec8f2"
REMOTE_MAIN="$(git ls-remote "${REPOSITORY_URL}" refs/heads/main | awk '{print $1}')"
REMOTE_STUDENT="$(git ls-remote "${REPOSITORY_URL}" \
  refs/heads/student/reproduce | awk '{print $1}')"
test "${REMOTE_MAIN}" = "${EXPECTED_MAIN}"
test -z "${REMOTE_STUDENT}"

git -C "${PUBLISH_ROOT}" remote add origin "${REPOSITORY_URL}"
git -C "${PUBLISH_ROOT}" push --dry-run --atomic \
  --force-with-lease="refs/heads/main:${EXPECTED_MAIN}" \
  --force-with-lease="refs/heads/student/reproduce:" \
  origin \
  refs/heads/main:refs/heads/main \
  refs/heads/student/reproduce:refs/heads/student/reproduce
```

Only after the dry run and all audits pass, repeat the same command without
`--dry-run`. The empty expected value on the student lease means that a remotely
created student branch causes rejection. Never use `--force`, `--all`,
`--mirror`, or `--tags` for this release. Finally compare both remote OIDs with
the two local branch OIDs.
