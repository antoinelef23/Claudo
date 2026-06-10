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
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_EVAL_RETRIES = 3
MAX_PARALLEL = 3
CLAUDE_ARGS = [
    "--permission-mode", "acceptEdits", "--max-turns", "100",
    # headless : acceptEdits couvre les éditions, pas Bash — whitelist minimale pour
    # que l'implementer puisse exécuter ses tests (sinon il code à l'aveugle)
    "--allowedTools", "Bash(uv:*),Bash(make:*),Bash(python3:*),Bash(mkdir:*),Bash(ls:*),Bash(git diff:*),Bash(git log:*)",
]
SPEC_ID = re.compile(r"\b(?:INV|BHV|EX|EVAL|NG)-[A-Za-z0-9]+\b")

COMMIT_LOCK = threading.Lock()


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
            tm = re.search(r"\*\*trigger\s*:?\*\*[^\n]*?quand\s+\[?([T\d\s,]+?)\]?\s+(?:sont\s+)?done", body)
            if tm:
                deps = [d.strip() for d in tm.group(1).split(",") if d.strip()]

        pm = re.search(r"\*\*prompt\s*:?\*\*\s*\n?((?:\s*>.*\n?)+)", body)
        prompt = ""
        if pm:
            prompt = "\n".join(l.strip().lstrip("> ") for l in pm.group(1).splitlines()).strip()
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
            errors.append(f"{n.id} : done_when manquant (rien d'exécutable ne définit « fini »)")
        if not n.files:
            errors.append(f"{n.id} : files_touched manquant ou sans backticks (parallélisme invérifiable)")
        if not n.prompt:
            warnings.append(f"{n.id} : prompt vide — l'implementer n'aura que le titre")
        if not n.verify:
            warnings.append(f"{n.id} : pas de verify exécutable — le done_when ne sera pas vérifié mécaniquement")

    # IDs de spec
    spec_path = feature / "spec.md"
    if spec_path.exists():
        spec_text = spec_path.read_text(encoding="utf-8")
        for n in nodes:
            for tok in n.implements:
                for sid in SPEC_ID.findall(tok):
                    if sid not in spec_text:
                        errors.append(f"{n.id} : implémente [{sid}] introuvable dans spec.md")
    else:
        errors.append("spec.md introuvable à côté de tasks.md")

    # Sécurité du parallélisme : deux tâches non ordonnées ne partagent aucun chemin
    anc = _ancestors(nodes)
    tasks = [n for n in nodes if not n.is_checkpoint]
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            if a.id in anc[b.id] or b.id in anc[a.id]:
                continue  # ordonnées par le DAG
            clash = [(fa, fb) for fa in a.files for fb in b.files if _paths_overlap(fa, fb)]
            if clash:
                errors.append(
                    f"{a.id} ∥ {b.id} : exécutables en parallèle mais files_touched se recouvrent "
                    f"({clash[0][0]} ↔ {clash[0][1]}) — ajoute un depends_on ou sépare les chemins"
                )

    # Checkpoints
    cps = [n for n in nodes if n.is_checkpoint]
    if not cps:
        warnings.append("aucun checkpoint — un plan sans pause humaine viole CLAUDE.md (hard rules)")
    dependents = {n.id: [m.id for m in nodes if n.id in m.depends_on] for n in nodes}
    for cp in cps:
        if not cp.depends_on:
            warnings.append(f"{cp.id} : trigger non parsé — ajoute « trigger : auto quand [Tn, Tm] done »")
        is_sink = not dependents[cp.id]
        mentions_merge = "merge" in (cp.title + " ").lower()
        if cp.mode == "auto" and (is_sink or mentions_merge):
            errors.append(f"{cp.id} : un checkpoint final/merge ne peut pas être mode auto — le merge est humain, toujours")

    return errors, warnings


# ---------------------------------------------------------------- exécution


def notify(msg: str) -> None:
    print(f"🔔 {msg}", flush=True)
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{msg}" with title "Lab IA-natif" sound name "Glass"'],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


