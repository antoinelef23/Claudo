# Passer à l'échelle : planification récursive et jumeau numérique

Cette page enregistre la première évolution structurante du lab vers le multi-périmètre. Elle **étend** [l'architecture de l'orchestrateur](architecture.md), elle ne la remplace pas : la thèse v1 tient intégralement — *les agents génèrent, l'humain valide* ; le DAG, les vagues parallèles et les checkpoints restent le socle. Ce qui change, c'est qu'on ajoute une couche *au-dessus* du planner pour des demandes qui ne tiennent pas dans un seul périmètre.

## Pourquoi

Le flot v1 — un `planner` → un DAG → une feature dans `work/<feature>/` — tient tant que la demande tient dans **un seul bounded context**. Il casse dès qu'une demande métier traverse plusieurs périmètres/dépôts, et il casse de trois façons distinctes :

- **explosion de contexte** — au-delà d'une poignée de dépôts *modifiés activement* en même temps, l'agent se perd (le mur est la surface de *modification*, pas la surface de lecture) ;
- **masse de conformité** — un référentiel de conformité d'organisation (plusieurs centaines de points), un design system partagé, des centaines de dépôts : tenter de tout faire vivre dans un `design.md` écrit à la main produit un « trou noir » illisible, vite faux ;
- **régression inter-périmètres** — un agent qui ne connaît que son contexte a raison *localement* et casse le voisin. Le vrai risque du multi-périmètre n'est pas la livraison, c'est la **mesure d'impact**.

Les trois ADR ci-dessous prennent l'orchestrateur de « une feature, un contexte » à « une demande qui traverse l'org ». Le pivot des trois est le même : un **jumeau numérique** de l'organisation, interrogé à la demande.

## Décisions (ADRs)

### ADR-1 — L'unité de travail = un bounded context ; au-delà, le planner récurse

- **Status :** accepted — intention de conception, implémentation différée
- **Context :** une demande métier traverse rarement une seule équipe. Le planner v1 produit un `tasks.md` pour une feature tenant dans un seul périmètre ; au-delà, tout charger dans un contexte unique dégrade l'agent.
- **Decision :** l'unité de travail est le **bounded context**. Critère d'arrêt de la récursion : si la spec tient dans un seul bounded context, le planner **exécute** (il produit un `tasks.md`, comme aujourd'hui) ; sinon il agit en **dispatcher** — il découpe la spec en sous-specs (une par périmètre), délègue un sous-planner par sous-spec, et ne code pas lui-même. Récursion bornée en profondeur.
- **Anchored on :** le pattern Cognition (le plan généré, l'humain valide) déjà porté par l'agent `planner` ; la détection de collision `paths_overlap` de `lab/engine/plan.py` (des périmètres = des `files_touched` disjoints) généralisée d'un cran. Le dispatcher est le planner appliqué à lui-même (poupée gigogne).
- **Alternatives considered :** (a) un seuil en *nombre de dépôts* — rejeté : un nombre arbitraire ne capture pas la cohésion métier, le bounded context oui ; (b) tout charger et compter sur de plus grandes fenêtres — rejeté : la dégradation vient de la surface de modification, pas de la taille brute du contexte.
- **Consequences :** le critère d'unité de travail devient explicite (il répond à « c'est quoi une unité de travail ? »). Il faut une carte des périmètres et de leurs dépendances → ADR-2. La profondeur de récursion doit être plafonnée et le découpage validé par un humain → ADR-3.

### ADR-2 — La mémoire = un jumeau numérique interrogé ; `design.md` devient une projection

- **Status :** accepted — intention de conception, implémentation différée
- **Context :** un référentiel de conformité d'org, un design system partagé, des centaines de dépôts : si on tente de tout faire vivre dans un `design.md` à la main, il devient un trou noir illisible. Mais l'agent a besoin de cas concrets — les quelques dépôts de référence qui implémentent déjà tout ou partie de la cible.
- **Decision :** deux couches qu'on ne confond jamais. (1) une **constitution mince**, toujours en contexte (`CLAUDE.md`) : les rares invariants vrais *partout* — sécurité, noyau de conformité non-négociable, conventions. (2) un **jumeau numérique de l'org**, mémoire grasse **interrogée à la demande** : carte des dépôts, graphe d'impact (qui dépend de qui), catalogue de patterns (quel dépôt implémente quoi), référentiel de conformité complet. Un **agent mémoire** (extension de `design-scout`) interroge le jumeau et **projette** un `design.md` court, spécifique à un bounded context. Le `design.md` n'est plus écrit à la main : il est généré, jetable, et ne grossit jamais. Les « 6-7 dépôts de référence » sont un *résultat de requête* distillé en patterns — pas une liste statique, pas 7 dépôts bruts chargés en contexte.
- **Anchored on :** le principe [git-as-memory](git-as-memory.md) du lab (la mémoire vit dans un substrat versionné, pas dans une tête ni un wiki) ; l'agent `design-scout`, qui explore déjà dépôts internes et références OSS — le jumeau est sa base de connaissance persistée, l'agent mémoire est `design-scout` outillé d'un index requêtable (RAG sur l'org).
- **Alternatives considered :** (a) un fichier de règles global à l'échelle de l'org, chargé en contexte — rejeté : reproduit exactement le trou noir, la masse non-négociable ne tient pas en contexte ; (b) un `design.md` écrit à la main par périmètre — rejeté : ne passe pas l'échelle, dérive, redondance.
- **Consequences :** le jumeau devient le cœur du lab v2 — c'est lui qui fournit le critère de découpe (ADR-1), la projection `design.md`, et l'eval d'impact (ADR-3). C'est aussi l'actif que le lab construit puis transmet : les frameworks agentiques génériques sont *bring-your-own-context*, aucun n'a de jumeau d'org. **Dette acceptée :** construire et tenir le jumeau à jour est un investissement initial non trivial (rôle FDE).

