#!/usr/bin/env bash
# Creates labels, milestones and issues for ukvet from scripts/backlog.tsv
# Requirements: GitHub CLI (`gh`) installed and authenticated (`gh auth login`),
# run from inside the cloned ukvet repo. Safe to run once; re-running creates duplicate issues.
set -euo pipefail

cd "$(dirname "$0")/.."

TSV="scripts/backlog.tsv"
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

echo "==> Repository: $REPO"

if [[ ! -f "$TSV" ]]; then
  echo "ERROR: $TSV not found"
  exit 1
fi

echo "==> Creating labels"

labels=(
  phase-0 phase-1 phase-2 phase-3 phase-4 phase-5 phase-6
  docs research mcp agent api ui infra testing evals ci
  observability security performance models release career
)

for label in "${labels[@]}"; do
  gh label create "$label" \
    --repo "$REPO" \
    --force \
    --color "ededed" >/dev/null

  echo "   label: $label"
done

echo "==> Creating milestones"

tail -n +2 "$TSV" |
  cut -f1 |
  awk '!seen[$0]++' |
  while IFS= read -r milestone; do

    if gh api "repos/$REPO/milestones?state=all" \
      --jq '.[].title' |
      grep -Fxq "$milestone"; then

      echo "   exists: $milestone"

    else

      gh api "repos/$REPO/milestones" \
        -f title="$milestone" >/dev/null

      echo "   created: $milestone"

    fi

  done

echo "==> Creating issues"

tail -n +2 "$TSV" |
  while IFS=$'\t' read -r milestone labels title body; do

    gh issue create \
      --repo "$REPO" \
      --title "$title" \
      --body "$body

**Definition of Done:** see docs/09-plan.md §4." \
      --milestone "$milestone" \
      --label "$labels"

    echo "   created: $title"

  done

echo
echo "Done."
echo "Labels, milestones and issues have been created."
echo "Create the GitHub Project board separately."
