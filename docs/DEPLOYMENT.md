# Faire tourner le lab hors de votre Mac

> État : la **colonne d'orchestration** est mûre pour tourner **hors-Mac dans un sandbox jetable et
> sans secret**, pour des features pures comme celles déjà éprouvées. Elle n'est PAS prête à tourner
> sur une machine ayant accès à des credentials/prod, ni encore éprouvée sur une vraie feature de production.

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

### Egress allowlisté (fourni et validé)
Par défaut Docker donne un **accès sortant complet** → exfiltration ou install malveillant possibles
depuis le code de l'agent. `--network none` ne marche pas (la CLI claude doit joindre l'API). La
solution fournie (portable, marche sur Docker Desktop) : un réseau **`--internal`** (sans internet)
+ un **proxy tinyproxy allowlisté** qui ne laisse sortir que vers `anthropic.com`.

```bash
scripts/sandbox_net.sh up                 # crée lab-internal (sans egress) + lab-egress + le proxy
LAB_DOCKER_NETWORK=lab-internal LAB_EGRESS_PROXY=lab-egress-proxy:8888 \
  ANTHROPIC_API_KEY=sk-... LAB_BUDGET_USD=10 scripts/run_sandboxed.sh work/ma-feature
scripts/sandbox_net.sh down                # nettoyage
```

Le sandbox tourne alors sur `lab-internal` (aucun egress direct) et ne joint l'extérieur QUE via le
proxy. Allowlist dans `sandbox/filter` (une regex de domaine par ligne — ajouter un miroir de paquets
interne ici si un run doit installer des deps au runtime, déconseillé).

**Validé** (2026-06-15, depuis un conteneur sur `lab-internal`) :
- `api.anthropic.com` via proxy → HTTP 405 (TLS atteint l'API réelle) ✅ autorisé ;
- `example.com` / `github.com` via proxy → curl exit 7 ✅ refusés par le proxy ;
- sans proxy sur l'internal → curl exit 6 ✅ aucun egress (pas même de DNS).

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

## 5. Réutilisation externe (le cœur est générique)

Le fonctionnement (orchestrateur, agents `.md`, templates, `CLAUDE.md`, README) **ne mentionne aucune
organisation** : pas de design system ni de référentiel de conformité codés en dur. Les spécificités
d'un client se déclarent **par feature, dans `design.md` §6** (nom du design system, référentiel
applicable) et §2.1 (repos internes de l'organisation) — jamais dans le cœur.

**Brancher une organisation :** dans le `design.md` d'une feature, renseigner §6 (ex. tel design
system, tel référentiel d'accessibilité/conformité) et §2.1 (repos internes + contacts). L'agent
`design-scout` lit ces entrées et reste agnostique.

**Si vous clonez depuis un dépôt porteur d'un contexte client**, retirer en plus : tout deck/PDF
commercial (`*.pptx`, déjà exclu de l'image via `.dockerignore`), les features d'exemple `work/*`
et les revues `docs/workflow-review-*.md`.

**À ajouter pour une diffusion :** un `LICENSE` (décision du propriétaire — non choisi ici).

**Générique, à garder tel quel :** `scripts/`, `.claude/agents/*`, `templates/*`, `models/*`,
`evals/`, `tests/`, `Makefile`, CI, `Dockerfile`, `sandbox/`.

## 6. Reste à faire (non bloquant pour un sandbox jetable, requis pour « sérieux »)

- ~~Egress allowlist~~ ✅ fourni et validé (cf. §1 : `scripts/sandbox_net.sh`).
- 1 **run live `claude -p` dans le conteneur** (avec ANTHROPIC_API_KEY) — reste à exécuter pour
  prouver le chemin agent de bout en bout en sandbox (le `make ci` in-image utilise le shim).
- Endpoint d'approbation distante ergonomique (au-delà du volume partagé).
- Garde anti-injection de prompt sur le corps des artefacts (revue : M14) avant inputs non fiables.
- 1 baptême sur une **vraie feature de production** avec humain en supervision.
