#!/usr/bin/env bash
# Garde-fou CI fond/forme + plan-lint sur les features changées (findings M11 + L5).
# Compare spec/design des features modifiées à une BASE (≠ HEAD : en checkout propre
# arbre==HEAD, --git passerait trivialement — cf. content_guard --against).
#
# BASE (env)   : ref de comparaison (défaut origin/main).
# Bloquant     : content_guard (fond changé sans bump de version) → exit 1.
# Informatif   : plan-lint (make validate) — non bloquant (l'Owner a déjà approuvé).
# Fail-safe    : base introuvable → skip (pas de rouge CI spurieux).
set -uo pipefail
BASE="${BASE:-origin/main}"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null 2>&1; then
  echo "ℹ️  base '$BASE' introuvable — skip content-guard/plan-lint CI (non bloquant)."
  exit 0
fi

features=$(git diff --name-only "$BASE"...HEAD -- work/ examples/ 2>/dev/null \
  | sed -E 's@^(work|examples)/([^/]+)/.*@\1/\2@' | sort -u)

if [ -z "$features" ]; then
  echo "✅ aucune feature changée vs $BASE — rien à vérifier."
  exit 0
fi

rc=0
for feat in $features; do
  [ -f "$feat/spec.md" ] || { echo "⏭  $feat : pas de spec.md, skip"; continue; }
  echo "🔎 content-guard : $feat"
  python3 scripts/content_guard.py --against "$BASE" "$feat/spec.md" || rc=1
  if [ -f "$feat/design.md" ]; then
    python3 scripts/content_guard.py --against "$BASE" "$feat/design.md" || rc=1
  fi
  if [ -f "$feat/tasks.md" ]; then
    echo "🔎 plan-lint (informatif) : $feat"
    make validate "FEATURE=$feat" || echo "⚠️  plan-lint $feat : voir ci-dessus (non bloquant)"
  fi
done
exit $rc