def run_log(feature: Path, node: Node, agent: str, result: str) -> None:
    line = f"| {datetime.now():%Y-%m-%d %H:%M} | {node.id} | {agent} | {result} | |\n"
    with (feature / "tasks.md").open("a", encoding="utf-8") as f:
        f.write(line)


def run_evals() -> tuple[bool, str]:
    p = subprocess.run(["make", "-s", "evals"], cwd=ROOT, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr)[-3000:]


def count_evals() -> int:
    """Nombre d'evals réellement collectées — anti-gate-vide."""
    if not (ROOT / "pyproject.toml").exists():
        return 0
    p = subprocess.run(
        ["uv", "run", "pytest", "-m", "eval", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return p.stdout.count("::")


def scoped_commit(node: Node, feature: Path, message: str) -> None:
    """Stage uniquement le périmètre de la tâche, sous verrou (vagues parallèles)."""
    with COMMIT_LOCK:
        paths = [*node.files, "tests", "evals", str(feature.relative_to(ROOT))]
        for p in paths:
            subprocess.run(["git", "add", "--", p], cwd=ROOT, capture_output=True)
        leftover = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        ).stdout
        out_of_scope = [l for l in leftover.splitlines() if l and not l.startswith(("A ", "M ", "R ", "D "))]
        if out_of_scope:
            print(f"⚠️  {node.id} : modifications hors files_touched laissées non commitées :", flush=True)
            for l in out_of_scope[:10]:
                print(f"     {l}", flush=True)
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
        f"« STATUS: done » ou « STATUS: blocked — <raison, ex. OQ-3> ».\n{node.prompt}"
    )
    if dry:
        print(f"  [dry-run] claude -p '<prompt {node.id}>' {' '.join(CLAUDE_ARGS)}")
        return "done"

    extra = ""
    for attempt in range(1, MAX_EVAL_RETRIES + 1):
        print(f"▶ {node.id} (tentative {attempt}/{MAX_EVAL_RETRIES})", flush=True)
        p = subprocess.run(
            ["claude", "-p", base_prompt + extra, *CLAUDE_ARGS],
            cwd=ROOT, capture_output=True, text=True,
        )
        if p.returncode != 0:
            print(p.stderr[-2000:], file=sys.stderr)
            run_log(feature, node, "implementer", f"erreur claude (t{attempt})")
            continue

        sm = re.search(r"STATUS:\s*(done|blocked)([^\n]*)", p.stdout, re.I)
        if sm and sm.group(1).lower() == "blocked":
            reason = sm.group(2).strip(" —-:") or "raison non précisée"
            run_log(feature, node, "implementer", f"BLOCKED — {reason}")
            notify(f"{node.id} bloquée : {reason} — réponse Owner attendue (spec.md §8)")
            return "blocked"
        if not sm:
            print(f"⚠️  {node.id} : pas de ligne STATUS dans la réponse — on s'en remet aux evals", flush=True)

        if node.verify:
            v = subprocess.run(node.verify, shell=True, cwd=ROOT, capture_output=True, text=True)
            if v.returncode != 0:
                extra = f"\n\n⛔ verify a échoué (`{node.verify}`) :\n{(v.stdout + v.stderr)[-2000:]}"
                run_log(feature, node, "implementer", f"verify FAIL (t{attempt})")
                continue

        ok, out = run_evals()
        if ok and any(SPEC_ID.search(t) for t in node.implements) and count_evals() == 0:
            ok = False
            out = (
                "Gate vide : `make evals` est vert mais AUCUNE eval n'est collectée alors que la tâche "
                f"implémente {node.implements}. Écris les evals de spec.md §7 (pytest -m eval) — "
                "pas d'eval, pas de done."
            )
        if ok:
            run_log(feature, node, "implementer", f"done, evals vertes (t{attempt})")
            scoped_commit(node, feature, f"feat({feature.name}): {node.id} {node.title} [auto]")
            return "done"
        extra = f"\n\n⛔ EVAL GATE ROUGE à la tentative précédente. Corrige :\n{out}"
        run_log(feature, node, "eval-runner", f"FAIL (t{attempt})")
    notify(f"{node.id} : {MAX_EVAL_RETRIES} échecs d'evals — escalade Owner")
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
    p = subprocess.run(["claude", "-p", prompt, *CLAUDE_ARGS], cwd=ROOT, capture_output=True, text=True)
    report.parent.mkdir(exist_ok=True)
    report.write_text(p.stdout or p.stderr, encoding="utf-8")
    vm = re.findall(r"VERDICT:\s*(PASS|WARN|BLOCK)", p.stdout)
    return (vm[-1] if vm else "WARN"), report


