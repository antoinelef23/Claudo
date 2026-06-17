#!/usr/bin/env bash
# Validation humaine d'un checkpoint : scripts/approve.sh CP-1 examples/agent-douche
# Crée le jeton d'approbation SIGNÉ (HMAC) que l'orchestrateur attend, via
# scripts/approvals.py. Trace l'auteur et la date. Le jeton n'est falsifiable par un
# agent que s'il connaît LAB_APPROVAL_SECRET (retiré de l'env des sous-agents).
set -euo pipefail
CP="${1:?usage: approve.sh CP-n <feature_dir>}"
FEATURE="${2:?usage: approve.sh CP-n <feature_dir>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUTHOR="$(git config user.name 2>/dev/null || whoami)"
python3 "$ROOT/scripts/approvals.py" sign "$CP" "$ROOT/$FEATURE" "$AUTHOR"
echo "✅ $CP approuvé pour $FEATURE"
