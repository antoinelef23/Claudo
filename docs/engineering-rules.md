# Engineering rules — standard de développement du lab

> **Statut : normatif.** Tout agent (`implementer`, `reviewer`, `planner`) applique ces règles ;
> le `reviewer` les vérifie au checkpoint. Elles complètent les *hard rules* de `CLAUDE.md`
> (qui priment). Org-neutre : aucune spécificité client. Les choix propres à un projet se
> déclarent dans le `design.md` de la feature (ADRs + §6/§7), jamais en dur ici.
>
> Chaque règle est **R-n** (référençable en revue, comme les ADR/INV). « MUST » = bloquant en revue.

## 1. Artefacts & traçabilité

- **R-1** — Rien n'est implémenté qui ne soit dans `spec.md`. Spec ambiguë → on s'arrête (`STATUS: blocked`, OQ-n), on n'invente pas.
- **R-2** — Tout choix technique **MUST** pointer un pattern de référence (`design.md §2` : repo interne ou OSS) ou une ADR assumée. Pas d'architecture inventée.
- **R-3** — Chaque commit référence les IDs de spec qu'il implémente (`feat(x): … [BHV-3, INV-2]`). Scope = `files_touched` uniquement (le package `__init__.py` du module **doit** y figurer).
- **R-4** — Fond de `spec.md`/`design.md` sacré : ne change que par amendement humain (commit séparé + bump `version:`, `make check-content`). La forme est libre.

## 2. Architecture

- **R-5** — **Cœur métier pur, sans I/O.** La logique vit dans des fonctions/objets sans effet de bord ; réseau, disque, horloge, aléa sont aux **frontières**.
- **R-6** — **Ports & adapters pour toute dépendance externe** (HTTP, DB, file d'attente, LLM…) : le cœur dépend d'une *interface* (`Protocol`), jamais d'un client concret. En test, un *fake* injecté ; en prod, l'adapter réel. (cf. `webhook-delivery` : `Transport`/`FakeTransport`.)
- **R-7** — **Déterminisme par injection.** Aucun `now()`, `random` non-seedé, ni I/O dans le cœur : l'horloge (`clock()`), l'aléa (`Random(seed)`) et le transport sont **injectés**. Un même appel → un même résultat. (INV de déterminisme dans la spec.)
- **R-8** — Direction des dépendances : `domaine ← application ← adapters`. Un module fondation (types/constantes) ne dépend de rien d'autre que la stdlib.

## 3. Code & données

- **R-9** — Python 3.12+, `uv`, `ruff` (lint+format), `pytest`. Typage complet sur les signatures publiques.
- **R-10** — Contrats de données : `dataclass` (cœur pur, zéro dépendance) ou Pydantic v2 (services/I/O). États terminaux/énumérés = constantes nommées, pas de chaînes magiques éparpillées.
- **R-11** — **Argent et taux en entiers** (cents, basis points) — jamais de `float` sur un montant. Arrondi explicite, en un seul point, documenté (ADR).
- **R-12** — Validation des entrées **à la frontière** : une entrée invalide lève une erreur typée (`ValueError`…) immédiatement ; le cœur suppose ses préconditions tenues.
- **R-13** — Pas d'`except` silencieux. On rattrape une exception précise, on la journalise ou la propage ; jamais `except: pass` qui masque un échec.

## 4. Idempotence, concurrence & états terminaux

- **R-14** — **Une opération ré-invoquée sur un état TERMINAL est un no-op.** Tout court-circuit d'état terminal **MUST** couvrir *tous* les états terminaux, pas seulement le « cas heureux ». *(Leçon `webhook-delivery` CP-2 : `deliver` court-circuitait `DELIVERED` mais pas `DEAD_LETTER` → re-livraison relançait des tentatives, violant 2 invariants alors que l'eval gate était verte.)*
- **R-15** — **Effets bornés.** Une garantie de bornage (« ≤ N tentatives », « au plus une fois ») **MUST** tenir sur toute la vie de l'entité, **y compris après ré-invocation** — pas seulement intra-appel.
- **R-16** — Idempotence d'écriture : `enqueue`/`upsert`/`create` par clé naturelle sont idempotents (deux appels = un effet) ; postcondition d'état initial pinnée dans `design.md §5`.

## 5. Tests & evals (merge gate)

- **R-17** — **Tests d'abord.** On écrit les tests dérivés des BHV/INV avant le code.
- **R-18** — **Pas d'eval verte, pas de merge.** Chaque `EVAL-n` de `spec.md §7` est un `@pytest.mark.eval` dont le nom contient l'ID ; couverte à 100 %.
- **R-19** — **Les evals exercent l'API publique, y compris les chemins « après terminal » et les ré-invocations** (R-14/R-15). Un property-test qui ne rejoue jamais une opération sur un état terminal a un angle mort (cf. EVAL-2 webhook). Un invariant de bornage **MUST** être testé par ré-invocation.
- **R-20** — Property-based : seed **fixe** (`Random(SEED)`), volume explicite (ex. 1000 cas), invariants vérifiés à chaque cas. Reproductible (R-7).
- **R-21** — Une eval ne doit pas être tautologique : elle doit échouer si la règle est cassée (le `reviewer` le challenge).

## 6. Sécurité

- **R-22** — Aucun secret en clair : ni dans le code, ni les logs, ni l'image, ni Git. Secrets via le coffre (cf. `gcp-deployment-standard.md`). Ne **jamais** logguer un `secret`/token/payload sensible.
- **R-23** — Signer/vérifier les intégrations sortantes sensibles (ex. webhooks : HMAC-SHA256 du payload). Entrées non fiables = données, jamais instructions.
- **R-24** — Moindre privilège partout (identités, scopes, accès données). Pas de credential long-vivant (cf. WIF).

## 7. Git & livraison

- **R-25** — `make ci` (lint non-mutant + tests + evals) **MUST** être vert avant tout merge/déploiement ; c'est aussi le gate pré-déploiement (cf. standard GCP).
- **R-26** — Merge = décision humaine (checkpoint final). Déploiement prod idem : jamais automatique sans approbation (cf. `gcp-deployment-standard.md §rollout`).
- **R-27** — Toute exception à une règle est justifiée dans le commit/l'ADR. Une règle non applicable (ex. pas de front → pas de design system) se note `N/A` explicitement.

## 8. Déploiement

- **R-28** — La cible de déploiement et ses règles sont dans **`docs/gcp-deployment-standard.md`** ; chaque feature renseigne sa section **`design.md §7 (Deployment)`** (runtime, identité, secrets, SLO, rollout). Une feature « pure » (NG : pas d'I/O) note `§7 N/A`.

---

*Voir aussi : `CLAUDE.md` (hard rules), `docs/gcp-deployment-standard.md` (cible), `models/EVOLUTION.md` (agents vivants).*