def wait_checkpoint(node: Node, feature: Path, dry: bool, supervised: bool) -> bool:
    approval = feature / ".approvals" / node.id
    if dry:
        print(f"  [dry-run] CHECKPOINT {node.id} (mode {node.mode}) — attend {approval}")
        return True

    verdict, report = run_review(node, feature, dry)
    evals_ok, _ = run_evals()

    if node.mode == "auto" and not supervised:
        if verdict == "PASS" and evals_ok:
            approval.parent.mkdir(exist_ok=True)
            approval.write_text(f"auto-approved (evals vertes + reviewer PASS) at={datetime.now().isoformat()}\n")
            run_log(feature, node, "reviewer", "checkpoint auto-validé (PASS, evals vertes)")
            notify(f"{node.id} auto-validé — rapport : {report.relative_to(ROOT)}")
            return True
        notify(f"{node.id} (auto) : reviewer {verdict} / evals {'vertes' if evals_ok else 'ROUGES'} → bascule en validation humaine")

    notify(
        f"CHECKPOINT {node.id} : validation Owner requise → scripts/approve.sh {node.id} {feature.relative_to(ROOT)} "
        f"(rapport reviewer : {report.relative_to(ROOT)}, verdict {verdict})"
    )
    print(f"⏸  {node.id} — en attente de {approval}", flush=True)
    while not approval.exists():
        time.sleep(20)
    run_log(feature, node, "owner", "checkpoint validé")
    notify(f"{node.id} validé — reprise de l'exécution")
    return True


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
    ap.add_argument("--validate", action="store_true", help="plan-lint : vérifie tasks.md et sort")
    ap.add_argument("--supervised", action="store_true", help="force tous les checkpoints en blocking")
    ap.add_argument("--force", action="store_true", help="ignorer status approved + erreurs de lint (déconseillé)")
    args = ap.parse_args()

    feature = (ROOT / args.feature).resolve()
    fm, nodes = parse_tasks_md(feature / "tasks.md")

    errors, warnings = validate(feature, fm, nodes)
    if args.validate or errors or warnings:
        print(f"Plan-lint — {len(nodes)} nœuds, status frontmatter : {fm.get('status', '∅')}")
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
        print(f"⛔ tasks.md a status '{fm.get('status')}' — un plan doit être 'approved' par l'Owner avant exécution.")
        return 1

    by_id = {n.id: n for n in nodes}
    print(f"Plan : {len(nodes)} nœuds — " + ", ".join(n.id for n in nodes))

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
            n for n in nodes
            if n.status == "pending" and all(by_id[d].status == "done" for d in n.depends_on if d in by_id)
        ]
        if not ready:
            print("⛔ Deadlock : aucune tâche prête. Vérifie le graphe depends_on (--validate).")
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
            cp.status = "done" if wait_checkpoint(cp, feature, args.dry_run, args.supervised) else "failed"
            if cp.status == "failed":
                skip_dependents(cp, nodes)
            save()

    bad = [n for n in nodes if n.status in ("failed", "blocked", "skipped")]
    print("\n=== Bilan ===")
    for n in nodes:
        mark = {"done": "✅", "failed": "❌", "blocked": "🛑", "skipped": "⏭"}.get(n.status, "·")
        print(f"  {mark} {n.id} — {n.status}")
    if bad:
        notify(
            f"{feature.name} : run terminé avec {len(bad)} nœud(s) non done — "
            "réponds aux blocages puis relance (reprise via .runs/state.json)."
        )
        return 1
    notify(f"🎉 {feature.name} : toutes les tâches sont done. Merge = décision humaine (CP final).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
