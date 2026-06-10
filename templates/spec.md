---
artifact: spec
feature: <slug-de-la-feature>
version: 0.1.0
status: draft            # draft | validated | superseded
owner: <nom de l'Owner courant>
validated_by: <métier — nom + date, vide tant que draft>
---

# Spec — <Nom de la feature>

> **Le QUOI. Le contrat du métier.** Ce fichier est le prompt principal de tout agent qui code.
> Règles d'or pour être parfaitement compris d'une IA :
> 1. Chaque affirmation est **testable** et porte un **ID stable** (INV-n, BHV-n, EX-n, EVAL-n) — jamais réutilisé, jamais renuméroté.
> 2. Zéro ambiguïté : « rapide », « simple », « pertinent » sont interdits sans chiffre.
> 3. Les exemples concrets priment sur la prose : en cas de conflit prose/exemple, **l'exemple gagne** et la prose doit être corrigée.
> 4. Ce qui n'est pas dans la spec n'existe pas. Ce qui est hors scope est dit explicitement (§6).

## 1. Intent

*2 à 5 phrases. Pourquoi cette feature existe, pour qui, et quel KPI business elle bouge. C'est la section que l'agent relit quand il doit arbitrer.*

**KPI cible :** <métrique, valeur actuelle → valeur visée, horizon>

## 2. Glossary

*Vocabulaire métier exact. L'agent DOIT utiliser ces termes dans le code (noms de classes, champs, events). Un terme = une définition = un nom canonique en anglais pour le code.*

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| <terme> | `<snake_case>` | <définition sans ambiguïté> |

## 3. Invariants

*Les règles toujours vraies, quoi qu'il arrive. Chaque invariant est vérifiable par un test. Format : MUST / MUST NOT.*

- **INV-1** — <Le système MUST ... / MUST NOT ...>
- **INV-2** — ...

## 4. Behaviors

*Comportements attendus, format Given/When/Then. Un BHV = un comportement observable, pas une étape technique.*

### BHV-1 — <titre court>
- **Given** <état initial précis>
- **When** <action de l'utilisateur ou événement>
- **Then** <résultat observable, avec valeurs>
- **Edge cases :** <liste numérotée BHV-1a, BHV-1b… avec le comportement attendu pour chacun>

## 5. Examples

*Galerie d'exemples concrets entrée → sortie, issus du Vibe Workshop. Données réalistes, pas de foo/bar. C'est la section la plus lue par les agents.*

### EX-1 — <cas nominal>
```yaml
input:
  <champ>: <valeur réaliste>
expected_output:
  <champ>: <valeur exacte attendue>
covers: [BHV-1, INV-2]
```

### EX-2 — <cas limite>
...

## 6. Non-goals

*Ce que cette feature NE fait PAS, même si ça semble proche. Empêche l'agent d'halluciner du scope.*

- **NG-1** — <hors scope + pourquoi / où c'est traité>

## 7. Evals — merge gate

*Chaque eval est exécutable (`pytest -m eval`). Pas d'eval verte, pas de merge. Une eval référence les BHV/INV qu'elle couvre. Tout BHV et tout INV doit être couvert par au moins une eval.*

*Convention exécutable : une eval = un test pytest marqué `@pytest.mark.eval` dont le nom contient l'ID en minuscules (ex. `test_eval_1_matching_exact`). C'est ce qui permet à l'orchestrateur de vérifier mécaniquement qu'une eval existe (anti-gate-vide : un `make evals` vert avec zéro eval collectée ne valide RIEN) et, à terme, la couverture eval ↔ spec.*

| ID | Type | Description | Couvre | Seuil de succès |
|---|---|---|---|---|
| EVAL-1 | deterministic | <test exact entrée/sortie> | BHV-1, INV-1 | 100 % |
| EVAL-2 | llm-judge | <critère de qualité jugé par LLM, rubrique en annexe> | BHV-2 | ≥ <n>/10 sur <m> cas |
| EVAL-3 | property-based | <propriété vérifiée sur données générées> | INV-2 | 100 % |

## 8. Open questions

*Questions sans réponse. Un agent qui rencontre une OQ s'arrête et demande — il ne devine pas.*

- **OQ-1** — <question> → *(résolue le <date> : <réponse>, intégrée en BHV-n)*

## 9. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 0.1.0 | <date> | Vibe Workshop | Création — spec v1 commitée |
