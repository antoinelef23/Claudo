"""Suite de régression de l'orchestrateur — rejoue la campagne de simulation
du 2026-06-10 (devis-pose / export-devis) en secondes, avec le shim claude.
"""

from __future__ import annotations

import json
from pathlib import Path

from .conftest import approve, run_orch

FM = """---
artifact: tasks
feature: feat
status: approved
---

# Tasks — feat
"""


def write_tasks(sandbox: Path, body: str) -> None:
    (sandbox / "work" / "feat" / "tasks.md").write_text(FM + body)


def state(sandbox: Path) -> dict:
    return json.loads((sandbox / "work" / "feat" / ".runs" / "state.json").read_text())


def journal_events(sandbox: Path) -> list[dict]:
    p = sandbox / "work" / "feat" / ".runs" / "journal.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()]


# ---------------------------------------------------------------- plan-lint


def test_lint_catches_all_error_classes(sandbox: Path) -> None:
    write_tasks(
        sandbox,
        """
### T1 — A
- **depends_on :** [T9]
- **implements :** [BHV-99]
- **files_touched :** `src/core/`
- **done_when :** ok
- **verify :** `true`

### T2 — B (overlap avec T1)
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `src/core/sub/`
- **done_when :** ok
- **verify :** `true`

### T3 — C sans done_when ni files

### CP-1 — CHECKPOINT : merge final
- **trigger :** auto quand [T1, T2, T3] done
- **validator :** Owner
- **mode :** auto
""",
    )
    r = run_orch(sandbox, "--validate")
    assert r.returncode == 1
    for needle in [
        "depends_on [T9] inexistant",
        "[BHV-99] introuvable",
        "T3 : done_when manquant",
        "T3 : files_touched manquant",
        "files_touched se recouvrent",
        "ne peut pas être mode auto",
    ]:
        assert needle in r.stdout, f"lint devrait signaler : {needle}\n{r.stdout}"


def test_lint_catches_cycle(sandbox: Path) -> None:
    write_tasks(
        sandbox,
        """
### T1 — A
- **depends_on :** [T2]
- **files_touched :** `a/`
- **done_when :** ok
- **verify :** `true`

### T2 — B
- **depends_on :** [T1]
- **files_touched :** `b/`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox, "--validate")
    assert r.returncode == 1
    assert "cycle de dépendances" in r.stdout


def test_dry_run_wave_order(sandbox: Path) -> None:
    write_tasks(
        sandbox,
        """
### T1 — Socle
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### T2 — Suite
- **depends_on :** [T1]
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox, "--dry-run")
    assert r.returncode == 0
    assert r.stdout.index("Vague parallèle : T1") < r.stdout.index(
        "Vague parallèle : T2"
    )


# ---------------------------------------------------------------- exécution


def test_happy_run_with_auto_checkpoint(sandbox: Path) -> None:
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo "données" > t1.txt\necho "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Produit un fichier
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** fichier présent
- **verify :** `test -f t1.txt`

### CP-1 — CHECKPOINT : vérification mécanique
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** auto

### T2 — Étape finale
- **depends_on :** [CP-1]
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`

### CP-2 — CHECKPOINT : merge
- **trigger :** auto quand T2 done
- **validator :** Owner
- **mode :** blocking
""",
    )
    approve(sandbox, "CP-2")  # pré-approuvé : le test ne doit pas attendre un humain
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(sandbox) == {
        "T1": "done",
        "CP-1": "done",
        "T2": "done",
        "CP-2": "done",
    }
    # CP-1 auto-validé sans humain, sur la foi du reviewer shim (PASS) + evals stub
    auto = (sandbox / "work" / "feat" / ".approvals" / "CP-1").read_text()
    assert "auto-approved" in auto
    # journal : tentatives, done, reviews, coût agrégé
    kinds = [e["event"] for e in journal_events(sandbox)]
    assert kinds.count("task_done") == 2 and "review" in kinds and "run_end" in kinds
    # commit scopé traçable
    import subprocess

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=sandbox, capture_output=True, text=True
    ).stdout
    assert "T1 Produit un fichier" in log and "[auto]" in log


def test_blocked_containment_and_resume(sandbox: Path) -> None:
    # T1 compte ses exécutions (preuve de non-rejeu à la reprise) ; T2 bloque sur OQ-1
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo x >> .shim/t1_count\necho "STATUS: done"\n'
    )
    (sandbox / ".shim" / "T2.sh").write_text('echo "STATUS: blocked — OQ-1 ouverte"\n')
    write_tasks(
        sandbox,
        """
### T1 — Branche indépendante
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### T2 — Bloquée par OQ-1
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`

