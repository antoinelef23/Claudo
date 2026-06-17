#!/usr/bin/env bash
# Hook Stop + SubagentStop — LE merge gate automatique.
# Quand un agent (principal ou sous-agent) veut terminer alors que du code Python a changé,
# on exécute les evals. Rouges → exit 2 : l'agent est renvoyé corriger (avec la sortie en contexte).
# Boucle infinie évitée via stop_hook_active.
set -uo pipefail

INPUT=$(cat)

# Si on est déjà dans une relance déclenchée par ce hook, ne pas reboucler.
ACTIVE=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_hook_active',False))" 2>/dev/null || echo False)
[ "$ACTIVE" = "True" ] && exit 0

# Rien à gater tant que le projet Python n'existe pas.
[ -f pyproject.toml ] || exit 0

# Ne gater que si du code a changé depuis le dernier commit (évite de payer les evals à chaque tour de parole).
# --untracked-files=all : un NOUVEAU dossier de package non suivi s'affiche sinon en une
# seule ligne « ?? newpkg/ » que le grep raterait — le gate sauterait alors une feature
# livrée comme module neuf (finding H7).
if git rev-parse --git-dir >/dev/null 2>&1; then
  git status --porcelain --untracked-files=all | grep -qE '\.(py|toml)$' || exit 0
fi

OUT=$(make -s evals 2>&1)
STATUS=$?
if [ $STATUS -ne 0 ]; then
  echo "⛔ EVAL GATE ROUGE — corrige avant de terminer (spec.md §7 : pas d'eval verte, pas de merge)." >&2
  echo "$OUT" | tail -40 >&2
  exit 2
fi

# `make evals` masque pytest rc=5 (rien collecté) en 0 : « vert » peut vouloir dire
# « rien n'a tourné » (findings H8/M5). On le signale — NON bloquant ici : la règle dure
# « pas d'eval = pas de done » appartient à l'orchestrateur (scopé par tâche aux IDs
# réellement implémentés) ; bloquer dans ce hook générique casserait une tâche de
# scaffolding légitime sans eval encore écrite.
if command -v uv >/dev/null 2>&1; then
  COLLECTED=$(uv run pytest -m eval --collect-only -q 2>/dev/null | grep -c '::' || true)
  if [ "${COLLECTED:-0}" -eq 0 ]; then
    echo "⚠️  eval-gate : du code a changé mais AUCUNE eval n'est collectée — \`make evals\` est vert par ABSENCE, pas par succès (spec.md §7)." >&2
  fi
fi
exit 0
