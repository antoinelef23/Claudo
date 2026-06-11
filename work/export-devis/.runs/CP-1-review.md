Toutes les vérifications exécutables sont passées. Voici le rapport de revue.

---

# Rapport de revue — export-devis · CP-1 (revue finale, tâches T1 & T3)

**Périmètre revu :** diff complet `main..test/simulation-devis-pose` pour la feature export-devis (commits `6518e36` → `5127412`), incluant le livrable T2 dont T3 dépend.

## ✅ Points conformes

- **Traçabilité commits → spec** : `020b0b7` référence `[BHV-1, INV-1, EVAL-1]`, les commits doc référencent `[doc]`, l'amendement de spec est un commit séparé `e1d3099` conformément à la règle « spec immuable en cours de tâche ». Le confinement a fonctionné comme prévu : T2 s'est bloqué sur OQ-1 (run log `work/export-devis/tasks.md:65`), la spec a été amendée en v1.0.0, puis T2 a repris — c'est exactement le comportement attendu par la simulation.
- **Couverture spec ↔ code** : BHV-1 (`src/devis/export.py:12` — exactement `format_quote` encodé UTF-8), INV-1 porté par `format_quote` et vérifié (`tests/devis_export/test_evals.py:25`), BHV-1a testé (`tests/devis_export/test_export.py:19`), EX-1 fidèlement repris comme fixture.
- **Eval gate** : EVAL-1 verte — `uv run pytest -q tests/devis_export` : 3 passed ; `pytest -m eval` : 1 passed. Seuil 100 % atteint.
- **Conformité design** : fonction pure sans effet de bord (ADR-1 du socle devis-pose), module à l'emplacement prévu `src/devis/export.py`, réutilisation de `format_quote` sans duplication.
- **Verify des tâches** : T1 `grep -q "OQ-1" docs/export-notes.md` OK ; T3 `test -f docs/export-usage.md` OK. La doc d'usage (`docs/export-usage.md:33-37`) reproduit exactement la sortie réelle de `format_quote` — vérifié contre `src/devis/format.py:12-15`.
- **Scope** : rien dans le diff hors spec ; NG-1 (e-mail) explicitement exclu dans la doc. Aucun scope creep.
- **Qualité** : ruff check et format propres (4 fichiers), aucun TODO orphelin, aucun secret, aucune ligne écrite à la main non justifiée.

## ⚠️ Écarts à arbitrer

1. **Pointeurs de version périmés** — `work/export-devis/design.md:8` et `work/export-devis/tasks.md:8` référencent encore `spec v0.9.0` alors que la spec est en v1.0.0 depuis l'amendement OQ-1. Le design (v0.9.0) dit aussi « une fois OQ-1 tranchée » (`design.md:14`) sans avoir été révisé après la résolution. Traçabilité inter-artefacts à remettre à jour.
2. **`docs/export-notes.md` obsolète** — la note T1 affirme « OQ-1 reste ouverte » (`docs/export-notes.md:2`), ce qui contredit la spec v1.0.0. C'était vrai au moment de T1 (parallélisme voulu), mais le doc livré sur main sera faux. À archiver ou annoter avec la résolution.
3. **État de run non commité** — `work/export-devis/.runs/state.json` modifié en working tree (T3 `pending` → `done`) alors que CP-1 est en cours. Hygiène d'orchestration : à commiter avec la validation du checkpoint.
4. **Run log incomplet** — colonne `Commit` vide pour toutes les entrées du run log (`tasks.md:63-68`), alors que les commits existent. Mineur, mais c'est la mémoire du repo.

## ❌ Bloquants

Aucun.

---

Les quatre écarts sont documentaires/hygiène, sans impact sur le code livré ni sur l'eval gate (verte). L'Owner décide : ils peuvent être corrigés dans un commit de clôture du checkpoint.

VERDICT: WARN
