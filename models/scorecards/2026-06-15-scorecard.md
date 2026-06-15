# Scorecard modèles — 2026-06-15-scorecard

> Généré par `scripts/eval_models.py`. Métriques mesurées, essais bruts dans le `.jsonl`.
> Équité : mêmes fixtures/prompts, essais isolés, scorecard jugée contre nos evals cachées.

| Modèle | Rôle | Couche | n | Taux passage | Coût moy. $ | Latence moy. s |
|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | implementer | scorecard | 3 | 100% (3/3) | 0.0701 | 37.1 |
| claude-opus-4-8 | implementer | scorecard | 3 | 100% (3/3) | 0.2852 | 36.6 |
| claude-sonnet-4-6 | implementer | scorecard | 3 | 100% (3/3) | 0.1818 | 53.7 |

## Recommandation par rôle

- **implementer** → `claude-haiku-4-5-20251001` (taux global 100%, coût 0.0701$)
