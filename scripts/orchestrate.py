#!/usr/bin/env python3
"""Orchestrateur de fond du lab IA-natif.

Lit le tasks.md d'une feature, construit le DAG (depends_on), exécute les tâches
prêtes EN PARALLÈLE via `claude -p` (headless), passe le gate d'evals après chaque
tâche (max 3 itérations), et gère les checkpoints selon leur mode :
  - `mode: blocking` (défaut) — pause + notification, validation humaine via
        scripts/approve.sh CP-1 <feature_dir>
  - `mode: auto` — auto-validé si et seulement si evals vertes ET reviewer PASS ;
        sinon bascule en blocking. Le checkpoint final (merge) est TOUJOURS blocking.

Niveaux d'autonomie :
    --dry-run       montre le plan, rien ne tourne
    --supervised    force tous les checkpoints en blocking (ignore les modes auto)
    (défaut)        croisière : respecte les modes du plan approuvé par l'Owner
    --validate      plan-lint : vérifie le tasks.md et sort (à lancer par planner
                    AVANT de proposer le plan, et par l'Owner avant d'approuver)

Garde-fous d'autonomie :
  - verdict structuré : l'implementer termine par STATUS: done|blocked — un agent
    bloqué sur un trou de spec (OQ) ne passe jamais pour fini
  - anti-gate-vide : une tâche qui implémente des IDs de spec échoue si AUCUNE eval
    n'est collectée (pas d'eval écrite = pas de done, même si `make evals` sort 0)
  - confinement d'échec : une tâche failed/blocked ne bloque que son sous-arbre de
    dépendants (skipped) ; les autres branches continuent
  - commits scopés : on ne stage que les files_touched de la tâche + les artefacts de la
    feature (spec/design/tasks), sous verrou ; tout fichier hors-scope déjà indexé est retiré
    de l'index avant le commit — jamais d'arbre tests/ ou evals/ entier ni de `git add -A`

Usage :
    python3 scripts/orchestrate.py examples/agent-douche --validate
    python3 scripts/orchestrate.py examples/agent-douche --dry-run
    caffeinate -i python3 scripts/orchestrate.py work/ma-feature &   # tourne en fond

Prérequis : claude CLI installé et authentifié ; tasks.md avec status: approved
(frontmatter) — l'orchestrateur refuse un plan non validé (pattern Cognition).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from registry import load_registry, resolve_model

# LAB_ROOT : surcharge pour les tests (sandbox) — défaut : la racine du repo
ROOT = Path(os.environ.get("LAB_ROOT") or Path(__file__).resolve().parent.parent)
REGISTRY = load_registry(
    ROOT
)  # affectation modèle×rôle (vide si pas de models/registry.toml)
MAX_EVAL_RETRIES = 3
MAX_PARALLEL = 3
MAX_CP_REJECTS = 2  # au-delà : le checkpoint passe failed, reprise manuelle
BUDGET_USD = float(os.environ.get("LAB_BUDGET_USD", "0") or 0)  # 0 = pas de plafond
TASK_TIMEOUT_S = int(
    os.environ.get("LAB_TASK_TIMEOUT", "2400")
)  # mur par agent : 40 min
CLAUDE_ARGS = [
    "--permission-mode",
    "acceptEdits",
    "--max-turns",
    "100",
    # headless : acceptEdits couvre les éditions, pas Bash — whitelist minimale pour
    # que l'implementer puisse exécuter ses tests (sinon il code à l'aveugle)
    "--allowedTools",
    "Bash(uv:*),Bash(make:*),Bash(python3:*),Bash(mkdir:*),Bash(ls:*),Bash(git diff:*),Bash(git log:*)",
    # sortie structurée : result + session_id (reprise des retries) + total_cost_usd (journal)
    "--output-format",
    "json",
]
SPEC_ID = re.compile(r"\b(?:INV|BHV|EX|EVAL|NG)-[A-Za-z0-9]+\b")

# H1 — le `verify` d'une tâche est exécuté en shell ; il provient du plan (tasks.md), donc
# potentiellement d'un modèle. On n'exécute QUE des vérificateurs vettés : pas de métacaractère
# shell, et un exécutable de la liste blanche (après d'éventuelles assignations d'env VAR=val).
VERIFY_CMDS = {
    "uv",
    "make",
    "python",
    "python3",
    "pytest",
    "test",
    "true",
    "ls",
    "echo",
}
_SHELL_META = re.compile(r"[;&|`$><(){}]|\\\n")


def verify_allowed(cmd: str) -> bool:
    """True si `cmd` est un vérificateur sûr (liste blanche, aucun opérateur shell)."""
    if not cmd or _SHELL_META.search(cmd):
        return False
    try:
        toks = shlex.split(cmd)
    except ValueError:
        return False
    if (
        "-c" in toks
    ):  # exécution de code inline (python -c …) : injection, jamais nécessaire
        return False
    i = 0
    while i < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i]):
        i += 1  # sauter les assignations d'env en tête (ex. PYTHONPATH=src)
    if i >= len(toks):
        return False
    return toks[i].split("/")[-1] in VERIFY_CMDS


COMMIT_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
COST_LOCK = threading.Lock()
COST_TOTAL = {"usd": 0.0}


@dataclass
class Node:
    id: str
    title: str
    is_checkpoint: bool
    depends_on: list[str] = field(default_factory=list)
    prompt: str = ""
    implements: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    verify: str = ""
    done_when: str = ""
    mode: str = "blocking"  # checkpoints : blocking | auto
    status: str = "pending"  # pending | running | done | failed | blocked | skipped
    rework: str = ""  # commentaire Owner après rejet de checkpoint (transmis à l'agent)
    model: str = ""  # override de modèle de tâche (sinon : défaut de rôle du registre)
    reviewers: int = (
        1  # taille du panel de reviewers (checkpoint) — ≥2 = vote majoritaire
    )


def parse_tasks_md(path: Path) -> tuple[dict, list[Node]]:
    text = path.read_text(encoding="utf-8")

    fm = {}
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.split("#")[0].strip()

    nodes: list[Node] = []
    sections = re.split(r"\n### ", text)
    for sec in sections[1:]:
        header, _, body = sec.partition("\n")
        hm = re.match(r"(T\d+|CP-\d+)\s*—\s*(.*)", header.strip())
        if not hm:
            continue
        nid, title = hm.group(1), hm.group(2).strip()
        is_cp = nid.startswith("CP")

        deps: list[str] = []
        dm = re.search(r"\*\*depends_on\s*:?\*\*\s*\[([^\]]*)\]", body)
        if dm:
            deps = [d.strip() for d in dm.group(1).split(",") if d.strip()]
        if is_cp:
            tm = re.search(
                r"\*\*trigger\s*:?\*\*[^\n]*?quand\s+\[?([T\d\s,]+?)\]?\s+(?:sont\s+)?done",
                body,
            )
            if tm:
                deps = [d.strip() for d in tm.group(1).split(",") if d.strip()]

        pm = re.search(r"\*\*prompt\s*:?\*\*\s*\n?((?:\s*>.*\n?)+)", body)
        prompt = ""
        if pm:
            prompt = "\n".join(
                line.strip().lstrip("> ") for line in pm.group(1).splitlines()
            ).strip()
        if not prompt:
            pm = re.search(r"\*\*prompt\s*:?\*\*\s*([^\n]+)", body)
            if pm:
                prompt = pm.group(1).strip()

        node = Node(nid, title, is_cp, deps, prompt)

        im = re.search(r"\*\*implements\s*:?\*\*\s*\[([^\]]*)\]", body)
        if im:
            node.implements = [t.strip() for t in im.group(1).split(",") if t.strip()]
        fmm = re.search(r"\*\*files_touched\s*:?\*\*\s*([^\n]+)", body)
        if fmm:
            node.files = re.findall(r"`([^`]+)`", fmm.group(1))
        vm = re.search(r"\*\*verify\s*:?\*\*\s*`([^`]+)`", body)
        if vm:
            node.verify = vm.group(1).strip()
        dw = re.search(r"\*\*done_when\s*:?\*\*\s*([^\n]+)", body)
        if dw:
            node.done_when = dw.group(1).strip()
        mm = re.search(r"\*\*mode\s*:?\*\*\s*(auto|blocking)", body)
        if mm:
            node.mode = mm.group(1)
        mom = re.search(r"\*\*model\s*:?\*\*\s*`?([\w.\-]+)`?", body)
        if mom:
            node.model = mom.group(1)
        rm = re.search(r"\*\*reviewers\s*:?\*\*\s*(\d+)", body)
        if rm:
            node.reviewers = max(1, int(rm.group(1)))

        nodes.append(node)

    # H3 — toute tâche placée après un checkpoint doit en dépendre, SAUF si elle dépend déjà
    # d'un nœud situé au niveau ou après ce checkpoint. (L'ancienne règle n'injectait le
    # checkpoint que pour les tâches SANS dépendance — une tâche câblée à une sœur d'AVANT le
    # checkpoint s'exécutait alors avant la validation humaine : faille de gate silencieuse.)
    pos = {n.id: i for i, n in enumerate(nodes)}
    by_id = {n.id: n for n in nodes}
    last_cp: str | None = None
    for n in nodes:
        if n.is_checkpoint:
            last_cp = n.id
            continue
        if not last_cp or last_cp in n.depends_on:
            continue
        # M1 — ne pas injecter le CP dans une tâche dont le CP dépend déjà (tâche-trigger placée
        # APRÈS le CP) : cela créerait un cycle. Le plan-lint le signalerait, mais autant ne pas le fabriquer.
        if n.id in by_id[last_cp].depends_on:
            continue
        cp_i = pos[last_cp]
        if not any(pos.get(d, -1) >= cp_i for d in n.depends_on):
            n.depends_on.append(last_cp)
    return fm, nodes


# ---------------------------------------------------------------- plan-lint


def _ancestors(nodes: list[Node]) -> dict[str, set[str]]:
    by_id = {n.id: n for n in nodes}
    memo: dict[str, set[str]] = {}

    def walk(nid: str, stack: tuple[str, ...] = ()) -> set[str]:
        if nid in memo:
            return memo[nid]
        if nid in stack:  # cycle — signalé par validate(), on coupe ici
            return set()
        acc: set[str] = set()
        for d in by_id.get(nid, Node(nid, "", False)).depends_on:
            acc.add(d)
            acc |= walk(d, (*stack, nid))
        memo[nid] = acc
        return acc

    return {n.id: walk(n.id) for n in nodes}


def _paths_overlap(a: str, b: str) -> bool:
    a, b = a.strip().rstrip("/"), b.strip().rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def validate(feature: Path, fm: dict, nodes: list[Node]) -> tuple[list[str], list[str]]:
    """Plan-lint. Retourne (erreurs, avertissements)."""
    errors: list[str] = []
    warnings: list[str] = []
    by_id = {n.id: n for n in nodes}

    if not nodes:
        return (["aucune tâche reconnue — vérifie le format `### T1 — titre`"], [])
    seen: set[str] = set()
    for n in nodes:
        if n.id in seen:
            errors.append(f"{n.id} : ID dupliqué")
        seen.add(n.id)

    # Graphe
    for n in nodes:
        for d in n.depends_on:
            if d not in by_id:
                errors.append(f"{n.id} : depends_on [{d}] inexistant")
    # Cycles (DFS coloration)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def dfs(nid: str) -> bool:
        color[nid] = GREY
        for d in by_id[nid].depends_on:
            if d not in by_id:
                continue
            if color[d] == GREY:
                errors.append(f"cycle de dépendances via {nid} → {d}")
                return True
            if color[d] == WHITE and dfs(d):
                return True
        color[nid] = BLACK
        return False

    for n in nodes:
        if color[n.id] == WHITE and dfs(n.id):
            break

    # Champs obligatoires des tâches
    for n in nodes:
        if n.is_checkpoint:
            continue
        if not n.done_when:
            errors.append(
                f"{n.id} : done_when manquant (rien d'exécutable ne définit « fini »)"
            )
        if not n.files:
            errors.append(
                f"{n.id} : files_touched manquant ou sans backticks (parallélisme invérifiable)"
            )
        if not n.prompt:
            warnings.append(f"{n.id} : prompt vide — l'implementer n'aura que le titre")
        if not n.verify:
            warnings.append(
                f"{n.id} : pas de verify exécutable — le done_when ne sera pas vérifié mécaniquement"
            )
        elif not verify_allowed(n.verify):
            errors.append(
                f"{n.id} : verify `{n.verify}` rejeté — un vérificateur exécuté en shell ne peut "
                f"contenir d'opérateur shell et doit invoquer un outil vetté {sorted(VERIFY_CMDS)}"
            )
        # M3/M4 — une tâche qui implémente une EVAL-* DOIT déclarer un chemin de test dans son scope ;
        # sinon la couverture par ID retombe sur tout le dépôt (collision cross-feature).
        ev_ids = [
            s for t in n.implements for s in SPEC_ID.findall(t) if s.startswith("EVAL-")
        ]
        if ev_ids and not any(f.startswith(("tests/", "evals/")) for f in n.files):
            errors.append(
                f"{n.id} : implémente {ev_ids} mais aucun chemin tests/ ou evals/ dans files_touched "
                "— l'eval ne serait ni écrite ni gatée dans le périmètre (couverture non scopable)"
            )

    # IDs de spec
    spec_path = feature / "spec.md"
    if spec_path.exists():
        spec_text = spec_path.read_text(encoding="utf-8")
        for n in nodes:
            for tok in n.implements:
                for sid in SPEC_ID.findall(tok):
                    if sid not in spec_text:
                        errors.append(
                            f"{n.id} : implémente [{sid}] introuvable dans spec.md"
                        )
        # Chaque EVAL-n déclarée dans la spec doit être portée par une tâche
        claimed = {s for n in nodes for t in n.implements for s in SPEC_ID.findall(t)}
        for ev in sorted(set(re.findall(r"\bEVAL-\w+\b", spec_text))):
            if ev not in claimed:
                warnings.append(
                    f"{ev} déclarée dans spec.md §7 mais portée par aucune tâche (implements)"
                )
        # Dérive documentaire : les pointeurs « # version : x.y.z » doivent suivre la spec
        sv = re.search(r"^version:\s*([\d.]+)", spec_text, re.M)
        if sv:
            for art in ("tasks.md", "design.md"):
                p = feature / art
                if not p.exists():
                    continue
                m = re.search(
                    r"^spec:.*?version\s*:?\s*([\d.]+)",
                    p.read_text(encoding="utf-8"),
                    re.M,
                )
                if m and m.group(1) != sv.group(1):
                    warnings.append(
                        f"{art} référence spec v{m.group(1)} mais spec.md est en v{sv.group(1)} — "
                        f"dérive documentaire, mets à jour le pointeur après l'amendement"
                    )
    else:
        errors.append("spec.md introuvable à côté de tasks.md")

    # Sécurité du parallélisme : deux tâches non ordonnées ne partagent aucun chemin
    anc = _ancestors(nodes)
    tasks = [n for n in nodes if not n.is_checkpoint]
    for i, a in enumerate(tasks):
        for b in tasks[i + 1 :]:
            if a.id in anc[b.id] or b.id in anc[a.id]:
                continue  # ordonnées par le DAG
            clash = [
                (fa, fb) for fa in a.files for fb in b.files if _paths_overlap(fa, fb)
            ]
            if clash:
                errors.append(
                    f"{a.id} ∥ {b.id} : exécutables en parallèle mais files_touched se recouvrent "
                    f"({clash[0][0]} ↔ {clash[0][1]}) — ajoute un depends_on ou sépare les chemins"
                )

    # H3 — défense en profondeur : aucune tâche ne doit pouvoir s'exécuter avant le checkpoint
    # qui la précède textuellement. parse_tasks_md l'injecte déjà ; ceci attrape les plans où
    # un depends_on manuel court-circuiterait un checkpoint (la validation humaine est sacrée).
    posn = {n.id: i for i, n in enumerate(nodes)}
    cp_pos = [(posn[n.id], n.id) for n in nodes if n.is_checkpoint]
    for n in nodes:
        if n.is_checkpoint:
            continue
        prior = [cid for (ci, cid) in cp_pos if ci < posn[n.id]]
        if prior and prior[-1] not in anc[n.id]:
            errors.append(
                f"{n.id} : s'exécuterait avant le checkpoint {prior[-1]} (absent de ses ancêtres) — "
                "une tâche post-checkpoint ne doit jamais tourner sans la validation humaine"
            )

    # Checkpoints
    cps = [n for n in nodes if n.is_checkpoint]
    if not cps:
        warnings.append(
            "aucun checkpoint — un plan sans pause humaine viole CLAUDE.md (hard rules)"
        )
    dependents = {n.id: [m.id for m in nodes if n.id in m.depends_on] for n in nodes}
    for cp in cps:
        if not cp.depends_on:
            warnings.append(
                f"{cp.id} : trigger non parsé — ajoute « trigger : auto quand [Tn, Tm] done »"
            )
        is_sink = not dependents[cp.id]
        mentions_merge = "merge" in (cp.title + " ").lower()
        if cp.mode == "auto" and (is_sink or mentions_merge):
            errors.append(
                f"{cp.id} : un checkpoint final/merge ne peut pas être mode auto — le merge est humain, toujours"
            )

    # Séparation des devoirs : un même modèle ne devrait pas implémenter ET arbitrer seul
    if REGISTRY.models:
        impl = REGISTRY.role_default("implementer")
        rev = REGISTRY.role_default("reviewer")
        if impl and impl == rev:
            warnings.append(
                f"séparation des devoirs : reviewer et implementer pointent le même modèle ({impl}) — "
                "un checkpoint auto ne pourra pas s'auto-valider (basculera en humain). "
                "Assigne un modèle reviewer distinct dans models/registry.toml."
            )

    # Modèles : un override de tâche doit désigner un modèle éligible pour son rôle
    if REGISTRY.models:
        for n in nodes:
            if not n.model:
                continue
            role = "reviewer" if n.is_checkpoint else "implementer"
            m = REGISTRY.by_id(n.model)
            if m is None:
                warnings.append(
                    f"{n.id} : modèle « {n.model} » absent du registre (models/registry.toml)"
                )
            elif role not in m.roles:
                msg = f"{n.id} : modèle « {n.model} » non éligible au rôle {role} (registre : {m.roles})"
                # M9 — un implementer ineligible TOURNERAIT quand même (la résolution ne filtre
                # pas) : c'est une erreur bloquante. Le reviewer, lui, s'auto-corrige via
                # eligible() dans pick_reviewer_models → simple avertissement.
                (errors if role == "implementer" else warnings).append(msg)

    return errors, warnings


# ---------------------------------------------------------------- exécution


def _gchat(msg: str) -> None:
    """Notification Google Chat (opt-in). No-op si LAB_GCHAT_WEBHOOK absent ; ne crashe jamais.
    Permet à une squad (et pas seulement l'Owner devant son Mac) de voir checkpoints/blocages."""
    url = os.environ.get("LAB_GCHAT_WEBHOOK")
    if not url:
        return
    try:
        import json as _json
        import urllib.request

        req = urllib.request.Request(
            url,
            data=_json.dumps({"text": f"[Lab IA-natif] {msg}"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def notify(msg: str) -> None:
    print(f"🔔 {msg}", flush=True)
    _gchat(msg)
    if os.environ.get("LAB_NO_NOTIFY"):  # tests / CI : pas de notif macOS
        return
    try:
        # H2 — msg peut contenir du texte émis par un modèle (raison de STATUS, titre de
        # tâche) : on le passe en ARGUMENT à osascript (`on run {msg}`), jamais interpolé dans
        # le source AppleScript — sinon un `"` + `do shell script` = exécution arbitraire.
        subprocess.run(
            [
                "osascript",
                "-e",
                'on run {msg}\ndisplay notification msg with title "Lab IA-natif" sound name "Glass"\nend run',
                msg,
            ],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


def run_log(feature: Path, node: Node, agent: str, result: str) -> None:
    line = f"| {datetime.now():%Y-%m-%d %H:%M} | {node.id} | {agent} | {result} | |\n"
    with LOG_LOCK, (feature / "tasks.md").open("a", encoding="utf-8") as f:
        f.write(line)


def journal(feature: Path, **event) -> None:
    """Télémétrie du run : une ligne JSON par événement dans .runs/journal.jsonl."""
    event["ts"] = datetime.now().isoformat(timespec="seconds")
    path = feature / ".runs" / "journal.jsonl"
    with LOG_LOCK:
        path.parent.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_claude(
    prompt: str, resume: str | None = None, model: str | None = None
) -> dict:
    """Appel claude headless. Retourne {ok, text, session_id, cost_usd, error}.

    Mur wall-clock TASK_TIMEOUT_S : un agent coincé ne bloque jamais sa vague
    indéfiniment. Sortie --output-format json : texte du résultat, session_id
    (pour reprendre la MÊME session au retry au lieu de repartir de zéro) et
    coût, agrégé dans COST_TOTAL pour le bilan de delivery.
    model : --model passé tel quel (défaut CLI si None).
    """
    cmd = ["claude", "-p", prompt, *CLAUDE_ARGS]
    if model:
        cmd += ["--model", model]
    if resume:
        cmd += ["--resume", resume]
    try:
        p = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=TASK_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "text": "",
            "session_id": None,
            "cost_usd": 0.0,
            "error": f"timeout : agent tué après {TASK_TIMEOUT_S}s (LAB_TASK_TIMEOUT)",
        }
    if p.returncode != 0:
        return {
            "ok": False,
            "text": p.stdout,
            "session_id": None,
            "cost_usd": 0.0,
            "error": p.stderr[-2000:] or p.stdout[-2000:],
        }
    text, session_id, cost = p.stdout, None, 0.0
    try:
        data = json.loads(p.stdout)
        text = data.get("result") or ""
        session_id = data.get("session_id")
        cost = float(data.get("total_cost_usd") or 0.0)
    except (json.JSONDecodeError, TypeError):
        pass  # sortie non-JSON : on garde le texte brut
    with COST_LOCK:
        COST_TOTAL["usd"] += cost
    return {
        "ok": True,
        "text": text,
        "session_id": session_id,
        "cost_usd": cost,
        "error": "",
    }


def run_evals() -> tuple[bool, str]:
    p = subprocess.run(
        ["make", "-s", "evals"], cwd=ROOT, capture_output=True, text=True
    )
    return p.returncode == 0, (p.stdout + p.stderr)[-3000:]


def evals_collected() -> str:
    """Liste brute des evals collectées (`pytest --collect-only`).

    Sert l'anti-gate-vide (vide = rien à gater) ET la couverture par ID :
    la convention « nom de test contenant l'ID en minuscules » rend chaque
    EVAL-n de la spec vérifiable mécaniquement.
    LAB_EVALS_COLLECTED_FILE : seam de test (contenu lu tel quel).
    """
    hook = os.environ.get("LAB_EVALS_COLLECTED_FILE")
    if hook:
        p = Path(hook)
        return p.read_text(encoding="utf-8") if p.exists() else ""
    if not (ROOT / "pyproject.toml").exists():
        return ""
    p = subprocess.run(
        ["uv", "run", "pytest", "-m", "eval", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return p.stdout


def scoped_commit(node: Node, feature: Path, message: str) -> None:
    """Stage UNIQUEMENT les files_touched de la tâche + les artefacts de la feature
    (spec/design/tasks), sous verrou.

    H4/M12 — on ne stage JAMAIS les arbres `tests/`/`evals/` entiers ni le dossier feature
    complet : en vague parallèle, la première tâche finie aspirerait sinon les fichiers en
    cours d'une tâche sœur dans CE commit (traçabilité « 1 commit ↔ ses IDs » cassée). Tout
    fichier hors-scope déjà indexé est RETIRÉ de l'index avant le commit (pas seulement signalé).
    """
    with COMMIT_LOCK:
        feat_rel = str(feature.relative_to(ROOT))
        allowed = [
            *node.files,
            f"{feat_rel}/spec.md",
            f"{feat_rel}/design.md",
            f"{feat_rel}/tasks.md",
        ]
        for p in allowed:
            subprocess.run(["git", "add", "--", p], cwd=ROOT, capture_output=True)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.split()
        allowed_norm = [a.rstrip("/") for a in allowed]
        out = [
            f
            for f in staged
            if not any(f == a or f.startswith(a + "/") for a in allowed_norm)
        ]
        if out:
            print(
                f"⚠️  {node.id} : {len(out)} fichier(s) hors files_touched retiré(s) de l'index :",
                flush=True,
            )
            for f in out[:10]:
                print(f"     {f}", flush=True)
            # L-1 — sur un dépôt sans HEAD (tout premier commit), `git restore --staged` échoue
            # (rc 128) et laisserait le hors-scope indexé ; on retombe sur `git rm --cached`.
            has_head = (
                subprocess.run(
                    ["git", "rev-parse", "--verify", "-q", "HEAD"],
                    cwd=ROOT,
                    capture_output=True,
                ).returncode
                == 0
            )
            unstage = (
                ["git", "restore", "--staged", "--", *out]
                if has_head
                else ["git", "rm", "--cached", "-q", "--", *out]
            )
            subprocess.run(unstage, cwd=ROOT, capture_output=True)
        r = subprocess.run(
            ["git", "commit", "-m", message], cwd=ROOT, capture_output=True, text=True
        )
        if r.returncode != 0 and "nothing to commit" in (r.stdout + r.stderr):
            print(
                f"⚠️  {node.id} : rien à committer dans le scope — aucun commit créé",
                flush=True,
            )


def run_task(node: Node, feature: Path, dry: bool) -> str:
    """Retourne done | failed | blocked."""
    base_prompt = (
        f"Tu agis comme l'agent implementer (.claude/agents/implementer.md). "
        f"Lis {feature}/spec.md puis {feature}/design.md puis {feature}/tasks.md. "
        f"Exécute UNIQUEMENT la tâche {node.id} — {node.title}. "
        f"Respecte son scope files_touched et son done_when. "
        f"Si la spec est ambiguë ou trouée : n'invente pas, note la question (format OQ-n) dans spec.md §8 "
        f"et termine en blocked. "
        f"Termine IMPÉRATIVEMENT ta réponse par une ligne seule : "
        f"« STATUS: done » ou « STATUS: blocked — <raison, ex. OQ-3> ».\n{node.prompt}{node.rework}"
    )
    if dry:
        print(f"  [dry-run] claude -p '<prompt {node.id}>' {' '.join(CLAUDE_ARGS)}")
        return "done"

    real_ids = list(
        dict.fromkeys(s for t in node.implements for s in SPEC_ID.findall(t))
    )
    trace = f"[{', '.join(real_ids)}]" if real_ids else "[auto]"

    mid = resolve_model("implementer", node.model, REGISTRY)
    if REGISTRY.models and mid:  # M9 — un implementer ineligible ne doit pas tourner
        m = REGISTRY.by_id(mid)
        if m is not None and "implementer" not in m.roles:
            notify(
                f"{node.id} : modèle {mid} non éligible au rôle implementer (registre : {m.roles}) "
                "— tâche bloquée (corrige le **model :** ou models/registry.toml)."
            )
            journal(
                feature,
                event="task_blocked",
                id=node.id,
                reason=f"modèle {mid} ineligible implementer",
            )
            return "blocked"
    base_prompt += REGISTRY.profile_text(mid)
    if node.verify and not verify_allowed(node.verify):  # H1 — défense en profondeur
        notify(
            f"{node.id} : verify `{node.verify}` non vetté — tâche refusée (H1 ; corrige le plan)"
        )
        journal(feature, event="task_failed", id=node.id, reason="verify non vetté")
        return "failed"
    session: str | None = None
    extra = ""
    for attempt in range(1, MAX_EVAL_RETRIES + 1):
        print(f"▶ {node.id} (tentative {attempt}/{MAX_EVAL_RETRIES})", flush=True)
        t0 = time.monotonic()
        if session:
            # Retry dans la MÊME session : l'agent corrige son travail au lieu de refaire
            prompt = (
                f"Toujours sur la tâche {node.id} — {node.title}. Corrige sans tout réécrire :{extra}\n"
                f"Termine par « STATUS: done » ou « STATUS: blocked — <raison> »."
            )
        else:
            prompt = base_prompt + extra
        r = run_claude(prompt, resume=session, model=mid)
        journal(
            feature,
            event="task_attempt",
            id=node.id,
            attempt=attempt,
            model=mid,
            duration_s=round(time.monotonic() - t0, 1),
            cost_usd=r["cost_usd"],
            session=r["session_id"],
            ok=r["ok"],
        )
        if not r["ok"]:
            print(r["error"], file=sys.stderr)
            run_log(feature, node, "implementer", f"erreur claude (t{attempt})")
            session = None  # session inconnue/perdue : repartir propre
            continue
        session = r["session_id"] or session

        # M10 — prendre la DERNIÈRE ligne STATUS autonome (comme le parseur VERDICT) : sinon
        # une instruction « termine par STATUS: blocked » recopiée dans la prose inverserait
        # le verdict. Ancré en début de ligne (tolère une puce/citation markdown).
        sms = re.findall(r"(?im)^[\s>*\-]*STATUS:\s*(done|blocked)([^\n]*)$", r["text"])
        sm = sms[-1] if sms else None
        if sm and sm[0].lower() == "blocked":
            reason = sm[1].strip(" —-:") or "raison non précisée"
            run_log(feature, node, "implementer", f"BLOCKED — {reason}")
            journal(feature, event="task_blocked", id=node.id, reason=reason)
            notify(
                f"{node.id} bloquée : {reason} — réponse Owner attendue (spec.md §8)"
            )
            return "blocked"
        if not sm:
            print(
                f"⚠️  {node.id} : pas de ligne STATUS dans la réponse — on s'en remet aux evals",
                flush=True,
            )

        if node.verify:
            # H1 — exécution SANS shell : on tokenise (verify_allowed a déjà rejeté métacaractères
            # et exécutables hors liste), on extrait les assignations d'env en tête, et on lance la
            # liste d'arguments. Plus de shell = plus d'injection, et verify ≤ capacités de l'agent.
            vtoks = shlex.split(node.verify)
            venv: dict[str, str] = {}
            j = 0
            while j < len(vtoks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", vtoks[j]):
                k, _, val = vtoks[j].partition("=")
                venv[k] = val
                j += 1
            v = subprocess.run(
                vtoks[j:],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, **venv},
            )
            if v.returncode != 0:
                extra = f"\n\n⛔ verify a échoué (`{node.verify}`) :\n{(v.stdout + v.stderr)[-2000:]}"
                run_log(feature, node, "implementer", f"verify FAIL (t{attempt})")
                continue

        ok, out = run_evals()
        if ok and real_ids:
            collected = evals_collected()
            # M3/M4 — restreindre la couverture aux tests DU périmètre de la tâche. Sinon un
            # EVAL-2 d'une AUTRE feature (même numéro) satisfait la couverture par collision de
            # sous-chaîne, et l'anti-gate-vide n'est jamais par-tâche. Repli sur le dépôt entier
            # si la tâche ne déclare aucun chemin de test (ex. une CLI sans eval propre).
            scope = [
                f.rstrip("/") for f in node.files if f.startswith(("tests/", "evals/"))
            ]
            if scope:
                # M2 — frontière de chemin exacte : `tests/foo` ne doit PAS matcher `tests/foobar`.
                # nodeid pytest = `chemin::test`, donc on borne par `/` (répertoire) ou `::` (fichier).
                def _in_scope(ln: str) -> bool:
                    ln = ln.strip()
                    return any(
                        ln == s or ln.startswith(s + "/") or ln.startswith(s + "::")
                        for s in scope
                    )

                collected = "\n".join(
                    ln for ln in collected.splitlines() if _in_scope(ln)
                )
            if "::" not in collected:
                ok = False
                out = (
                    "Gate vide : `make evals` est vert mais AUCUNE eval n'est collectée alors que la tâche "
                    f"implémente {node.implements}. Écris les evals de spec.md §7 (pytest -m eval) — "
                    "pas d'eval, pas de done."
                )
            else:
                low = collected.lower()
                missing = [
                    i
                    for i in real_ids
                    if i.startswith("EVAL-") and i.lower().replace("-", "_") not in low
                ]
                if missing:
                    ok = False
                    out = (
                        f"Couverture eval incomplète : aucune eval collectée ne porte {missing}. "
                        f"Convention : nom de test contenant l'ID en minuscules, "
                        f"ex. test_{missing[0].lower().replace('-', '_')}_<cas>."
                    )
        if ok:
            run_log(feature, node, "implementer", f"done, evals vertes (t{attempt})")
            scoped_commit(
                node,
                feature,
                f"feat({feature.name}): {node.id} {node.title} {trace} [auto]",
            )
            journal(feature, event="task_done", id=node.id, attempts=attempt)
            return "done"
        extra = f"\n\n⛔ EVAL GATE ROUGE à la tentative précédente. Corrige :\n{out}"
        run_log(feature, node, "eval-runner", f"FAIL (t{attempt})")
    notify(f"{node.id} : {MAX_EVAL_RETRIES} échecs d'evals — escalade Owner")
    journal(feature, event="task_failed", id=node.id)
    return "failed"


REVIEW_LENSES = [
    "correction : le code fait-il ce que la spec dit (INV/BHV), valeurs et bornes comprises",
    "conformité spec/design : traçabilité, scope, respect des ADRs, pas de scope creep",
    "cas limites & robustesse : entrées extrêmes, erreurs, le livrable s'exécute-t-il vraiment",
]


def pick_reviewer_models(cp: Node, n: int) -> list[str | None]:
    """n modèles pour le panel. Séparation des devoirs : on préfère un modèle reviewer
    DIFFÉRENT de l'implementer (un modèle ne doit pas valider seul son propre travail)."""
    impl = resolve_model("implementer", "", REGISTRY)
    base = resolve_model("reviewer", cp.model, REGISTRY)
    pool = [m.id for m in REGISTRY.eligible("reviewer")] or ([base] if base else [None])
    # priorité aux modèles ≠ implementer, puis le reste
    ordered = [m for m in pool if m != impl] + [m for m in pool if m == impl]
    if base in ordered:  # garder le défaut de rôle en tête s'il est admissible
        ordered = [base] + [m for m in ordered if m != base]
    return [ordered[i % len(ordered)] for i in range(n)]


def _aggregate_verdict(verdicts: list[str]) -> str:
    if any(v == "BLOCK" for v in verdicts):
        return "BLOCK"
    if sum(v == "PASS" for v in verdicts) > len(verdicts) / 2:  # majorité stricte
        return "PASS"
    return "WARN"


def run_review(cp: Node, feature: Path, dry: bool) -> tuple[str, Path, bool]:
    """Panel de reviewers. Retourne (verdict_agrégé, rapport, self_review_only).
    self_review_only = True si tous les panelistes tournent sur le modèle de l'implementer
    (séparation des devoirs impossible → l'auto-validation sera refusée)."""
    report = feature / ".runs" / f"{cp.id}-review.md"
    if dry:
        print(f"  [dry-run] reviewer×{cp.reviewers} → {report}")
        return "PASS", report, False

    n = cp.reviewers
    models = pick_reviewer_models(cp, n)
    impl = resolve_model("implementer", "", REGISTRY)
    verdicts: list[str] = []
    sections: list[str] = []
    for i, mid in enumerate(models):
        lens = REVIEW_LENSES[i % len(REVIEW_LENSES)] if n > 1 else "revue complète"
        prompt = (
            f"Tu agis comme l'agent reviewer (.claude/agents/reviewer.md). Feature : {feature}. "
            f"Checkpoint {cp.id} — {cp.title}. Tâches couvertes : {', '.join(cp.depends_on) or 'toutes'}. "
            f"ANGLE DE REVUE imposé : {lens}. "
            f"Produis le rapport (✅/⚠️/❌ avec fichier:ligne) et termine IMPÉRATIVEMENT par une "
            f"ligne seule : « VERDICT: PASS », « VERDICT: WARN » ou « VERDICT: BLOCK »."
        ) + REGISTRY.profile_text(mid)
        r = run_claude(prompt, model=mid)
        vm = re.findall(r"VERDICT:\s*(PASS|WARN|BLOCK)", r["text"])
        v = vm[-1] if vm else "WARN"
        verdicts.append(v)
        sections.append(
            f"## Paneliste {i + 1} — {mid or 'défaut CLI'} — angle : {lens}\nVERDICT: {v}\n\n{r['text'] or r['error']}"
        )
        journal(
            feature,
            event="review",
            id=cp.id,
            model=mid,
            lens=lens,
            verdict=v,
            cost_usd=r["cost_usd"],
            ok=r["ok"],
        )

    agg = _aggregate_verdict(verdicts)
    self_only = impl is not None and all(m == impl for m in models)
    report.parent.mkdir(exist_ok=True)
    header = f"# Revue {cp.id} — panel de {n} — verdict agrégé : {agg} ({', '.join(verdicts)})\n\n"
    report.write_text(header + "\n\n---\n\n".join(sections), encoding="utf-8")
    return agg, report, self_only


def parse_rejection(path: Path) -> dict:
    info: dict = {"reason": "", "tasks": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("reason="):
            info["reason"] = line[len("reason=") :].strip()
        elif line.startswith("tasks="):
            info["tasks"] = line[len("tasks=") :].split()
    return info


def approvals_dir(feature: Path) -> Path:
    """Dossier des jetons d'approbation. LAB_APPROVALS_DIR le pointe vers un volume monté/partagé
    → l'Owner peut approuver depuis une AUTRE machine (run hors-Mac, en conteneur)."""
    d = os.environ.get("LAB_APPROVALS_DIR")
    return Path(d) if d else feature / ".approvals"


def wait_checkpoint(
    node: Node, feature: Path, dry: bool, supervised: bool
) -> tuple[str, dict]:
    """Retourne ("approved", {}) ou ("rejected", {reason, tasks})."""
    base = approvals_dir(feature)
    base.mkdir(parents=True, exist_ok=True)
    approval = base / node.id
    rejection = base / f"{node.id}.rejected"
    if dry:
        print(
            f"  [dry-run] CHECKPOINT {node.id} (mode {node.mode}) — attend {approval}"
        )
        return "approved", {}

    verdict, report, self_only = run_review(node, feature, dry)
    evals_ok, _ = run_evals()

    if node.mode == "auto" and not supervised:
        if self_only:
            notify(
                f"{node.id} (auto) : séparation des devoirs impossible (reviewer = modèle de l'implementer) "
                "→ validation humaine requise. Configure un modèle reviewer distinct dans models/registry.toml."
            )
        elif verdict == "PASS" and evals_ok:
            approval.parent.mkdir(exist_ok=True)
            approval.write_text(
                f"auto-approved (evals vertes + panel reviewer PASS) at={datetime.now().isoformat()}\n"
            )
            run_log(
                feature, node, "reviewer", "checkpoint auto-validé (PASS, evals vertes)"
            )
            notify(f"{node.id} auto-validé — rapport : {report.relative_to(ROOT)}")
            return "approved", {}
        else:
            notify(
                f"{node.id} (auto) : panel {verdict} / evals {'vertes' if evals_ok else 'ROUGES'} → bascule en validation humaine"
            )

    notify(
        f"CHECKPOINT {node.id} : décision Owner → scripts/approve.sh {node.id} {feature.relative_to(ROOT)} "
        f'ou scripts/reject.sh {node.id} {feature.relative_to(ROOT)} "raison" [Tn …] '
        f"(rapport reviewer : {report.relative_to(ROOT)}, verdict {verdict})"
    )
    print(f"⏸  {node.id} — en attente de {approval} (ou .rejected)", flush=True)
    while True:
        if rejection.exists():
            info = parse_rejection(rejection)
            rejection.rename(
                rejection.parent
                / f"{node.id}.rejected.handled-{datetime.now():%Y%m%d%H%M%S}"
            )
            run_log(feature, node, "owner", f"checkpoint REJETÉ — {info['reason']}")
            journal(feature, event="checkpoint_rejected", id=node.id, **info)
            notify(
                f"{node.id} rejeté — réouverture : {', '.join(info['tasks']) or 'toutes les tâches du checkpoint'}"
            )
            return "rejected", info
        if approval.exists():
            run_log(feature, node, "owner", "checkpoint validé")
            notify(f"{node.id} validé — reprise de l'exécution")
            return "approved", {}
        time.sleep(20)


def skip_dependents(failed: Node, nodes: list[Node]) -> None:
    """Confinement : seuls les dépendants (transitifs) d'un échec sont neutralisés."""
    by_id = {n.id: n for n in nodes}
    queue = [failed.id]
    while queue:
        cur = queue.pop()
        for n in nodes:
            if n.status == "pending" and cur in n.depends_on:
                n.status = "skipped"
                print(f"⏭  {n.id} skipped (dépend de {cur})", flush=True)
                queue.append(n.id)
    _ = by_id  # lisibilité


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("feature", help="dossier de la feature (contient tasks.md)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--validate", action="store_true", help="plan-lint : vérifie tasks.md et sort"
    )
    ap.add_argument(
        "--supervised",
        action="store_true",
        help="force tous les checkpoints en blocking",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="ignorer status approved + erreurs de lint (déconseillé)",
    )
    args = ap.parse_args()

    feature = (ROOT / args.feature).resolve()
    fm, nodes = parse_tasks_md(feature / "tasks.md")

    errors, warnings = validate(feature, fm, nodes)
    if args.validate or errors or warnings:
        print(
            f"Plan-lint — {len(nodes)} nœuds, status frontmatter : {fm.get('status', '∅')}"
        )
        for w in warnings:
            print(f"  ⚠️  {w}")
        for e in errors:
            print(f"  ❌ {e}")
        if not errors and not warnings:
            print("  ✅ aucun problème")
    if args.validate:
        return 1 if errors else 0
    if errors and not args.force:
        print("⛔ Plan invalide — corrige (ou --force, déconseillé).")
        return 1

    if fm.get("status") != "approved" and not (args.dry_run or args.force):
        print(
            f"⛔ tasks.md a status '{fm.get('status')}' — un plan doit être 'approved' par l'Owner avant exécution."
        )
        return 1

    by_id = {n.id: n for n in nodes}
    print(f"Plan : {len(nodes)} nœuds — " + ", ".join(n.id for n in nodes))
    if REGISTRY.models:
        roles_used = {
            "implementer": resolve_model("implementer", "", REGISTRY),
            "reviewer": resolve_model("reviewer", "", REGISTRY),
        }
        print(
            "Modèles (registre) : "
            + ", ".join(f"{r}={m or 'défaut CLI'}" for r, m in roles_used.items())
        )

    rejections: dict[str, int] = {}
    state_f = feature / ".runs" / "state.json"
    state_f.parent.mkdir(exist_ok=True)
    if state_f.exists() and not args.dry_run:
        for nid, st in json.loads(state_f.read_text()).items():
            if nid in by_id and st == "done":
                by_id[nid].status = "done"

    def save() -> None:
        if not args.dry_run:
            state_f.write_text(json.dumps({n.id: n.status for n in nodes}, indent=2))

    while any(n.status == "pending" for n in nodes):
        if BUDGET_USD and COST_TOTAL["usd"] >= BUDGET_USD:
            notify(
                f"⛔ Budget atteint : ${COST_TOTAL['usd']:.2f} ≥ ${BUDGET_USD:.2f} (LAB_BUDGET_USD) — "
                "arrêt avant la vague suivante. Relance après revue (reprise via .runs/state.json)."
            )
            journal(
                feature,
                event="budget_stop",
                spent_usd=round(COST_TOTAL["usd"], 4),
                cap_usd=BUDGET_USD,
            )
            return 1
        ready = [
            n
            for n in nodes
            if n.status == "pending"
            and all(by_id[d].status == "done" for d in n.depends_on if d in by_id)
        ]
        if not ready:
            print(
                "⛔ Deadlock : aucune tâche prête. Vérifie le graphe depends_on (--validate)."
            )
            return 1

        cps = [n for n in ready if n.is_checkpoint]
        tasks = [n for n in ready if not n.is_checkpoint]

        if tasks:
            wave = ", ".join(n.id for n in tasks)
            print(f"\n=== Vague parallèle : {wave} ===")
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
                futs = {}
                for n in tasks:
                    # M13 — plafond vérifié AVANT chaque soumission (pas seulement entre vagues) :
                    # borne le dépassement à ce qui tourne déjà, pas +MAX_PARALLEL agents.
                    if BUDGET_USD and COST_TOTAL["usd"] >= BUDGET_USD:
                        print(
                            f"⛔ Budget atteint avant {n.id} — non lancée (reste pending)",
                            flush=True,
                        )
                        continue
                    futs[ex.submit(run_task, n, feature, args.dry_run)] = n
                for fut in as_completed(futs):
                    n = futs[fut]
                    n.status = fut.result()
                    if n.status in ("failed", "blocked"):
                        skip_dependents(n, nodes)
                    save()
        for cp in cps:
            outcome, info = wait_checkpoint(cp, feature, args.dry_run, args.supervised)
            if outcome == "approved":
                cp.status = "done"
            else:  # rejected — on_reject : retour aux tâches concernées avec commentaire
                rejections[cp.id] = rejections.get(cp.id, 0) + 1
                if rejections[cp.id] > MAX_CP_REJECTS:
                    cp.status = "failed"
                    notify(
                        f"{cp.id} : rejeté {rejections[cp.id]} fois — arrêt, reprise manuelle requise"
                    )
                    skip_dependents(cp, nodes)
                else:
                    targets = info["tasks"] or list(cp.depends_on)
                    for tid in targets:
                        t = by_id.get(tid)
                        if t and not t.is_checkpoint:
                            t.status = "pending"
                            t.rework = (
                                f"\n\n⚠️ RETOUR DE REVUE OWNER (rejet {cp.id}) : {info['reason']}\n"
                                f"Corrige en conséquence avant de re-livrer."
                            )
                    cp.status = (
                        "pending"  # re-déclenché quand les tâches reviennent done
                    )
            save()

    bad = [n for n in nodes if n.status in ("failed", "blocked", "skipped")]
    print("\n=== Bilan ===")
    for n in nodes:
        mark = {"done": "✅", "failed": "❌", "blocked": "🛑", "skipped": "⏭"}.get(
            n.status, "·"
        )
        print(f"  {mark} {n.id} — {n.status}")
    print(f"  Σ coût agents : ${COST_TOTAL['usd']:.2f} (détail : .runs/journal.jsonl)")
    journal(
        feature,
        event="run_end",
        cost_usd_total=round(COST_TOTAL["usd"], 4),
        statuses={n.id: n.status for n in nodes},
    )
    if bad:
        notify(
            f"{feature.name} : run terminé avec {len(bad)} nœud(s) non done — "
            "réponds aux blocages puis relance (reprise via .runs/state.json)."
        )
        return 1
    notify(
        f"🎉 {feature.name} : toutes les tâches sont done. Merge = décision humaine (CP final)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
