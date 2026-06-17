#!/usr/bin/env python3
"""Jetons d'approbation signés (HMAC) — empêche un agent de forger sa propre
validation de checkpoint. Le merge est humain, toujours (CLAUDE.md, hard rules).

Modèle de menace fermé ici (finding H1) : un agent (Write/Edit en acceptEdits, ou
Bash) qui dépose lui-même `feature/.approvals/<CP>` pour s'auto-valider. Avant, le
gate se réduisait à `approval.exists()` — falsifiable d'un seul `Write`.

- Sans LAB_APPROVAL_SECRET : mode rétro-compatible. Un jeton non signé est accepté
  AVEC avertissement (la forge n'est PAS bloquée — configure le secret).
- Avec LAB_APPROVAL_SECRET : un jeton sans signature HMAC valide est REJETÉ. Un
  agent ne peut donc pas se valider sans le secret, que l'orchestrateur retire de
  l'environnement des sous-agents (cf. orchestrate.run_claude).

Résiduel connu (finding M4) : tant que les agents tournent sur le même hôte SANS
sandbox, un agent disposant d'exécution de code arbitraire (inhérente à un agent
qui lance ses tests) pourrait exfiltrer le secret depuis les dotfiles de l'Owner.
Le confinement complet passe par le sandbox (branche ship/portable-sandbox). Ici
on ferme la forge naïve / par-outil et on lie le jeton au checkpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
from pathlib import Path

ENV_SECRET = "LAB_APPROVAL_SECRET"


def _secret() -> bytes | None:
    # Un secret vide OU uniquement blanc est traité comme absent (entropie nulle) :
    # pas de fausse impression de sécurité avec LAB_APPROVAL_SECRET="   ".
    s = (os.environ.get(ENV_SECRET) or "").strip()
    return s.encode() if s else None


def _feature_id(feature: Path) -> str:
    # parent/name (ex. work/feat) plutôt que le seul basename — évite une collision
    # de jeton entre work/x et examples/x. Stable entre approve.sh et l'orchestrateur
    # (tous deux résolvent le chemin avant d'appeler).
    return f"{feature.parent.name}/{feature.name}"


def _payload(feature: Path, cp_id: str) -> str:
    # Lié au checkpoint et à la feature — PAS au contenu de tasks.md (muté par
    # run_log pendant le run, ce qui invaliderait un jeton légitime). La fraîcheur
    # (anti-rejeu, finding H4) est assurée par la consommation du jeton après
    # honoration côté orchestrateur (wait_checkpoint) + le gitignore de .approvals.
    return f"{cp_id}|{_feature_id(feature)}"


def sign(feature: Path, cp_id: str, author: str, ts: str) -> str:
    lines = [
        f"approved_by={author}",
        f"at={ts}",
        f"payload={_payload(feature, cp_id)}",
    ]
    sec = _secret()
    if sec:
        sig = hmac.new(
            sec, _payload(feature, cp_id).encode(), hashlib.sha256
        ).hexdigest()
        lines.append(f"sig={sig}")
    return "\n".join(lines) + "\n"


def _fields(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in content.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def verify(feature: Path, cp_id: str, content: str) -> tuple[bool, str]:
    """(accepté, motif). Refuse un jeton signé invalide ; accepte (avec
    avertissement) un jeton non signé seulement si aucun secret n'est configuré."""
    sec = _secret()
    if sec is None:
        return (
            True,
            "non signé (LAB_APPROVAL_SECRET absent — forge non bloquée, "
            "configure le secret pour durcir le checkpoint)",
        )
    sig = _fields(content).get("sig")
    if not sig:
        return (
            False,
            "jeton sans signature alors que LAB_APPROVAL_SECRET est défini "
            "(forge probable par un agent)",
        )
    expected = hmac.new(
        sec, _payload(feature, cp_id).encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return (
            False,
            "signature invalide (jeton forgé ou checkpoint/feature incohérent)",
        )
    return True, "signature valide"


def _cli(argv: list[str]) -> int:
    """Usage interne pour approve.sh : approvals.py sign <CP> <feature_dir> <author>."""
    if len(argv) >= 4 and argv[0] == "sign":
        from datetime import datetime

        cp, feature_dir, author = argv[1], argv[2], argv[3]
        feature = Path(feature_dir).resolve()
        d = feature / ".approvals"
        d.mkdir(parents=True, exist_ok=True)
        (d / cp).write_text(
            sign(feature, cp, author, datetime.now().isoformat(timespec="seconds")),
            encoding="utf-8",
        )
        if _secret() is None:
            print(
                "⚠️  LAB_APPROVAL_SECRET non défini : jeton NON signé (un agent "
                "pourrait le forger). Exporte le secret pour durcir.",
                file=sys.stderr,
            )
        return 0
    print("usage: approvals.py sign <CP> <feature_dir> <author>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
