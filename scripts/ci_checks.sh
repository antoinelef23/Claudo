#!/usr/bin/env bash
# CI substance/form guardrail + plan-lint on the changed features (findings M11 + L5).
# Compares spec/design of the modified features to a BASE (≠ HEAD: on a clean checkout
# tree==HEAD, --git would pass trivially — cf. content_guard --against).
#
# BASE (env)   : comparison ref (default origin/main).
# Blocking     : content_guard (substance changed without version bump) → exit 1.
# Informative  : plan-lint (make validate) — non-blocking (the Owner already approved).
# Fail-safe    : base not found → skip (no spurious CI red).
set -uo pipefail
BASE="${BASE:-origin/main}"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null 2>&1; then
  echo "ℹ️  base '$BASE' not found — skip content-guard/plan-lint CI (non-blocking)."
  exit 0
fi

features=$(git diff --name-only "$BASE"...HEAD -- work/ examples/ 2>/dev/null \
  | sed -E 's@^(work|examples)/([^/]+)/.*@\1/\2@' | sort -u)

if [ -z "$features" ]; then
  echo "✅ no feature changed vs $BASE — nothing to check."
  exit 0
fi

rc=0
for feat in $features; do
  [ -f "$feat/spec.md" ] || { echo "⏭  $feat: no spec.md, skip"; continue; }
  echo "🔎 content-guard: $feat"
  python3 scripts/content_guard.py --against "$BASE" "$feat/spec.md" || rc=1
  if [ -f "$feat/design.md" ]; then
    python3 scripts/content_guard.py --against "$BASE" "$feat/design.md" || rc=1
  fi
  if [ -f "$feat/tasks.md" ]; then
    echo "🔎 plan-lint (informative): $feat"
    make validate "FEATURE=$feat" || echo "⚠️  plan-lint $feat: see above (non-blocking)"
  fi
done
exit $rc
