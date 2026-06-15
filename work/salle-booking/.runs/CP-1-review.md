# Revue CP-1 — panel de 1 — verdict agrégé : PASS (PASS)

## Paneliste 1 — claude-opus-4-8 — angle : revue complète
VERDICT: PASS

Toutes les vérifications mécaniques passent. Je rédige le rapport de revue.

---

# Rapport de revue — CP-1 · vertical slice du domaine (salle-booking)

**Tâches couvertes :** T1 — Domaine pur `model` + `store` + `availability` (+ EVAL-2)
**Angle :** revue complète · **Mode checkpoint :** auto

## ✅ Conforme

**Traçabilité**
- ✅ Les deux commits T1 référencent des IDs de spec valides — `f2debb2` porte `[INV-1, INV-2, INV-3, BHV-1, BHV-1a/b/c, BHV-2, BHV-2a/b, BHV-3, BHV-3a, BHV-4, EVAL-2]`, exactement le `implements:` de la tâche (`tasks.md:40`).
- ✅ Le commit de correction `a30e59c` trace le motif du rejet CP-1 précédent : `store.book() délègue INV-1 à model.overlaps() [INV-1, BHV-2…]`.
- ✅ Chaque BHV/INV de la tâche se retrouve dans un test nommé : `test_model.py`, `test_store.py`, `test_availability.py` couvrent INV-2/INV-3/BHV-1..4 par nom explicite ; EVAL-2 dans `test_eval_2_property.py:16`.

**Reprise sur rejet (audit du cycle CP-1)**
- ✅ Le rejet précédent (« réutilise `model.overlaps()` au lieu de réimplémenter le chevauchement inline », `tasks.md:150`) est **effectivement corrigé** : `store.py:27` appelle `overlaps(existing, candidate)` importé de `model` (`store.py:5`). Une seule définition de l'invariant — enforcement et EVAL-2 partagent `overlaps()`, plus de risque de divergence.

**Conformité design**
- ✅ ADR-1 (intervalles demi-ouverts, minutes int) : `overlaps` = `a.start < b.end and b.start < a.end` (`model.py:27`), adjacence `fin==début` autorisée — testée `test_model.py:74`, `test_availability.py:66`.
- ✅ ADR-2 (soft-delete) : `cancel` passe `status="cancelled"` (`store.py:37`) ; `confirmed()` filtre sur `status=="confirmed"` (`store.py:44`) → annulée ignorée pour overlap (`test_store.py:57`) et availability (`test_availability.py:58`).
- ✅ Contrats design §5 respectés à l'identique : `book → {"status":"confirmed","id":…}` / `{"rejected":<raison>}`, raisons `invalid_slot|too_long|overlap` ; `cancel → {"status":"cancelled"}|{"rejected":"not_found"}` ; `availability → list[tuple[int,int]]`.
- ✅ Pureté : aucun `now()`/`datetime`/I/O, temps en entrée, stdlib uniquement (NG-1/NG-2 respectés).

**Scope**
- ✅ Diff strictement dans le périmètre — `src/booking/` + `tests/booking_core/` + artefacts/`.runs`. Aucun fichier hors scope touché (vérifié vs base de merge `b4f4492`). EVAL-1/EVAL-3/CLI bien absentes (réservées T2/T3/T4).

**Qualité / evals**
- ✅ `pytest tests/booking_core` : **52 passed**. `-m eval` : **1 passed** (EVAL-2, 500 séquences seed=42). `done_when` de T1 satisfait.
- ✅ `ruff check src/booking tests/booking_core` : All checks passed.
- ✅ Types annotés, pas de secret, pas de TODO orphelin. Code `[auto]` — aucune ligne manuelle à justifier.

## ⚠️ Observations (non bloquantes, hors scope T1)

- ⚠️ **Forme du contrat `availability`** : la fonction retourne des `tuple` (`availability.py:14`, conforme design §5 `list[tuple[int,int]]`), alors que spec EX-4 (`spec.md:101`) écrit les gaps en listes `[[480,540],…]`. Source du métier = YAML d'exemple ; le design tranche en `tuple`. À cadrer dans EVAL-1 (T2) pour que la comparaison soit explicite — pas un défaut de T1.
- ⚠️ **Fenêtre `availability` inversée non spécifiée** : `availability(store, room, ws, we)` avec `ws ≥ we` renvoie `[]` silencieusement. BHV-4 suppose une fenêtre valide ; aucun invariant ne le couvre. À noter comme angle mort éventuel pour une future spec, sans impact ici.

## ❌ Bloquants

Aucun.

---

Checkpoint `mode: auto` : EVAL-2 verte, reviewer sans écart bloquant, rejet précédent corrigé, scope propre, design respecté. Les deux ⚠️ sont des points d'attention pour T2, pas des écarts sur T1.

VERDICT: PASS