### ADR-3 — Fan-in : un eval transverse mécanique, deux portes humaines seulement

- **Status :** accepted — intention de conception, implémentation différée
- **Context :** un agent qui ne connaît que son contexte peut casser un périmètre voisin. Il faut *signer* la cohérence inter-sous-specs sans réintroduire un goulot humain à chaque niveau (qui tuerait la vélocité et confirmerait le reproche de verbosité fait aux méthodes agentiques bavardes).
- **Decision :** trois signatures, une seule lourde. (1) **gate mécanique = un eval transverse** dérivé du graphe d'impact du jumeau : *un changement dans le périmètre A viole-t-il un invariant/contrat du périmètre B ?* C'est la **mesure d'impact mécanisée**, pas un jugement d'agent ; elle respecte « pas d'eval verte, pas de merge ». (2) un **reviewer transverse** (agent) produit un rapport d'impact lisible à partir du même graphe — il informe, il ne décide pas. (3) **humain à deux endroits seulement** : à la racine *avant le fan-out* (il valide la décomposition + la carte d'impact — c'est là qu'est le craftsman), et au **merge final**. Jamais à chaque niveau de l'arbre.
- **Anchored on :** le gate d'eval existant (`_eval_gate`, anti-empty-gate) et le modèle de checkpoint (`blocking`/`auto`, merge toujours humain) de `lab/engine/orchestrate.py` ; `paths_overlap` (collision de fichiers détectée *avant* le run) généralisé en collision d'**impact** inter-périmètres. C'est la machinerie de gate v1 montée d'un cran.
- **Alternatives considered :** (a) cohérence laissée au seul jugement d'un agent reviewer — rejeté : non mécanique, non reproductible, l'impact doit être un eval ; (b) checkpoint humain à chaque niveau de récursion — rejeté : goulot en 2^n, verbosité.
- **Consequences :** la mesure d'impact devient un artefact exécutable (l'eval transverse), donc gateable et traçable comme le reste. Les feuilles tournent leurs evals locales ; la racine porte l'eval transverse + le rapport. Deux portes humaines, profondeur bornée. Dépend du graphe d'impact du jumeau (ADR-2).

## Ce que ça change, en une phrase

Le jumeau numérique est le pivot : il fournit le critère de découpe (le planner peut récurser), il supprime le trou noir du `design.md` (projection courte et jetable), et il transforme la mesure d'impact en eval gateable. Les trois décisions n'en font qu'une.

## Encore ouvert (à trancher dans une spec dédiée)

- Comment le **graphe d'impact** du jumeau est construit et tenu frais (dérivé du code ? déclaratif ? hybride) — c'est la pièce dont dépend l'eval transverse d'ADR-3.
- La techno d'**index** du jumeau (la couche requêtable de l'agent mémoire).
- La **valeur du plafond** de profondeur de récursion d'ADR-1.
- Le **format de sous-spec** émis par le dispatcher (sous-ensemble du template `spec.md`, ou contrat dédié).
