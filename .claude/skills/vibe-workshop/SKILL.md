---
name: vibe-workshop
description: Anime le Vibe Workshop (105 min, 6-8 personnes) qui produit spec.md v1.0. Utiliser quand le PE lance un atelier de spec avec le métier — Claude médie en partage d'écran et rédige la spec en direct.
---

# Vibe Workshop — la fabrique de la spec

Tu médies l'atelier en partage d'écran. Le métier parle, tu structures en direct dans le format templates/spec.md. Objectif de sortie : spec.md v1.0 commitée.

## Déroulé (105 min)
1. **Pitch d'intention métier (15 min)** → §1 Intent + KPI cible. Reformule jusqu'à accord explicite.
2. **Event Storming digital (30 min)** → événements métier, acteurs, commandes. Alimente §2 Glossary (exige un nom canonique par terme) et la liste brute des BHV.
3. **Sweep d'invariants & cas limites (25 min)** → « qu'est-ce qui ne doit JAMAIS arriver ? » → §3 INV-n. Puis pour chaque BHV : « et si… ? » → edge cases BHV-na, nb…
4. **Galerie d'exemples (25 min)** → §5. Données réalistes exigées (vrais produits, vrais montants). Chaque exemple tague ce qu'il couvre. En cas de désaccord prose/exemple : l'exemple gagne.
5. **Clôture (10 min)** → relecture des OQ-n restantes, proposition d'evals (§7) dérivées des exemples, commit `spec.md v1.0` + tag.

## Règles d'animation
- Bannis les mots flous : « rapide », « pertinent », « simple » → exige un chiffre ou un exemple.
- Une question à la fois, jamais de jargon technique avec le métier.
- Tout désaccord non tranché en séance devient une OQ-n, pas un compromis mou.
- Le métier valide à l'écran section par section : la spec est SON contrat.
