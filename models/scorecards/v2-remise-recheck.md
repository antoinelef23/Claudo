# Scorecard modèles — v2-remise-recheck

> Généré par `scripts/eval_models.py`. Métriques mesurées, essais bruts dans le `.jsonl`.
> Équité : mêmes fixtures/prompts, essais isolés, scorecard jugée contre nos evals cachées.

| Modèle | Rôle | Couche | n | Taux passage | Coût moy. $ | Latence moy. s |
|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | implementer | scorecard | 3 | 100% (3/3) | 0.0732 | 41.7 |
| claude-opus-4-8 | implementer | scorecard | 3 | 100% (3/3) | 0.4293 | 69.7 |
| claude-sonnet-4-6 | implementer | scorecard | 3 | 67% (2/3) | 0.1423 | 43.1 |

## Recommandation par rôle

- **implementer** → `claude-haiku-4-5-20251001` (taux global 100%, coût 0.0732$)
