# Threat model — l'orchestrateur agentique lui-même

> Le gate sécurité (R-29) et le `security-reviewer` (R-30) sécurisent le **code produit**.
> Ce document couvre les menaces contre le **processus agentique** : les agents, les entrées
> qu'ils ingèrent, et la boucle d'orchestration. Référentiels : **OWASP Top 10 for LLM Apps
> 2025** (LLM01–10), **OWASP Agentic / ASI** (ASI01–10), **MITRE ATLAS**, **Google SAIF 2.0**.
> Statut par menace : ✅ mitigé · 🟡 partiel · 🔴 résiduel.

## Surface d'attaque
Un agent `claude -p` headless qui : lit `spec.md`/`design.md`/`tasks.md` (potentiellement rédigés
par un modèle), lit des repos de référence (`design-scout`), exécute des commandes shell et le
code qu'il écrit, et commit. Owner unique, exécution locale ou en conteneur sandboxé, une clé API.

## Menaces & contrôles

| Menace (réf) | Statut | Contrôle en place / écart |
|---|---|---|
| **Injection de prompt indirecte** (LLM01 / ASI01 / ATLAS AML.T0051,T0054) — instructions cachées dans un spec/design, un repo de référence, ou la **sortie d'outil** (logs de test, `curl`) | 🔴 **résiduel** | Surface aujourd'hui RÉDUITE : specs validées par l'Owner (Vibe Workshop + approbation du plan), `design-scout` **jamais** lancé sur de vrais repos. Blast-radius limité par l'allowlist d'outils, l'allowlist `verify`, l'egress sandbox. MAIS aucune quarantaine/provenance des contenus ingérés. **Devient la menace n°1 dès que `design-scout` lit des repos externes.** Plan ci-dessous. |
| **Excessive agency / tool misuse** (LLM06 / ASI02) | ✅ | `--allowedTools` (default-deny, Bash allowlisté), `verify` tokenisé sans shell + allowlist (H1), **relecteurs en lecture seule** (REVIEW_ARGS, pas d'auto-édition — moindre privilège par rôle). |
| **Sandbox / RCE / escape-to-host** (ASI05 / ATLAS) | ✅ | Conteneur Docker non-root + egress allowlist **validés** ; commits locaux (pas de push auto) ; merge/déploiement = décision humaine. |
| **Reward hacking** — l'agent affaiblit son propre juge (test) | ✅ | **R-31** : eval hors-scope modifiée → tâche refusée. Séparation des devoirs (modèle reviewer ≠ implementer). **R-32** mutation testing prouve que les evals tuent les mutants. Thèse review>evals prouvée 2×. |
| **Sensitive info disclosure / lecture de secrets** (LLM02 / LLM07) | 🟡 partiel | `detect-secrets` bloque les secrets **commités** ; egress allowlist = filet anti-exfiltration. ÉCART : rien n'empêche un agent de **lire** `.env`/credentials en explorant (pas de deny-list de chemins). |
| **Unbounded consumption / denial-of-wallet** (LLM10 / ATLAS Cost Harvesting) | ✅ | `LAB_BUDGET_USD` (plafond + vérif par-tâche M13), `LAB_TASK_TIMEOUT`, `MAX_EVAL_RETRIES`, `MAX_PARALLEL`. |
| **Memory / context poisoning** (ASI06 / LLM04) | 🟡 partiel | `content_guard` empreinte le FOND de spec/design : une altération silencieuse sans bump de version est rejetée. Pas de défense sur un store de mémoire agent persistant (n/a aujourd'hui). |
| **Identity & privilege abuse dans la chaîne** (ASI03) | 🟡 partiel | Une seule identité (clé API partagée) ; pas de token scopé par agent. Mitigé par lecture-seule des relecteurs et l'absence de push auto. |
| **Cascading agent failures** (ASI08) | ✅ | Confinement d'échec (sous-arbre `skipped`, branches saines continuent) ; gate evals + veto sécurité entre étapes. |
| **Hallucinated / typosquatted deps « slopsquatting »** (LLM09 / LLM03) | 🔴 résiduel | `pip-audit` couvre les CVE connues, pas un paquet inexistant/malveillant fraîchement publié. ÉCART : pas de vérif d'existence/réputation avant ajout de dépendance. |
| **Supply chain de build** (provenance/signature) | 🟡 design-only | cosign/SLSA/Binary Auth spécifiés (`gcp-deployment-standard.md` D-14) mais pas câblés ; pas de SBOM (syft/CycloneDX). |
| **Audit / traçabilité** (SAIF observabilité) | 🟡 partiel | `journal.jsonl` (events, coût, verdict, modèle, lens) au niveau orchestrateur. Pas de trace par appel d'outil (OTel `gen_ai.*`). |

## Plan — injection de prompt indirecte (la menace résiduelle prioritaire)
À traiter **avant** que `design-scout` n'ingère de vrais repos externes (pattern dual-LLM /
quarantaine, Willison 2025 / DeepMind CaMeL ; arXiv 2506.08837) :
1. **Traiter tout contenu ingéré comme non fiable** : repos de référence, sorties d'outils, specs
   d'origine non humaine. Ne pas le piper brut dans l'agent qui planifie/commit.
2. **Quarantaine** : un agent *quarantiné* lit le contenu non fiable et n'en renvoie que des
   variables typées/contraintes (noms de patterns, chemins) — jamais des instructions libres —
   vers l'agent *privilégié* qui agit.
3. **Provenance** : marquer les tokens issus de sources non fiables ; l'effet consécutif (commit,
   install, egress) reste sous checkpoint humain.
4. **Garde-fous existants à conserver** : allowlist d'outils, egress allowlist, `curl`/`wget` non
   auto-approuvés, vérification de confiance d'un nouveau repo/MCP.

## Écarts mineurs traçés (backlog sécurité)
- Deny-list de lecture des chemins de secrets pour les agents (LLM02).
- Vérif d'existence/réputation des dépendances avant install (slopsquatting, LLM09).
- SBOM (syft/CycloneDX) + signature cosign/SLSA câblés dans la CI (aujourd'hui design-only).
- Trace OTel `gen_ai.*` par appel d'outil (audit fin).
- Identité/token scopé par rôle d'agent (ASI03).
