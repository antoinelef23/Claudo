#!/usr/bin/env python3
"""Orchestrateur de fond du lab IA-natif.

Lit le tasks.md d'une feature, construit le DAG (depends_on), exécute les tâches
prêtes EN PARALLÈLE via `claude -p` (headless), passe le gate d'evals après chaque
tâche (max 3 itérations), et se met EN PAUSE à chaque CHECKPOINT en notifiant
l'Owner (notification macOS). La validation d'un checkpoint reste humaine :
    scripts/approve.sh CP-1 <feature_dir>

Usage :
    python3 scripts/orchestrate.py examples/agent-douche --dry-run   # montre le plan
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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_EVAL_RETRIES = 3
MAX_PARALLEL = 3
CLAUDE_ARGS = ["--permission-mode", "acceptEdits", "--max-turns", "100"]


@dataclass
class Node:
    id: str
    title: str
    is_checkpoint: bool
    depends_on: list[str] = field(default_factory=list)
    prompt: str = ""
    status: str = "pending"  # pending | running | done | failed | waiting_approval


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

        pm = re.search(r"\*\*prompt\s*:?\*\*\s*\n((?:\s*>.*\n?)+)", body)
        prompt = ""
        if pm:
            prompt = "\n".join(l.strip().lstrip("> ") for l in pm.group(1).splitlines()).strip()

        nodes.append(Node(nid, title, is_cp, deps, prompt))

    # Chaque tâche dépend implicitement de tout checkpoint défini avant elle
    last_cp: str | None = None
    for n in nodes:
        if n.is_checkpoint:
            last_cp = n.id
        elif last_cp and last_cp not in n.depends_on and not n.depends_on:
            n.depends_on.append(last_cp)
    return fm, nodes


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


def run_task(node: Node, feature: Path, dry: bool) -> bool:
    base_prompt = (
        f"Tu agis comme l'agent implementer (.claude/agents/implementer.md). "
        f"Lis {feature}/spec.md puis {feature}/design.md puis {feature}/tasks.md. "
        f"Exécute UNIQUEMENT la tâche {node.id} — {node.title}. "
        f"Respecte son scope files_touched et son done_when.\n{node.prompt}"
    )
    if dry:
        print(f"  [dry-run] claude -p '<prompt {node.id}>' {' '.join(CLAUDE_ARGS)}")
        return True

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
        ok, out = run_evals()
        if ok:
            run_log(feature, node, "implementer", f"done, evals vertes (t{attempt})")
            subprocess.run(["git", "add", "-A"], cwd=ROOT)
            subprocess.run(["git", "commit", "-m", f"feat({feature.name}): {node.id} {node.title} [auto]"], cwd=ROOT)
            return True
        extra = f"\n\n⛔ EVAL GATE ROUGE à la tentative précédente. Corrige :\n{out}"
        run_log(feature, node, "eval-runner", f"FAIL (t{attempt})")
    notify(f"{node.id} : 3 échecs d'evals — escalade Owner")
    return False


def wait_checkpoint(node: Node, feature: Path, dry: bool) -> bool:
    approval = feature / ".approvals" / node.id
    if dry:
        print(f"  [dry-run] PAUSE checkpoint {node.id} — attend {approval}")
        return True
    notify(f"CHECKPOINT {node.id} : validation Owner requise → scripts/approve.sh {node.id} {feature}")
    print(f"⏸  {node.id} — en attente de {approval}", flush=True)
    while not approval.exists():
        time.sleep(20)
    run_log(feature, node, "owner", "checkpoint validé")
    notify(f"{node.id} validé — reprise de l'exécution")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("feature", help="dossier de la feature (contient tasks.md)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignorer le status approved (déconseillé)")
    args = ap.parse_args()

    feature = (ROOT / args.feature).resolve()
    fm, nodes = parse_tasks_md(feature / "tasks.md")

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
            print("⛔ Deadlock : aucune tâche prête. Vérifie le graphe depends_on.")
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
                    n.status = "done" if fut.result() else "failed"
                    save()
        for cp in cps:
            cp.status = "done" if wait_checkpoint(cp, feature, args.dry_run) else "failed"
            save()

        if any(n.status == "failed" for n in nodes):
            print("⛔ Arrêt : une tâche a échoué après escalade. Reprends avec le même état (.runs/state.json).")
            return 1

    notify(f"🎉 {feature.name} : toutes les tâches sont done. Merge = décision humaine (CP final).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
