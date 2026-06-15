# Faire tourner le lab hors de votre Mac

> État : la **colonne d'orchestration** est mûre pour tourner **hors-Mac dans un sandbox jetable et
> sans secret**, pour des features pures comme celles déjà éprouvées. Elle n'est PAS prête à tourner
> sur une machine ayant accès à des credentials/prod, ni encore éprouvée sur une vraie feature LMFR.

## 0. Le modèle de menace (à lire avant tout)

L'implementer tourne avec `--permission-mode acceptEdits` et une whitelist Bash incluant
`python3`/`uv`/`make` : **il exécute du code écrit par un modèle, par conception** (il doit écrire
puis lancer ses tests). On a durci la surface de l'orchestrateur (verify sans shell, pas
d'injection osascript, garde fond/forme), mais la capacité d'exécution de l'agent est inchangée.

Conséquence : **ne lancer que dans un environnement jetable et sans secret.** Jamais sur un poste
ou un serveur portant SSH/gcloud/AWS, ni avec accès à de la prod.

## 1. Sandbox conteneurisé

```bash
docker build -t lab-ia-natif .
export ANTHROPIC_API_KEY=sk-...           # seule credential donnée au conteneur
LAB_BUDGET_USD=20 scripts/run_sandboxed.sh work/ma-feature
```

`scripts/run_sandboxed.sh` lance un conteneur **`--rm` (jetable), non-root, `--cap-drop ALL`,
`--no-new-privileges`, pids/mémoire bornés**, ne montant QUE la feature + un volume d'approbations.
L'image (`.dockerignore`) n'embarque ni l'historique git, ni les secrets, ni le deck commercial.

### Le maillon à durcir : l'egress réseau
Par défaut Docker donne un **accès sortant complet** → exfiltration ou `pip install` malveillant
possibles depuis le code de l'agent. `--network none` ne marche pas (la CLI claude doit joindre
l'API). En production :
- réseau Docker dédié + pare-feu/proxy **n'autorisant que `api.anthropic.com`** (et le miroir de
  paquets interne si besoin), via `LAB_DOCKER_NETWORK=ma-net-filtree scripts/run_sandboxed.sh …` ;
- ou un egress-proxy (Squid/allowlist) sur l'hôte.
Tant que l'egress n'est pas restreint, considérer le sandbox comme « confiné en écriture/credentials
mais pas en exfiltration ».

## 2. Variables d'environnement

| Var | Rôle |
|---|---|
| `ANTHROPIC_API_KEY` | auth de la CLI claude headless (obligatoire hors-Mac) |
| `LAB_BUDGET_USD` | plafond de coût agents du run (0 = pas de plafond) |
| `LAB_TASK_TIMEOUT` | mur wall-clock par tâche (défaut 2400 s) |
| `LAB_NO_NOTIFY` | `1` = pas de notif macOS (osascript) — mettre à 1 hors-Mac |
| `LAB_GCHAT_WEBHOOK` | notifications checkpoints/blocages vers Google Chat (cross-plateforme) |
| `LAB_APPROVALS_DIR` | dossier des jetons d'approbation (défaut `work/<feat>/.approvals`) — **clé de l'approbation distante** |

## 3. Approbation humaine à distance

Les checkpoints `blocking` attendent un fichier d'approbation. `LAB_APPROVALS_DIR` permet de le
placer sur un **volume partagé** : l'Owner approuve depuis une autre machine.

```bash
# côté conteneur : LAB_APPROVALS_DIR=/approvals (monté depuis ./.sandbox-approvals)
# côté Owner (même volume / dossier synchronisé) :
LAB_APPROVALS_DIR=./.sandbox-approvals scripts/approve.sh CP-2 work/ma-feature
LAB_APPROVALS_DIR=./.sandbox-approvals scripts/reject.sh CP-1 work/ma-feature "raison" T1
```

Patterns possibles pour le volume partagé : montage NFS/cloud, dossier synchronisé (Drive/Syncthing),
ou un petit dépôt git que les deux côtés `pull`/`push`. (Un vrai endpoint HTTP/Slack-action reste à
construire si l'on veut approuver « depuis son téléphone » — non fourni.)

## 4. CI (déjà en place)

`.github/workflows/gate.yml` tourne sur `ubuntu-latest` et lance **`make ci`** = lint **non mutant**
(`ruff check` + `ruff format --check`) + tests + evals, suite orchestrateur comprise (shim claude
déterministe, aucun vrai agent ni clé requis). `make gate` (local) garde l'auto-fix ; `make ci`
échoue au lieu de corriger en silence.

## 5. Forker pour une réutilisation externe

La colonne d'orchestration est générique ; le packaging actuel est spécifique LMFR. Pour un fork
réutilisable hors LMFR :

**À retirer / neutraliser :**
- `LMFR - Dominique FDE.pptx` (deck commercial, 54 Mo) — `git rm`, déjà exclu de l'image via
  `.dockerignore`.
- `work/*` (features d'exemple/jetables) et `docs/workflow-review-*.md`.
- Les spécificités LMFR de `CLAUDE.md` (Mozaïc, Adeo Global Ready, vocabulaire Owner/FDE/PE,
  Vibe Workshop) et du template `design.md` §6 — à généraliser ou rendre optionnelles.

**Générique, à garder tel quel :** `scripts/` (orchestrateur, content_guard, registry, eval_models,
approve/reject, run_sandboxed), `.claude/agents/*`, `templates/*`, `models/*` (registre + EVOLUTION),
`evals/`, `tests/`, `Makefile`, CI, `Dockerfile`.

**À ajouter pour une diffusion :** un `LICENSE` (décision du propriétaire — non choisi ici), un README
« getting started » générique (le README actuel mentionne le contexte LMFR), et idéalement extraire
les bouts LMFR de `CLAUDE.md` dans un `CLAUDE.local.md` non versionné par le fork.

## 6. Reste à faire (non bloquant pour un sandbox jetable, requis pour « sérieux »)

- Egress allowlist effectif (cf. §1) — **le plus important**.
- Endpoint d'approbation distante ergonomique (au-delà du volume partagé).
- Garde anti-injection de prompt sur le corps des artefacts (revue : M14) avant inputs non fiables.
- 1 baptême sur une **vraie feature LMFR** avec humain en supervision.
