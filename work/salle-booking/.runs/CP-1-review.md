# Revue CP-1 — panel de 1 — verdict agrégé : WARN (WARN)

## Paneliste 1 — claude-opus-4-8 — angle : revue complète
VERDICT: WARN

Tout est vert (52 tests core, EVAL-2 verte, ruff clean, zéro `now()`/`datetime`). Je rédige le dossier de revue.

---

# Rapport de revue — CP-1 · salle-booking · T1

**Angle :** revue complète · **Tâches :** T1 (Domaine pur : model + store + availability + EVAL-2) · **Checkpoint :** CP-1 `mode: auto`

## ✅ Conformes

**Traçabilité**
- ✅ Commit `0236868` référence tous les IDs de T1 (`INV-1..3, BHV-1..4 + edge cases, EVAL-2`) — alignés sur `tasks.md:40`.
- ✅ Chaque BHV/INV de la tâche se retrouve dans le diff ET est testé nominativement : INV-2 `model.py:18`, INV-3 `model.py:20`, BHV-1a (demi-ouvert) `model.py:27`, INV-1 `store.py:17-19`, BHV-2b (cancelled ignoré) `store.py:43`, BHV-3a `store.py:35`, BHV-4 `availability.py:23-32`.

**Conformité design**
- ✅ ADR-1 respecté : intervalles demi-ouverts, minutes int 0..1440, chevauchement `a.start < b.end and b.start < a.end` (`model.py:27`). Adjacence `fin==début` autorisée — vérifié `test_model.py:74`.
- ✅ ADR-2 respecté : soft-delete via `status="cancelled"` (`store.py:36`), `confirmed()` filtre sur status (`store.py:42-43`).
- ✅ Contrats design §5 exacts : raisons `invalid_slot`/`too_long`/`overlap`/`not_found`, signatures `book/cancel/availability` conformes.
- ✅ Pureté déterministe (NG-1/NG-2) : zéro `now()`/`datetime`/I/O, le temps est une donnée d'entrée. EVAL-2 à seed fixe (`SEED=42`, `test_eval_2_property.py:12`).

**Scope**
- ✅ Aucun scope creep : `cli.py` (T4) et `tests/booking_evals/` (T2/T3) absents du diff, comme prévu. `files_touched` de T1 respecté à la lettre.

**Qualité**
- ✅ `ruff check` clean · 52 tests core verts · EVAL-2 collectée + verte (`-m eval`) → `done_when` de T1 satisfait.
- ✅ Pas de secret, pas de TODO orphelin, types annotés. Commit `[auto]` (généré, pas de ligne manuelle à justifier).

## ⚠️ À arbitrer par l'Owner

- ⚠️ **Logique de chevauchement dupliquée** (`store.py:18` vs `model.py:27`). Le design §1 dit que le store applique INV-1 *« en s'appuyant sur `model` »*. Or `book()` réimplémente le test inline (`existing.start < end and start < existing.end`) au lieu de réutiliser le helper `overlaps()` de `model.py`. Logiquement identique aujourd'hui, mais c'est une définition d'invariant en double : un futur changement de la règle d'adjacence dans `model.overlaps()` ne se propagerait pas au store. EVAL-2 vérifie via `overlaps()`, l'enforcement passe par la copie — les deux pourraient diverger sans qu'un test l'attrape. Arbitrage : tolérer (cohérence locale acceptable pour un cœur pur) ou demander la réutilisation du helper.

## ❌ Bloquants

- Aucun.

---

**Synthèse :** T1 est fonctionnellement complet, tracé, gaté (EVAL-2 verte) et conforme aux ADR. Le seul écart est un point de cohérence de design (DRY de la règle d'overlap) — non bloquant mais réel par rapport au texte du design. Conformément à la règle de l'agent (PASS = zéro écart ; au moindre écart sur un checkpoint `auto` → WARN, bascule en validation humaine), je ne valide pas en automatique : l'Owner tranche la duplication.

VERDICT: WARN