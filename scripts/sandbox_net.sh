#!/usr/bin/env bash
# Réseau sandbox à egress allowlisté : un réseau Docker `--internal` (sans internet) + un proxy
# tinyproxy qui ne laisse sortir que vers anthropic.com. Le sandbox tourne sur l'internal et
# n'atteint l'API claude QUE via le proxy → exfiltration / installs arbitraires bloqués.
#
#   scripts/sandbox_net.sh up      # crée réseaux + lance le proxy
#   scripts/sandbox_net.sh down    # nettoie
#
# Puis :  LAB_DOCKER_NETWORK=lab-internal LAB_EGRESS_PROXY=lab-egress-proxy:8888 \
#           scripts/run_sandboxed.sh work/ma-feature
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:-up}"
PROXY=lab-egress-proxy

case "$ACTION" in
  up)
    docker network inspect lab-internal >/dev/null 2>&1 || docker network create --internal lab-internal
    docker network inspect lab-egress  >/dev/null 2>&1 || docker network create lab-egress
    docker build -t lab-egress-proxy -f "$HERE/sandbox/Dockerfile.proxy" "$HERE/sandbox"
    docker rm -f "$PROXY" >/dev/null 2>&1 || true
    docker run -d --name "$PROXY" --network lab-egress --restart unless-stopped lab-egress-proxy
    docker network connect lab-internal "$PROXY"
    echo "✅ egress proxy up — sandbox sur 'lab-internal' (sans internet direct) → $PROXY:8888 → anthropic.com seul"
    echo "   run : LAB_DOCKER_NETWORK=lab-internal LAB_EGRESS_PROXY=$PROXY:8888 scripts/run_sandboxed.sh work/ma-feature"
    ;;
  down)
    docker rm -f "$PROXY" >/dev/null 2>&1 || true
    docker network rm lab-internal lab-egress >/dev/null 2>&1 || true
    echo "🧹 egress proxy + réseaux supprimés"
    ;;
  *)
    echo "usage: sandbox_net.sh [up|down]"; exit 1 ;;
esac
