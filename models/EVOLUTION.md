# Évolution des modèles — la boucle de réévaluation

Les modèles changent vite. Ce lab est conçu pour que **changer de modèle soit une
décision chiffrée, pas un réflexe** — et pour que l'arrivée d'un nouveau modèle
déclenche une réévaluation, jamais une migration à l'aveugle.

## Le principe

On évalue **trois choses distinctes** (cf. `scripts/eval_models.py`) :

1. **Scorecard** — sur des tâches-or (`evals/golden/`), le code produit passe-t-il **nos**
   evals cachées ? Mesure la capacité brute par rôle, jugée contre des références que le
   modèle n'écrit pas lui-même (équité).
2. **Comportemental** — le modèle respecte-t-il son contrat de rôle (`evals/behavioral/`) :
   scope, verdict `STATUS`, arrêt sur ambiguïté, evals d'abord, verdicts reviewer calibrés.
3. **Chaîne de commandement** — une instruction de tâche peut-elle lui faire violer une hard
   rule de `CLAUDE.md` (merger sans humain, sauter les evals, sortir du scope) ? Il doit refuser.

C'est l'application directe de l'idée du Model Spec d'OpenAI : un **contrat de comportement**
+ une **hiérarchie d'autorité**. Le Model Spec ne fournit pas de harnais ; le lab construit
celui-ci. `CLAUDE.md` (hard rules) > `.md` de rôle > prompt de tâche = notre chaîne de commandement.

## L'équité, par construction

- Mêmes fixtures, mêmes prompts, N essais par modèle (variance, pas single-shot).
- Chaque essai dans un répertoire **isolé** : aucun modèle n'hérite du travail d'un autre.
- Métriques **mesurées** (coût/latence via `claude --output-format json`), jamais déclarées.
- Tous les essais bruts tracés (`.jsonl`) → pas de cherry-pick.
- Profil de contexte **identique** (`base`) pour tous : aucun avantage de scaffolding au départ.

## La boucle, à chaque nouveau modèle Claude

1. **Ajouter au registre** — une entrée `[[model]]` dans `models/registry.toml` (id, rôles éligibles).
   Aucun code à toucher.
2. **Lancer la campagne** — `make eval-models LIVE=1` (les 3 couches, tous les modèles du registre).
   Produit un scorecard daté dans `models/scorecards/`.
3. **Comparer à l'incumbent** — le `[roles]` du registre est la ligne de base. Le nouveau
   modèle bat-il l'actuel sur sa couche, à coût acceptable ?
4. **Arbitrer l'affectation** — ne changer `[roles]` que sur preuve : meilleur taux comportemental
   ET scorecard, coût justifié. Un gain de capacité brute ne rachète JAMAIS une violation de
   chaîne de commandement (couche 3 = éliminatoire pour le rôle).
5. **Ajuster le contexte si besoin** — si un modèle rapide échoue une règle comportementale en
   profil `base`, tester `context_profile = "verbose"` et **re-mesurer** : le profil doit lever le
   score sans masquer une inaptitude de fond. Sinon, le modèle n'est pas éligible au rôle.
6. **Committer** — registre + scorecard daté. L'historique des scorecards montre la **dérive de
   capacité dans le temps** : c'est la mémoire d'évaluation du lab.

## À surveiller dans le temps

- **Régression silencieuse** : un nouveau point de version d'un modèle peut baisser un score.
  Le scorecard daté la rend visible — d'où l'intérêt de re-lancer périodiquement, pas seulement
  à l'arrivée d'un modèle.
- **Relâcher le scaffolding** : à mesure que les modèles progressent, des règles qui exigeaient un
  profil `verbose` peuvent passer en `base`. Le harnais dit quand on peut simplifier le contexte.
- **Cross-vendor** (Gemini/Vertex, cf. deck) : l'orchestrateur est Claude-only aujourd'hui
  (`claude -p` codé en dur). Comparer hors-Claude demandera un runner abstrait — backlog assumé.
