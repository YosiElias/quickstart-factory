#!/usr/bin/env bash
# Tests for validate-checkpoint.sh
set -u

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/validate-checkpoint.sh"
# shellcheck source=validate-checkpoint.sh
source "$SCRIPT"  # build_expected
passed=0
failed=0

assert_exit() {
  local expected="$1" desc="$2"
  shift 2
  local output rc
  output="$("$@" 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -eq "$expected" ]; then
    printf 'PASS  %s\n' "$desc"
    passed=$((passed + 1))
  else
    printf 'FAIL  %s (expected exit %s, got %s)\n' "$desc" "$expected" "$rc"
    printf '      %s\n' "$output" | head -n 5
    failed=$((failed + 1))
  fi
}

# Temp git repo with origin/main; HEAD has one commit ahead touching skills/$skill
make_repo() {
  local root="$1" skill="$2" body="$3"
  rm -rf "$root"
  mkdir -p "$root/skills/$skill" "$root/origin.git"
  git init -q --bare "$root/origin.git"
  git -C "$root" init -q
  git -C "$root" config user.email "test@example.com"
  git -C "$root" config user.name "test"
  git -C "$root" remote add origin "$root/origin.git"

  printf 'skills:\n  - id: %s\n' "$skill" > "$root/registry.yaml"
  printf 'base\n' > "$root/skills/$skill/SKILL.md"
  git -C "$root" add -A
  git -C "$root" commit -q -m base
  git -C "$root" branch -M main
  git -C "$root" push -q origin main

  printf '%s\n' "$body" > "$root/skills/$skill/SKILL.md"
  git -C "$root" add -A
  git -C "$root" commit -q -m change
}

run_in() {
  local root="$1"
  shift
  (cd "$root" && bash "$SCRIPT" "$@")
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

EMPTY_REG="$TMP/empty.yaml"
printf 'skills: []\n' > "$EMPTY_REG"
ONE_REG="$TMP/one.yaml"
printf 'skills:\n  - id: rh-qs-architect\n' > "$ONE_REG"

# --- early failures (cwd = this repo) ---
assert_exit 1 "missing registry" \
  bash "$SCRIPT" main "$TMP/skills" "$TMP/missing.yaml"

assert_exit 1 "empty registry skills" \
  bash "$SCRIPT" main "$TMP/skills" "$EMPTY_REG"

assert_exit 1 "bad base ref" \
  bash "$SCRIPT" does-not-exist core/skills "$ONE_REG"

# --- no changes → 0 ---
NOCHG="$TMP/no-change"
make_repo "$NOCHG" "test-skill" "$(build_expected test-skill)"
git -C "$NOCHG" push -q origin main
assert_exit 0 "no skill changes" \
  run_in "$NOCHG" main skills registry.yaml

# --- non-pipeline skill changed → 0 ---
NONPIPE="$TMP/non-pipe"
make_repo "$NONPIPE" "test-skill" "ignored"
git -C "$NONPIPE" reset -q --hard origin/main
mkdir -p "$NONPIPE/skills/other-skill"
printf 'changed\n' > "$NONPIPE/skills/other-skill/SKILL.md"
git -C "$NONPIPE" add -A
git -C "$NONPIPE" commit -q -m other
assert_exit 0 "non-pipeline skill changed" \
  run_in "$NONPIPE" main skills registry.yaml

# --- broken checkpoint → 1 ---
BAD="$TMP/bad"
make_repo "$BAD" "test-skill" "# no checkpoint here"
assert_exit 1 "missing checkpoint block" \
  run_in "$BAD" main skills registry.yaml

# --- good checkpoint → 0 ---
GOOD="$TMP/good"
make_repo "$GOOD" "test-skill" "$(printf '# Title\n\n%s\n' "$(build_expected test-skill)")"
assert_exit 0 "valid checkpoint block" \
  run_in "$GOOD" main skills registry.yaml

echo ""
echo "Results: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
