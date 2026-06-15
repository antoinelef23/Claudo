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
  - commits scopés : on ne stage que les files_touched de la tâche (+ tests/, evals/,
    le dossier feature) sous verrou — jamais de `git add -A` en vague parallèle

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

        nodes.append(node)

    # Chaque tâche dépend implicitement de tout checkpoint défini avant elle
    last_cp: str | None = None
    for n in nodes:
        if n.is_checkpoint:
            last_cp = n.id
        elif last_cp and last_cp not in n.depends_on and not n.depends_on:
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
                warnings.append(
                    f"{n.id} : modèle « {n.model} » non éligible au rôle {role} (registre : {m.roles})"
                )

    return errors, warnings


# ---------------------------------------------------------------- exécution


def notify(msg: str) -> None:
    print(f"🔔 {msg}", flush=True)
    if os.environ.get("LAB_NO_NOTIFY"):  # tests / CI
        return
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{msg}" with title "Lab IA-natif" sound name "Glass"',
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
    coût, agrégé dans COST_TOTAL pour le bilan (métrique Twin Track).
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
    """Stage uniquement le périmètre de la tâche, sous verrou (vagues parallèles)."""
    with COMMIT_LOCK:
        paths = [*node.files, "tests", "evals", str(feature.relative_to(ROOT))]
        for p in paths:
            subprocess.run(["git", "add", "--", p], cwd=ROOT, capture_output=True)
        leftover = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        ).stdout
        out_of_scope = [
            line
            for line in leftover.splitlines()
            if line and not line.startswith(("A ", "M ", "R ", "D "))
        ]
        if out_of_scope:
            print(
                f"⚠️  {node.id} : modifications hors files_touched laissées non commitées :",
                flush=True,
            )
            for line in out_of_scope[:10]:
                print(f"     {line}", flush=True)
        subprocess.run(["git", "commit", "-m", message], cwd=ROOT, capture_output=True)


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
    base_prompt += REGISTRY.profile_text(mid)
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

        sm = re.search(r"STATUS:\s*(done|blocked)([^\n]*)", r["text"], re.I)
        if sm and sm.group(1).lower() == "blocked":
            reason = sm.group(2).strip(" —-:") or "raison non précisée"
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
            v = subprocess.run(
                node.verify, shell=True, cwd=ROOT, capture_output=True, text=True
            )
            if v.returncode != 0:
                extra = f"\n\n⛔ verify a échoué (`{node.verify}`) :\n{(v.stdout + v.stderr)[-2000:]}"
                run_log(feature, node, "implementer", f"verify FAIL (t{attempt})")
                continue

        ok, out = run_evals()
        if ok and real_ids:
            collected = evals_collected()
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


def run_review(cp: Node, feature: Path, dry: bool) -> tuple[str, Path]:
    """Dossier de revue par l'agent reviewer. Retourne (PASS|WARN|BLOCK, chemin du rapport)."""
    report = feature / ".runs" / f"{cp.id}-review.md"
    if dry:
        print(f"  [dry-run] reviewer → {report}")
        return "PASS", report
    prompt = (
        f"Tu agis comme l'agent reviewer (.claude/agents/reviewer.md). Feature : {feature}. "
        f"Checkpoint {cp.id} — {cp.title}. Tâches couvertes : {', '.join(cp.depends_on) or 'toutes'}. "
        f"Produis le rapport de revue (✅/⚠️/❌ avec fichier:ligne) et termine IMPÉRATIVEMENT par une "
        f"ligne seule : « VERDICT: PASS » (aucun écart), « VERDICT: WARN » ou « VERDICT: BLOCK »."
    )
    mid = resolve_model("reviewer", cp.model, REGISTRY)
    prompt += REGISTRY.profile_text(mid)
    r = run_claude(prompt, model=mid)
    report.parent.mkdir(exist_ok=True)
    report.write_text(r["text"] or r["error"], encoding="utf-8")
    vm = re.findall(r"VERDICT:\s*(PASS|WARN|BLOCK)", r["text"])
    verdict = vm[-1] if vm else "WARN"
    journal(
        feature,
        event="review",
        id=cp.id,
        model=mid,
        verdict=verdict,
        cost_usd=r["cost_usd"],
        ok=r["ok"],
    )
    return verdict, report


def parse_rejection(path: Path) -> dict:
    info: dict = {"reason": "", "tasks": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("reason="):
            info["reason"] = line[len("reason=") :].strip()
        elif line.startswith("tasks="):
            info["tasks"] = line[len("tasks=") :].split()
    return info


def wait_checkpoint(
    node: Node, feature: Path, dry: bool, supervised: bool
) -> tuple[str, dict]:
    """Retourne ("approved", {}) ou ("rejected", {reason, tasks})."""
    approval = feature / ".approvals" / node.id
    rejection = feature / ".approvals" / f"{node.id}.rejected"
    if dry:
        print(
            f"  [dry-run] CHECKPOINT {node.id} (mode {node.mode}) — attend {approval}"
        )
        return "approved", {}

    verdict, report = run_review(node, feature, dry)
    evals_ok, _ = run_evals()

    if node.mode == "auto" and not supervised:
        if verdict == "PASS" and evals_ok:
            approval.parent.mkdir(exist_ok=True)
            approval.write_text(
                f"auto-approved (evals vertes + reviewer PASS) at={datetime.now().isoformat()}\n"
            )
            run_log(
                feature, node, "reviewer", "checkpoint auto-validé (PASS, evals vertes)"
            )
            notify(f"{node.id} auto-validé — rapport : {report.relative_to(ROOT)}")
            return "approved", {}
        notify(
            f"{node.id} (auto) : reviewer {verdict} / evals {'vertes' if evals_ok else 'ROUGES'} → bascule en validation humaine"
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
                futs = {ex.submit(run_task, n, feature, args.dry_run): n for n in tasks}
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
