"""EVAL-3 — formatage client (BHV-3) sur les données d'EX-2."""

import pytest

from devis.format import format_quote

# Dict conforme au contrat design.md §5 (clés des Examples), valeurs d'EX-2.
EX2_QUOTE = {
    "products_eur": 2375.00,
    "installation_eur": 900.00,
    "total_eur": 3275.00,
    "is_estimate": True,
}


@pytest.mark.eval
def test_eval_3_format_ex2():
    texte = format_quote(EX2_QUOTE)

    # BHV-3 : mention « estimation »
    assert "estimation" in texte.lower()

    # BHV-3 : total en euros avec exactement 2 décimales
    assert "3275.00" in texte

    # BHV-3 : détail produits / pose sur des lignes séparées
    lignes = texte.splitlines()
    lignes_produits = [l for l in lignes if "2375.00" in l]
    lignes_pose = [l for l in lignes if "900.00" in l]
    assert len(lignes_produits) == 1
    assert len(lignes_pose) == 1
    assert lignes_produits[0] != lignes_pose[0]
