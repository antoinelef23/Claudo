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

## Forme vs fond — adapter sans jamais altérer le contrat

Trois niveaux de mutabilité, par ordre de sacralité :

1. **Fond de spec.md / design.md** = SACRÉ. La spec est le contrat du métier, le design l'image
   technique de l'entreprise. Le contenu ne change QUE par **amendement humain explicite** :
   commit séparé + **bump de `version:`** + changelog. Jamais un agent, jamais « en passant ».
2. **Forme de spec.md / design.md** = LIBRE. Mise en page, table↔liste, gras, ordre des sections,
   reformulation de prose — notamment pour qu'un **autre modèle comprenne mieux** le contrat. Mais
   un reformat ne doit JAMAIS toucher le fond.
3. **Scaffolding** (agents `.md`, `CLAUDE.md`, `models/profiles/`) = VIVANT. C'est *là* qu'on adapte
   la compréhension des modèles (cf. section suivante).

**Le garde-fou mécanique : `scripts/content_guard.py`.** Il extrait une *empreinte de fond*
(assertions par ID INV/BHV/EX/EVAL/NG/OQ/ADR + noms canoniques du glossaire + KPI), normalisée pour
ignorer la forme. Règle appliquée (`make check-content FEATURE=…`) :

- reformat (fond identique) → ✅, la forme est libre ;
- fond modifié **avec** bump de version → ✅, amendement assumé ;
- fond modifié **sans** bump de version → ⛔ rejet (« amendement déguisé en reformat »).

C'est ce qui rend la règle « on adapte la forme, jamais le fond » **impossible à violer par accident**,
y compris quand on reformate une spec pour aider un modèle qui la comprend mal. Le guard est
**conservateur** : au moindre doute (même un signe de ponctuation), il flague pour confirmation humaine —
un faux positif coûte une relecture, un faux négatif laisse filer une dérive de contrat.

**Ordre d'intervention pour aider un modèle qui comprend mal le contrat :**
1. ajuster son **profil de contexte** (`models/profiles/`) — ajoute des consignes de lecture, ne touche rien ;
2. renforcer l'**agent `.md`** du rôle — le contrat de comportement, pas le contrat métier ;
3. en **dernier recours**, reformater spec/design — sous `content_guard`, fond prouvé identique.

## Agents vivants — la boucle évals → scaffolding

Les agents doivent évoluer **à la vitesse des modèles**. Mais « vivant » ne veut pas dire « muté en
silence » : un agent est versionné (`version:` + changelog dans son frontmatter) et **ne change que sur
preuve**, exactement comme le code ne merge que sur eval verte.

La boucle, à chaque campagne (`make eval-models`) ou au fil des journaux de production :

1. **Constat** — une éval comportementale/chaîne échoue pour un `(modèle, règle)` précis
   (ex. campagne 2026-06-15 : Haiku rate COC-merge).
2. **Diagnostic du bon levier** — l'échec se corrige TOUJOURS dans le scaffolding, JAMAIS dans
   spec/design : profil de contexte du modèle, ou agent `.md` du rôle. Si la règle violée est
   **éliminatoire** (chaîne de commandement), le modèle est écarté du rôle — on ne « rattrape » pas
   une faille de gouvernance par du prompt.
3. **Patch minimal** — la plus petite modification de profil/agent qui adresse le constat.
4. **Vérification** — re-lancer les évals *affectées* pour ce modèle. Le patch doit **lever le score
   visé sans en régresser un autre** (même exigence que le merge gate). Sinon : rejet.
5. **Commit gouverné** — bump de `version:` de l'agent + changelog ; validation humaine (comme un merge).
   L'historique des versions d'agent = la mémoire de leur évolution.

Ainsi les agents suivent les modèles en continu, mais chaque évolution est **mesurée, versionnée,
réversible** — jamais une dérive opaque.

## À surveiller dans le temps

- **Régression silencieuse** : un nouveau point de version d'un modèle peut baisser un score.
  Le scorecard daté la rend visible — d'où l'intérêt de re-lancer périodiquement, pas seulement
  à l'arrivée d'un modèle.
- **Relâcher le scaffolding** : à mesure que les modèles progressent, des règles qui exigeaient un
  profil `verbose` peuvent passer en `base`. Le harnais dit quand on peut simplifier le contexte.
- **Cross-vendor** (Gemini/Vertex, cf. deck) : l'orchestrateur est Claude-only aujourd'hui
  (`claude -p` codé en dur). Comparer hors-Claude demandera un runner abstrait — backlog assumé.
