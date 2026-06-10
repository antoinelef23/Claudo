#!/usr/bin/env bash
# Hook PostToolUse (Edit|Write) — lint rapide non bloquant sur les fichiers Python modifiés.
# Reçoit le JSON de l'événement sur stdin. Sort toujours en 0 (informatif, jamais bloquant).
set -uo pipefail

INPUT=$(cat)
FILE=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)

case "$FILE" in
  *.py)
    if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
      uv run ruff check --fix "$FILE" >&2 || true
      uv run ruff format "$FILE" >&2 || true
    fi
    ;;
esac
exit 0
