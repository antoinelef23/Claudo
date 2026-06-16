"""Tests T7 — CLI de démo manuelle (src/webhooks/cli.py).

Scope : scénario succès → DELIVERED ; scénario échec persistant → DEAD_LETTER.
Pas d'eval ici (done_when tasks.md T7).
"""

import pytest

from webhooks.cli import run, main
from webhooks.model import DELIVERED, DEAD_LETTER


def test_cli_success_immediate():
    """Transport répond True au 1er appel → DELIVERED, 1 appel. (BHV-1)"""
    delivery, transport = run(results=[True], max_attempts=3)
    assert delivery.state == DELIVERED
    assert len(transport.calls) == 1


def test_cli_dead_letter_persistent():
    """Transport toujours False → DEAD_LETTER, exactement max_attempts appels. (BHV-3)"""
    delivery, transport = run(results=[False, False, False], max_attempts=3)
    assert delivery.state == DEAD_LETTER
    assert len(transport.calls) == 3


def test_cli_success_after_failures():
    """Echec puis succès → DELIVERED, 2 appels. (BHV-2)"""
    delivery, transport = run(results=[False, True], max_attempts=5)
    assert delivery.state == DELIVERED
    assert len(transport.calls) == 2


def test_cli_max_attempts_bounds_calls():
    """Même si results fournis sont plus nombreux, appels bornés à max_attempts. (INV-2)"""
    delivery, transport = run(results=[False] * 10, max_attempts=4)
    assert delivery.state == DEAD_LETTER
    assert len(transport.calls) == 4


def test_cli_main_help(capsys):
    """--help ne lève pas d'exception (exit 0)."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_cli_main_success_output(capsys):
    """main() affiche état final et nombre d'appels sur stdout."""
    main(["--results", "T"])
    out = capsys.readouterr().out
    assert DELIVERED in out
    assert "1" in out


def test_cli_main_dead_letter_output(capsys):
    """main() affiche DEAD_LETTER quand tous les résultats sont F."""
    main(["--results", "F", "F", "--max-attempts", "2"])
    out = capsys.readouterr().out
    assert DEAD_LETTER in out
    assert "2" in out
