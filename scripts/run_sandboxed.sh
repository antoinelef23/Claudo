#!/usr/bin/env bash
# Lance une feature dans le sandbox conteneurisé (orchestrateur hors-Mac).
#
# Usage :  scripts/run_sandboxed.sh work/ma-feature
# Prérequis :
#   - image construite :  docker build -t lab-ia-natif .
#   - ANTHROPIC_API_KEY exportée (seule credential donnée au conteneur)
#   - approbations : déposées dans ./.sandbox-approvals (monté en /approvals) — un humain y écrit
#     via  LAB_APPROVALS_DIR=./.sandbox-approvals scripts/approve.sh CP-1 <feature>
#     (depuis cette machine OU une autre qui partage ce volume).
#
# ⚠️ SÉCURITÉ — l'agent exécute du code arbitraire (par conception). Ce conteneur est jetable
# (--rm), non-root, sans secret monté. L'EGRESS RÉSEAU reste le maillon à durcir : par défaut
# Docker donne un accès sortant complet (exfiltration / `pip install` malveillant possibles).
# En production, restreindre l'egress à api.anthropic.com via un proxy/allowlist ou un réseau
# Docker dédié filtré. `--network none` NE marche PAS : la CLI claude doit joindre l'API.
set -euo pipefail

FEATURE="${1:?usage: run_sandboxed.sh work/ma-feature}"
: "${ANTHROPIC_API_KEY:?exporte ANTHROPIC_API_KEY (seule credential du sandbox)}"
IMAGE="${LAB_IMAGE:-lab-ia-natif}"
APPROVALS_HOST="${LAB_APPROVALS_HOST:-$PWD/.sandbox-approvals}"
mkdir -p "$APPROVALS_HOST"

echo "▶ sandbox : $FEATURE  (image $IMAGE, approvals → $APPROVALS_HOST)"
echo "  egress : ${LAB_DOCKER_NETWORK:-bridge}  (a restreindre en prod si bridge — cf. en-tete)"

exec docker run --rm \
  --network "${LAB_DOCKER_NETWORK:-bridge}" \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 512 \
  --memory "${LAB_DOCKER_MEMORY:-2g}" \
  -e ANTHROPIC_API_KEY \
  -e LAB_NO_NOTIFY=1 \
  -e LAB_APPROVALS_DIR=/approvals \
  -e LAB_BUDGET_USD="${LAB_BUDGET_USD:-20}" \
  -e LAB_TASK_TIMEOUT="${LAB_TASK_TIMEOUT:-2400}" \
  ${LAB_GCHAT_WEBHOOK:+-e LAB_GCHAT_WEBHOOK} \
  ${LAB_EGRESS_PROXY:+-e HTTPS_PROXY=http://$LAB_EGRESS_PROXY -e HTTP_PROXY=http://$LAB_EGRESS_PROXY -e NO_PROXY=localhost,127.0.0.1} \
  -v "$PWD/$FEATURE":"/lab/$FEATURE" \
  -v "$APPROVALS_HOST":/approvals \
  "$IMAGE" "$FEATURE"
