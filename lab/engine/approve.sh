#!/usr/bin/env bash
# Human validation of a checkpoint: lab/engine/approve.sh CP-1 work/my-feature
# Creates the SIGNED approval token (HMAC) the orchestrator waits for, via
# lab/engine/approvals.py. Records the author and date. The token is forgeable by an
# agent only if it knows LAB_APPROVAL_SECRET (removed from the sub-agents' env).
set -euo pipefail
CP="${1:?usage: approve.sh CP-n <feature_dir>}"
FEATURE="${2:?usage: approve.sh CP-n <feature_dir>}"
# Lab repo root, resolved from THIS script's real location (engine lives at lab/engine/),
# independent of cwd and of which git repo we stand in — correct whether invoked by path,
# by bare name (PATH), or from an external project. `git rev-parse` here would resolve the
# WRONG repo when the cwd is an external project (finding: latent ROOT bug).
ROOT="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve().parents[2])' "$0")"
# External-project support: when the build lives in another repo (the engine's
# --project / LAB_PROJECT_ROOT), resolve the feature there. An absolute FEATURE is
# honored as-is. Unset + relative FEATURE ⇒ the lab repo (back-compat, unchanged).
if [[ "$FEATURE" = /* ]]; then FEATURE_DIR="$FEATURE"; else FEATURE_DIR="${LAB_PROJECT_ROOT:-$ROOT}/$FEATURE"; fi
AUTHOR="$(git config user.name 2>/dev/null || whoami)"
python3 "$ROOT/lab/engine/approvals.py" sign "$CP" "$FEATURE_DIR" "$AUTHOR"
echo "✅ $CP approved for $FEATURE_DIR"
