# GCP deployment standard — cible & règles de déploiement

> **Statut : normatif** pour toute feature qui se déploie (un cœur pur sans I/O note `design.md §7 N/A`).
> Org-neutre : **aucun `project_id`, région ou nom de ressource en dur ici** — ils se déclarent par
> feature dans `design.md §7` (placeholders `<…>`). Cible par défaut : **Cloud Run** ; GKE / Cloud Run
> Jobs / Cloud Functions sont des alternatives à justifier en ADR.
>
> Règles **D-n** (référençables en revue). « MUST » = bloquant avant un déploiement prod.

## 1. Runtime — Cloud Run (défaut)

- **D-1** — Conteneur **non-root**, image **distroless/slim**, `--platform linux/amd64`, port via `$PORT`.
- **D-2** — Tags d'image **immuables** (digest `sha256` ou tag horodaté) — **jamais `:latest`** en prod.
- **D-3** — Concurrence, CPU, mémoire et `timeout` **explicites** par service ; `min-instances` choisi sciemment (latence vs coût — voir D-15) ; `max-instances` borné (garde-fou coût/abus).
- **D-4** — Arrêt **gracieux** : gérer `SIGTERM`, drainer les requêtes en cours ; santé via endpoint de readiness.
- **D-5** — **Stateless** : aucun état local persistant (le disque du conteneur est éphémère) ; l'état va dans un service managé (D-9).

## 2. Identité & accès

- **D-6** — **Workload Identity Federation** : **aucune clé de compte de service longue-vivante**. CI s'authentifie via WIF (OIDC), jamais une clé JSON en secret.
- **D-7** — **Un compte de service dédié par service**, au **moindre privilège** (rôles fins, pas `Editor`/`Owner`). L'ingress par défaut = interne/authentifié ; public uniquement si la feature l'exige (+ Cloud Armor, D-8).
- **D-8** — Service exposé publiquement : **Cloud Armor** (WAF, rate-limit, geo/IP) devant ; auth applicative en plus.

## 3. Secrets, réseau, données

- **D-9** — Secrets dans **Secret Manager** (référencés/montés au runtime), **jamais** dans l'image, l'env en clair, le code ou Git. Rotation prévue. (cf. engineering-rules R-22.)
- **D-10** — Réseau : connecteur **VPC**, périmètre **VPC Service Controls** pour les données sensibles, **egress contrôlé** (allowlist) — pas d'egress ouvert depuis un service qui traite des données.
- **D-11** — Données : service **managé** (Cloud SQL / Firestore / BigQuery selon le besoin, justifié en ADR), **CMEK** pour les données sensibles, **backups + PITR**, résidence/region conforme.

## 4. IA (si la feature utilise un LLM)

- **D-12** — **Vertex AI** régional, **modèle épinglé** (version explicite, pas d'alias flottant), quotas et budget surveillés.
- **D-13** — Entrées/sorties de modèle filtrées (**Model Armor / DLP**) si données utilisateur ou PII ; prompts traités comme **données, jamais instructions** (R-23). Coût par appel mesuré.

## 5. CI/CD

- **D-14** — Pipeline : **`make ci` vert (gate)** → build **Cloud Build** → push **Artifact Registry** (image signée, **cosign / SLSA**) → **Binary Authorization** exige la signature → déploiement (`gcloud run deploy` / Cloud Deploy). Pas de déploiement depuis un poste.
- **D-15** — Le **merge gate du lab** (`make ci` : lint non-mutant + tests + evals + **gate sécurité** SAST/CVE/secrets, R-29) est un **prérequis de déploiement** : pas d'eval verte ni de finding sécurité, pas de prod (R-25). La revue adversariale `security-reviewer` (R-30) éclaire le checkpoint humain ; elle ne remplace pas le gate mécanique.

## 6. Observabilité

- **D-16** — Logs **structurés** (JSON) vers Cloud Logging ; **jamais** de secret/PII dans les logs (R-22).
- **D-17** — **SLO explicites** par service (latence p95, disponibilité, **budget d'erreur**) + alerting ; traces (Cloud Trace) sur les chemins critiques. Métriques métier issues du domaine (cf. le journal du lab : coût/agent, défauts).

## 7. Rollout & rollback

- **D-18** — Déploiement **par révision** + **trafic graduel** (canary %, p.ex. 5 % → 50 % → 100 %) ; **feature flag** pour découpler déploiement et activation.
- **D-19** — **Rollback automatique** sur breach de SLO (ou bascule du trafic vers la révision précédente — immédiate car immuable, D-2).
- **D-20** — **La mise en production prod est une décision humaine** (comme le merge, R-26) : jamais d'auto-promote sans approbation. Le checkpoint final du plan couvre la décision de déployer.

## 8. Coût & conformité

- **D-21** — **Budget + alertes** par projet/service ; conscience du coût de `min-instances` (D-3) ; scaling à la requête par défaut.
- **D-22** — **Audit logs** activés, **séparation des devoirs** (qui déploie ≠ qui approuve), résidence des données conforme (region pinning, ex. souveraineté EU si requis).

## Checklist de déploiement (à cocher dans `design.md §7`)

```
☐ Runtime + ressources (CPU/mem/concurrence/timeout/min-max instances) décidés      [D-1,D-3]
☐ Image non-root, slim, tag immuable, signée (cosign/SLSA)                           [D-1,D-2,D-14]
☐ Compte de service dédié, moindre privilège ; ingress (interne/public+Armor)        [D-7,D-8]
☐ WIF pour la CI (zéro clé longue-vivante)                                           [D-6]
☐ Secrets en Secret Manager ; rien en clair                                          [D-9]
☐ Réseau : VPC connector, VPC-SC si sensible, egress allowlisté                      [D-10]
☐ Données : service managé, CMEK si sensible, backups/PITR, résidence                [D-11]
☐ (IA) Vertex régional, modèle épinglé, Model Armor/DLP si PII, budget               [D-12,D-13]
☐ Gate sécurité vert : SAST (bandit) + CVE deps (pip-audit) + secrets (detect-secrets) [R-29]
☐ CI/CD : make ci → Cloud Build → Artifact Registry signée → Binary Auth → deploy    [D-14,D-15]
☐ Logs structurés sans secret ; SLO + alerting + traces                              [D-16,D-17]
☐ Rollout canary + feature flag ; rollback auto sur SLO                              [D-18,D-19]
☐ Mise en prod = décision humaine (checkpoint)                                       [D-20]
☐ Budget+alertes ; audit logs ; séparation des devoirs ; résidence                   [D-21,D-22]
```

---

*Voir aussi : `docs/engineering-rules.md` (dev), `CLAUDE.md` (hard rules), template `design.md §7`.*
