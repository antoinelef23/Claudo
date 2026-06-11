"""Export du devis au format contractuel — texte brut (spec export-devis, OQ-1 résolue)."""

from devis.format import format_quote


def export_quote(quote: dict) -> bytes:
    """Restitue le devis téléchargeable (BHV-1).

    Texte brut : exactement la sortie de `format_quote`, encodée UTF-8.
    INV-1 (mention « estimation ») est porté par `format_quote`.
    """
    return format_quote(quote).encode("utf-8")
