#!/usr/bin/env bash
set -euo pipefail

PR_NUMBER="${1:-}"

if [[ -z "${PR_NUMBER}" ]]; then
  echo "Usage: $0 <PR_NUMBER>"
  exit 2
fi

REPO="$(
  gh repo view \
    --json nameWithOwner \
    --jq '.nameWithOwner'
)"

echo "Repository: ${REPO}"
echo "Pull request: #${PR_NUMBER}"

PR_STATE="$(
  gh pr view "${PR_NUMBER}" \
    --json state \
    --jq '.state'
)"

if [[ "${PR_STATE}" != "OPEN" ]]; then
  echo "ERROR: PR #${PR_NUMBER} is not open: ${PR_STATE}"
  exit 1
fi

MERGEABLE="$(
  gh pr view "${PR_NUMBER}" \
    --json mergeable \
    --jq '.mergeable'
)"

if [[ "${MERGEABLE}" != "MERGEABLE" ]]; then
  echo "ERROR: PR #${PR_NUMBER} is not mergeable: ${MERGEABLE}"
  exit 1
fi

HEAD_BRANCH="$(
  gh pr view "${PR_NUMBER}" \
    --json headRefName \
    --jq '.headRefName'
)"

BASE_BRANCH="$(
  gh pr view "${PR_NUMBER}" \
    --json baseRefName \
    --jq '.baseRefName'
)"

echo "Head: ${HEAD_BRANCH}"
echo "Base: ${BASE_BRANCH}"

CHECK_JSON="$(
  gh pr view "${PR_NUMBER}" \
    --json statusCheckRollup
)"

CHECK_COUNT="$(
  jq '
    [.statusCheckRollup[] | select(.name == "test")]
    | length
  ' <<<"${CHECK_JSON}"
)"

if [[ "${CHECK_COUNT}" -lt 1 ]]; then
  echo "ERROR: required check 'test' was not found"
  exit 1
fi

FAILED_COUNT="$(
  jq '
    [
      .statusCheckRollup[]
      | select(.name == "test")
      | select(
          .status != "COMPLETED"
          or .conclusion != "SUCCESS"
        )
    ]
    | length
  ' <<<"${CHECK_JSON}"
)"

if [[ "${FAILED_COUNT}" -ne 0 ]]; then
  echo "ERROR: required CI checks are pending or unsuccessful"

  jq '
    .statusCheckRollup[]
    | select(.name == "test")
    | {
        workflow: .workflowName,
        status,
        conclusion,
        url: .detailsUrl
      }
  ' <<<"${CHECK_JSON}"

  exit 1
fi

echo "PASS: every required CI check succeeded"
echo "PASS: PR is mergeable"

gh pr merge "${PR_NUMBER}" \
  --squash \
  --delete-branch
