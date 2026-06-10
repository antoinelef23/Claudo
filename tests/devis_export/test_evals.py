"""EVAL-1 — export texte brut (BHV-1, INV-1) sur les données d'EX-1."""

import pytest

from devis.export import export_quote

# Dict conforme au contrat design.md §5 de devis-pose, valeurs d'EX-1.
EX1_QUOTE = {
    "products_eur": 2375.00,
    "installation_eur": 900.00,
    "total_eur": 3275.00,
    "is_estimate": True,
}


@pytest.mark.eval
def test_eval_1_export_ex1():
    export = export_quote(EX1_QUOTE)

    # BHV-1 : texte brut encodé UTF-8
    assert isinstance(export, bytes)
    texte = export.decode("utf-8")

    # INV-1 : mention « estimation »
    assert "estimation" in texte.lower()

    # EX-1 : total avec exactement 2 décimales
    assert "3275.00" in texte

    # EX-1 : lignes Produits / Pose distinctes
    lignes = texte.splitlines()
    lignes_produits = [ligne for ligne in lignes if ligne.startswith("Produits")]
    lignes_pose = [ligne for ligne in lignes if ligne.startswith("Pose")]
    assert len(lignes_produits) == 1
    assert len(lignes_pose) == 1
    assert lignes_produits[0] != lignes_pose[0]
