# Usage — Export du devis (`src/devis/export.py`)

> Feature `export-devis` — spec v1.0.0 (OQ-1 résolue : export **texte brut**, PDF en phase 2).

## Fonction

```python
from devis.export import export_quote

payload: bytes = export_quote(quote)
```

`export_quote(quote: dict) -> bytes` restitue le devis téléchargeable (BHV-1) :
exactement la sortie de `format_quote`, encodée UTF-8. Fonction pure, sans effet de bord
(socle devis-pose, ADR-1).

## Contrat d'entrée

`quote` suit le contrat des Examples de devis-pose :

| Clé | Type | Exemple |
|---|---|---|
| `products_eur` | float | `2375.00` |
| `installation_eur` | float | `900.00` |
| `total_eur` | float | `3275.00` |
| `is_estimate` | bool | `true` |

## Sortie

Texte brut UTF-8, une ligne d'en-tête puis les lignes Produits / Pose / Total :

```
Devis de pose — estimation non contractuelle
Produits : 2375.00 EUR
Pose : 900.00 EUR
Total : 3275.00 EUR
```

- La mention « estimation » est toujours présente (INV-1, portée par `format_quote`).
- Devis sans pose (surface 0) : export valide, ligne `Pose : 0.00 EUR` (BHV-1a).

## Hors scope

- Envoi par e-mail (NG-1).
- Format PDF/CSV : phase 2 (cf. résolution OQ-1 dans spec.md §8).

## Vérification

```sh
uv run pytest -q tests/devis_export          # tests + eval EVAL-1
```