### T3 — Dépend de T2
- **depends_on :** [T2]
- **implements :** [doc]
- **files_touched :** `t3.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : final
- **trigger :** auto quand [T1, T3] done
- **validator :** Owner
- **mode :** blocking
""",
    )
    approve(sandbox, "CP-1")
    r = run_orch(sandbox)
    assert r.returncode == 1
    assert state(sandbox) == {
        "T1": "done",
        "T2": "blocked",
        "T3": "skipped",
        "CP-1": "skipped",
    }
    assert any(e["event"] == "task_blocked" for e in journal_events(sandbox))

    # Reprise : l'Owner « résout l'OQ » (scénario T2 passe à done) — T1 ne rejoue pas
    (sandbox / ".shim" / "T2.sh").write_text('echo "STATUS: done"\n')
    r2 = run_orch(sandbox)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert state(sandbox) == {"T1": "done", "T2": "done", "T3": "done", "CP-1": "done"}
    assert (sandbox / ".shim" / "t1_count").read_text().count("x") == 1


def test_eval_gate_retry_recovers(sandbox: Path) -> None:
    # Evals rouges au 1er passage ; le scénario T1 les « répare » à la 2e tentative
    (sandbox / ".evals_fail").write_text("")
    (sandbox / ".shim" / "T1.sh").write_text(
        "echo x >> .shim/count\n"
        '[ "$(grep -c x .shim/count)" -ge 2 ] && rm -f .evals_fail\n'
        'echo "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — Répare ses evals
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    done = [e for e in journal_events(sandbox) if e["event"] == "task_done"]
    assert done and done[0]["attempts"] == 2


def test_checkpoint_reject_reopens_tasks(sandbox: Path) -> None:
    # Le rejet pré-déposé est consommé en premier : T1 réouvert avec le commentaire
    # Owner, puis le checkpoint se re-présente et trouve l'approbation.
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo x >> .shim/t1_count\necho "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — À refaire une fois
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : final
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** blocking
""",
    )
    d = sandbox / "work" / "feat" / ".approvals"
    d.mkdir(parents=True)
    (d / "CP-1.rejected").write_text("reason=la sortie ne convient pas\ntasks=T1\n")
    (d / "CP-1").write_text("approved_by=test\n")
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(sandbox) == {"T1": "done", "CP-1": "done"}
    assert (sandbox / ".shim" / "t1_count").read_text().count(
        "x"
    ) == 2  # 1er run + rework
    events = journal_events(sandbox)
    assert any(e["event"] == "checkpoint_rejected" for e in events)
    assert "REJETÉ" in (sandbox / "work" / "feat" / "tasks.md").read_text()


def test_eval_coverage_per_id(sandbox: Path) -> None:
    # EVAL-1 implémentée mais seule une eval_2 est collectée → couverture incomplète → failed
    collected = sandbox / "collected.txt"
    collected.write_text("tests/x.py::test_eval_2_autre\n")
    write_tasks(
        sandbox,
        """
### T1 — Prétend couvrir EVAL-1
- **depends_on :** —
- **implements :** [EVAL-1]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    env = {"LAB_EVALS_COLLECTED_FILE": str(collected)}
    r = run_orch(sandbox, env_extra=env)
    assert r.returncode == 1
    assert state(sandbox)["T1"] == "failed"

    # Même plan, l'eval attendue existe → done
    collected.write_text("tests/x.py::test_eval_1_nominal\n")
    (sandbox / "work" / "feat" / ".runs" / "state.json").unlink()
    r2 = run_orch(sandbox, env_extra=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert state(sandbox)["T1"] == "done"


def test_lint_warns_on_spec_version_drift(sandbox: Path) -> None:
    spec = sandbox / "work" / "feat" / "spec.md"
    spec.write_text(spec.read_text().replace("version: 1.0.0", "version: 2.0.0"))
    write_tasks(
        sandbox,
        """
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    tasks = sandbox / "work" / "feat" / "tasks.md"
    tasks.write_text(
        tasks.read_text().replace(
            "status: approved",
            "status: approved\nspec: ./spec.md          # version : 1.0.0",
        )
    )
    r = run_orch(sandbox, "--validate")
    assert r.returncode == 0  # warning, pas erreur
    assert "dérive documentaire" in r.stdout and "v1.0.0" in r.stdout


def test_anti_gate_vide(sandbox: Path) -> None:
    # T1 implémente un ID réel mais aucune eval n'existe (pas de pyproject) → failed
    write_tasks(
        sandbox,
        """
### T1 — Prétend implémenter INV-1 sans eval
- **depends_on :** —
- **implements :** [INV-1]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 1
    assert state(sandbox)["T1"] == "failed"
    assert "FAIL" in (sandbox / "work" / "feat" / "tasks.md").read_text()


# ----------------------------------------------------- durcissement (revue 2026-06-15)


def test_lint_rejects_unsafe_verify(sandbox: Path) -> None:
    # H1 — un verify avec exécutable hors liste blanche / opérateur shell = erreur de lint
    write_tasks(
        sandbox,
        """
### T1 — verify dangereux
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `rm -rf /tmp/x`
""",
    )
    r = run_orch(sandbox, "--validate")
    assert r.returncode == 1
    assert "verify" in r.stdout and "rejeté" in r.stdout


def test_status_last_match_wins(sandbox: Path) -> None:
    # M10 — deux lignes STATUS : c'est la DERNIÈRE qui tranche (comme le parseur VERDICT)
    (sandbox / ".shim" / "T1.sh").write_text(
        'printf "STATUS: blocked — faux positif recopié\\nSTATUS: done\\n"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — conclut done malgré une ligne blocked plus haut
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert state(sandbox)["T1"] == "done"


def test_scoped_commit_does_not_sweep_unrelated_tests(sandbox: Path) -> None:
    # H4/M12 — un fichier non lié sous tests/ ne doit JAMAIS être aspiré dans le commit
    # de la tâche (l'ancien code stageait l'arbre tests/ en entier).
    (sandbox / "tests").mkdir()
    (sandbox / "tests" / "unrelated.py").write_text("# pas cette tâche\n")
    (sandbox / ".shim" / "T1.sh").write_text(
        'echo data > t1.txt\necho "STATUS: done"\n'
    )
    write_tasks(
        sandbox,
        """
### T1 — n'écrit que t1.txt
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `test -f t1.txt`
""",
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    import subprocess

    def tracked(p: str) -> str:
        return subprocess.run(
            ["git", "ls-files", p], cwd=sandbox, capture_output=True, text=True
        ).stdout

    assert tracked("tests/unrelated.py").strip() == ""  # hors scope → non committé
    assert "t1.txt" in tracked("t1.txt")  # dans le scope → committé


def test_eval_coverage_scoped_to_task_paths(sandbox: Path) -> None:
    # M3/M4 — la couverture par ID est restreinte aux chemins de test de la tâche : une
    # eval_1 d'une AUTRE feature ne satisfait pas la couverture (collision de sous-chaîne).
    collected = sandbox / "collected.txt"
    collected.write_text("tests/autre_feature/test_eval_1_x.py::test_eval_1_x\n")
    write_tasks(
        sandbox,
        """
### T1 — couvre EVAL-1 dans son propre périmètre
- **depends_on :** —
- **implements :** [EVAL-1]
- **files_touched :** `tests/ma_feature/`
- **done_when :** ok
- **verify :** `true`
""",
    )
    env = {"LAB_EVALS_COLLECTED_FILE": str(collected)}
    r = run_orch(sandbox, env_extra=env)
    assert r.returncode == 1  # l'eval est hors périmètre → couverture vide → failed
    assert state(sandbox)["T1"] == "failed"

    collected.write_text("tests/ma_feature/test_eval_1_x.py::test_eval_1_x\n")
    (sandbox / "work" / "feat" / ".runs" / "state.json").unlink()
    r2 = run_orch(sandbox, env_extra=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert state(sandbox)["T1"] == "done"
