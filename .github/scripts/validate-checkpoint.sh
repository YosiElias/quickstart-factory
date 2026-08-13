#!/bin/bash
# Validates that pipeline skills changed in this PR end with the
# pipeline-checkpoint block.
#
# Usage: validate-checkpoint.sh <base-ref> [skills-dir] [registry]
#   base-ref    Base branch to diff against (e.g. "main").
#   skills-dir  Directory containing skill subdirectories (default: "core/skills").
#   registry    Pipeline registry YAML (default: "core/flow/pipeline-registry.yaml").
#
# Exit codes:
#   0  All changed pipeline skills have the checkpoint block.
#   1  One or more changed pipeline skills are missing or have a wrong checkpoint block.

set -uo pipefail

BASE_REF="${1:-main}"
SKILLS_DIR="${2:-core/skills}"
REGISTRY="${3:-core/flow/pipeline-registry.yaml}"

SKILLS_DIR="${SKILLS_DIR%/}"

# --- Extract pipeline skill IDs from the registry ---
if [ ! -f "$REGISTRY" ]; then
  echo "::error::Pipeline registry not found: $REGISTRY"
  exit 1
fi

mapfile -t PIPELINE_SKILLS < <(
  yq '.skills[].id' "$REGISTRY"
)

if [ "${#PIPELINE_SKILLS[@]}" -eq 0 ]; then
  echo "::error::No pipeline skills found in $REGISTRY"
  exit 1
fi

# --- Find skills changed in this PR ---
mapfile -t changed_skills < <(
  git diff --name-only "origin/${BASE_REF}...HEAD" -- "$SKILLS_DIR/" 2>/dev/null \
    | sed "s|^${SKILLS_DIR}/||" \
    | cut -d'/' -f1 \
    | sort -u \
    | grep -v '^$'
)

if [ "${#changed_skills[@]}" -eq 0 ]; then
  echo "No skill directories changed — nothing to check."
  exit 0
fi

# --- Keep only pipeline skills ---
pipeline_changed=()
for skill in "${changed_skills[@]}"; do
  for ps in "${PIPELINE_SKILLS[@]}"; do
    if [ "$skill" = "$ps" ]; then
      pipeline_changed+=("$skill")
      break
    fi
  done
done

if [ "${#pipeline_changed[@]}" -eq 0 ]; then
  echo "Changed skills are not pipeline skills — nothing to check."
  exit 0
fi

echo "Checking ${#pipeline_changed[@]} changed pipeline skill(s): ${pipeline_changed[*]}"

# --- Expected checkpoint block (last 8 non-empty lines of SKILL.md) ---
# The block must match exactly, with --skill-name set to the skill directory name.
build_expected() {
  local skill_name="$1"
  cat <<EOF
## Pipeline checkpoint
Run the checkpoint:
\`\`\`bash
python3 core/flow/pipeline-checkpoint.py --skill-name ${skill_name} --qs-name {qs-name}
\`\`\`
Print the dashboard link to the user:
"Pipeline dashboard updated — track progress at [dashboard.md](.rhoai-qs/{qs-name}/flow/dashboard.md)"
EOF
}

FAILED=0

for skill in "${pipeline_changed[@]}"; do
  skill_md="${SKILLS_DIR}/${skill}/SKILL.md"

  if [ ! -f "$skill_md" ]; then
    echo "::warning::Skipping deleted skill: $skill"
    continue
  fi

  expected="$(build_expected "$skill")"
  expected_lines="$(echo "$expected" | wc -l)"

  # Extract the last N non-empty lines from the file
  actual="$(grep -v '^\s*$' "$skill_md" | tail -n "$expected_lines")"

  if [ "$actual" != "$expected" ]; then
    echo ""
    echo "::error file=${skill_md}::${skill}: SKILL.md does not end with the required pipeline checkpoint block."
    echo "--- Expected (last ${expected_lines} non-empty lines) ---"
    echo "$expected"
    echo "--- Actual ---"
    echo "$actual"
    echo "---"
    FAILED=1
  else
    echo "  ✓ $skill"
  fi
done

echo ""
if [ $FAILED -ne 0 ]; then
  echo "Pipeline checkpoint validation failed!"
  echo ""
  echo "Every pipeline skill must end with:"
  echo ""
  build_expected '<skill-name>' | sed 's/^/  /'
  exit 1
fi

echo "✅ All changed pipeline skills have the checkpoint block."
