#!/usr/bin/env bash
# Validation humaine d'un checkpoint : scripts/approve.sh CP-1 examples/agent-douche
# Crée le fichier d'approbation que l'orchestrateur attend. Trace l'auteur et la date.
set -euo pipefail
CP="${1:?usage: approve.sh CP-n <feature_dir>}"
FEATURE="${2:?usage: approve.sh CP-n <feature_dir>}"
# LAB_APPROVALS_DIR : volume partagé pour approuver un run hors-Mac (sinon dossier local).
DIR="${LAB_APPROVALS_DIR:-$(cd "$(dirname "$0")/.." && pwd)/$FEATURE/.approvals}"
mkdir -p "$DIR"
echo "approved_by=$(git config user.name 2>/dev/null || whoami) at=$(date -Iseconds)" > "$DIR/$CP"
echo "✅ $CP approuvé pour $FEATURE"
