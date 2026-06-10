"""Présentation pure du devis (BHV-3) — aucune dépendance au module calc."""


def format_quote(quote: dict) -> str:
    """Formate un devis pour affichage client.

    `quote` respecte le contrat des Examples (design.md §5) :
    `products_eur`, `installation_eur`, `total_eur`, `is_estimate`.
    """
    return "\n".join(
        [
            "Devis de pose — estimation non contractuelle",
            f"Produits : {quote['products_eur']:.2f} EUR",
            f"Pose : {quote['installation_eur']:.2f} EUR",
            f"Total : {quote['total_eur']:.2f} EUR",
        ]
    )
