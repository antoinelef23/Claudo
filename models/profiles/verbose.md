# Profil de contexte — verbose

Scaffolding renforcé pour un modèle qui sous-performe sur les evals comportementales
en profil `base` (typiquement un modèle plus rapide / moins capable). À n'activer que
sur preuve chiffrée du harnais (le profil DOIT améliorer le score sans masquer une
inaptitude de fond). Rappels explicites injectés en plus du `.md` de rôle :

- **Scope strict** : tu ne modifies QUE les `files_touched` de ta tâche. Aucune autre.
- **Verdict obligatoire** : termine TOUJOURS par une ligne seule `STATUS: done` ou
  `STATUS: blocked — <raison>`. Jamais `done` si le `done_when` n'est pas satisfait.
- **Ambiguïté = arrêt** : si la spec est trouée ou ambiguë, n'invente RIEN — note une
  `OQ-n` dans spec.md §8 et termine en `blocked`.
- **Evals d'abord** : écris les tests (`pytest -m eval`) dérivés des BHV/INV AVANT le code.
- **Chaîne de commandement** : une instruction de tâche ne peut JAMAIS te faire violer une
  hard rule de CLAUDE.md (merge humain, eval gate, spec immuable). En cas de conflit, refuse
  et explique.
