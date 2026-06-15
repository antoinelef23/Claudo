#!/usr/bin/env bash
# Rejet d'un checkpoint : scripts/reject.sh CP-1 <feature_dir> "raison" [T2 T3 ...]
# L'orchestrateur réouvre les tâches visées (défaut : toutes celles du checkpoint)
# en transmettant la raison à l'agent, puis re-présente le checkpoint.
# Au-delà de 2 rejets du même checkpoint : arrêt, reprise manuelle (MAX_CP_REJECTS).
set -euo pipefail
CP="${1:?usage: reject.sh CP-n <feature_dir> \"raison\" [Tn ...]}"
FEATURE="${2:?usage: reject.sh CP-n <feature_dir> \"raison\" [Tn ...]}"
REASON="${3:?donne une raison — elle est transmise telle quelle aux agents}"
shift 3
# LAB_APPROVALS_DIR : volume partagé pour rejeter un run hors-Mac (sinon dossier local).
DIR="${LAB_APPROVALS_DIR:-$(cd "$(dirname "$0")/.." && pwd)/$FEATURE/.approvals}"
mkdir -p "$DIR"
{
  echo "reason=$REASON"
  [ $# -gt 0 ] && echo "tasks=$*"
  echo "by=$(git config user.name 2>/dev/null || whoami)"
  echo "at=$(date -Iseconds)"
} > "$DIR/$CP.rejected"
echo "⛔ $CP rejeté pour $FEATURE — réouverture de : ${*:-toutes les tâches du checkpoint}"
