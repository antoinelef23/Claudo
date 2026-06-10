"""Test non-eval du CLI devis — sortie sur EX-1 (spec devis-pose §5)."""

from devis.cli import main


def test_cli_ex1_nominal(capsys):
    # EX-1 : products 1500.00, surface 10 → produits 1500.00, pose 450.00, total 1950.00
    main(["--products-eur", "1500.00", "--surface-m2", "10"])
    out = capsys.readouterr().out

    assert "estimation" in out
    assert "1500.00" in out
    assert "450.00" in out
    assert "1950.00" in out
    # BHV-3 : détail produits / pose sur des lignes séparées
    lines = out.splitlines()
    assert any("Produits" in line for line in lines)
    assert any("Pose" in line for line in lines)
