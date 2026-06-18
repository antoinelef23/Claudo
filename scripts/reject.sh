#!/usr/bin/env bash
# Rejecting a checkpoint: scripts/reject.sh CP-1 <feature_dir> "reason" [T2 T3 ...]
# The orchestrator reopens the targeted tasks (default: all those of the checkpoint)
# passing the reason to the agent, then re-presents the checkpoint.
# Beyond 2 rejections of the same checkpoint: stop, manual resume (MAX_CP_REJECTS).
set -euo pipefail
CP="${1:?usage: reject.sh CP-n <feature_dir> \"reason\" [Tn ...]}"
FEATURE="${2:?usage: reject.sh CP-n <feature_dir> \"reason\" [Tn ...]}"
REASON="${3:?give a reason — it is passed verbatim to the agents}"
shift 3
DIR="$(cd "$(dirname "$0")/.." && pwd)/$FEATURE/.approvals"
mkdir -p "$DIR"
{
  echo "reason=$REASON"
  [ $# -gt 0 ] && echo "tasks=$*"
  echo "by=$(git config user.name 2>/dev/null || whoami)"
  echo "at=$(date -Iseconds)"
} > "$DIR/$CP.rejected"
echo "⛔ $CP rejected for $FEATURE — reopening: ${*:-all the checkpoint tasks}"
