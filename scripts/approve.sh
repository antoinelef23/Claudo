#!/usr/bin/env bash
# Human validation of a checkpoint: scripts/approve.sh CP-1 examples/agent-douche
# Creates the SIGNED approval token (HMAC) the orchestrator waits for, via
# scripts/approvals.py. Records the author and date. The token is forgeable by an
# agent only if it knows LAB_APPROVAL_SECRET (removed from the sub-agents' env).
set -euo pipefail
CP="${1:?usage: approve.sh CP-n <feature_dir>}"
FEATURE="${2:?usage: approve.sh CP-n <feature_dir>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUTHOR="$(git config user.name 2>/dev/null || whoami)"
python3 "$ROOT/scripts/approvals.py" sign "$CP" "$ROOT/$FEATURE" "$AUTHOR"
echo "✅ $CP approved for $FEATURE"
