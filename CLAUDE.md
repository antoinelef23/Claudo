# CLAUDE.md — Lab IA-natif

## Context

Lab IA-natif : workflow de développement agentique, réutilisable sur n'importe quel projet. On recrée des applications depuis zéro : un Owner unique pilote, les agents codent, l'humain valide. Toute ligne de code écrite à la main est une exception justifiée dans le commit. Les spécificités d'une organisation (design system, référentiel de conformité, repos de référence) ne sont JAMAIS codées en dur dans le workflow : elles se déclarent par feature, dans son `design.md`.

## The 3 artifacts — source of truth

Chaque unité de travail vit dans `work/<feature>/` avec trois fichiers :

1. **`spec.md`** — le QUOI. Contrat métier : invariants, comportements, exemples, evals. C'est le prompt principal de tout agent qui code. **Ne jamais implémenter quelque chose d'absent de la spec.** Si la spec est ambiguë : poser la question, ne pas deviner.
2. **`design.md`** — le COMMENT. Stack, ADRs, repos de référence, intégration au design system du projet, conformité au référentiel applicable. **Tout choix technique doit pointer vers un pattern d'un repo de référence** (repo interne de l'organisation ou open source). *(Le design system et le référentiel de conformité sont propres à chaque organisation : ils se renseignent dans design.md §6, jamais en dur dans le cœur.)*
3. **`tasks.md`** — le DO. Plan d'exécution généré par l'agent, validé par l'Owner. Séquence via `depends_on`, parallélisme via `parallel_group`, checkpoints humains explicites.

Ordre de lecture obligatoire avant de coder : spec.md → design.md → tasks.md.

## Hard rules

- **Eval gate** : pas d'eval verte, pas de merge. Les evals sont définies dans spec.md (section Evals) et exécutables via `make evals`.
- **Checkpoint humain** : ne jamais exécuter un plan (tasks.md) sans validation explicite de l'Owner. Ne jamais merger, déployer, ou supprimer des données sans accord humain. Un checkpoint peut être `mode: auto` (auto-validé si evals vertes + reviewer PASS) — mais ce choix appartient à l'Owner au moment d'approuver le plan, et le checkpoint final (merge) est toujours humain.
- **Traçabilité** : chaque commit référence les IDs de la spec qu'il implémente (ex: `feat: matching produits [BHV-3, INV-2]`).
- **Design ancré** : ne jamais inventer une architecture. S'adosser aux repos de référence listés dans design.md §2. Si aucun pattern de référence ne couvre le besoin, le signaler dans une ADR plutôt qu'improviser.
- **Règles d'ingénierie & déploiement** : tout agent applique le standard de développement `docs/engineering-rules.md` (règles **R-n** : cœur pur, ports & adapters, déterminisme par injection, no-op sur états terminaux, evals qui exercent les ré-invocations…) ; pour une feature qui se déploie, le standard `docs/gcp-deployment-standard.md` (règles **D-n** : Cloud Run, WIF, Secret Manager, CI signée, SLO, rollout canary, prod = décision humaine), renseigné dans `design.md §7`. Le `reviewer` vérifie R-n/D-n au checkpoint ; une feature pure note `§7 N/A`.
- **Spec immuable en cours de tâche** : si l'implémentation révèle un trou dans la spec, on arrête, on amende la spec (commit séparé), puis on reprend.
- **Amendement = passe de cohérence** : tout amendement de spec impose de mettre à jour les pointeurs `# version :` de design.md/tasks.md et de relire les docs dépendants (une note rédigée avant l'amendement peut être devenue fausse). Le plan-lint signale la dérive de version.
- **Forme adaptable, fond sacré** : le FOND de spec.md (contrat métier) et design.md (image technique) ne change que par amendement humain (commit séparé + bump `version:`). La FORME peut évoluer librement, y compris pour qu'un autre modèle comprenne mieux. `scripts/content_guard.py` (`make check-content`) rend la règle mécanique : un reformat qui altère le fond sans bump de version est rejeté. Pour aider un modèle qui comprend mal : ajuster d'ABORD le scaffolding (`models/profiles/`, agent `.md`), reformater spec/design en DERNIER recours seulement.
- **Agents vivants** : les agents `.md` sont versionnés et évoluent à la vitesse des modèles — mais jamais en silence. Tout changement passe la boucle « évals → patch scaffolding → vérification (lève un score sans en régresser) → bump de version » (models/EVOLUTION.md). Un échec de chaîne de commandement est éliminatoire : on n'y remédie pas par du prompt.

## Conventions

- Python 3.12+, `uv` pour les dépendances, `ruff` pour lint/format, `pytest` pour les tests, `pytest -m eval` pour les evals.
- FastAPI pour les services, Pydantic v2 pour les contrats de données.
- Markdown + Git pour tout artefact. Pas de Confluence, pas de Jira : le repo est la mémoire.
- Langue : contenu métier en français, identifiants/code/sections structurantes en anglais.

## Vocabulary (ubiquitous language)

| Terme | Définition |
|---|---|
| Owner | Rôle unique qui pilote l'app (rotation 2 semaines, pool 3-5) |
| FDE | Forward Deployment Engineer — fait vivre l'architecture agentique |
| PE | Product Engineer — fait vivre les 3 artefacts, anime les Vibe Workshops |
| Vibe Workshop | Atelier 105 min qui produit spec.md v1.0 |
| Eval | Test exécutable dérivé de la spec, condition de merge |
| Design system | Le design system du projet — propre à l'organisation, déclaré dans design.md §6 |
| Référentiel de conformité | Le standard de conformité/accessibilité applicable — déclaré dans design.md §6 |

## Agents

Sous-agents disponibles dans `.claude/agents/` : `design-scout`, `planner`, `implementer`, `eval-runner`, `reviewer`. Leur orchestration est décrite dans README.md et dans chaque tasks.md.

## Modèles

L'affectation modèle ↔ rôle vit dans `models/registry.toml` (source de vérité data-driven), surchargeable par tâche via `**model :**`. On ne change l'affectation de production (`[roles]`) que sur preuve chiffrée du harnais `scripts/eval_models.py` (scorecard + comportemental + chaîne de commandement). Une violation de chaîne de commandement est éliminatoire pour le rôle, quel que soit le score brut. Boucle de réévaluation à chaque nouveau modèle : `models/EVOLUTION.md`.
