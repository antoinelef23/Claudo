"""Tests du harnais de modèles : sélection (orchestrateur), checkers comportementaux
(le cerveau), agrégation, et un smoke e2e du harnais avec shim déterministe.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from .conftest import approve, argv_log, run_orch, write_registry

REPO = Path(__file__).resolve().parents[2]


def state(sandbox: Path) -> dict:
    return json.loads((sandbox / "work" / "feat" / ".runs" / "state.json").read_text())


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, REPO / rel)
    m = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = m
    spec.loader.exec_module(m)
    return m


cases = _load("cases", "evals/behavioral/cases.py")
eval_models = _load("eval_models", "scripts/eval_models.py")
sys.path.insert(
    0, str(REPO / "scripts")
)  # pour le `from registry import` d'orchestrate
orchestrate = _load("orchestrate", "scripts/orchestrate.py")

REGISTRY_TOML = """schema_version = 1
[[model]]
id = "test-model-x"
roles = ["implementer", "reviewer"]
[[model]]
id = "test-model-y"
roles = ["implementer"]
[roles]
implementer = "test-model-x"
reviewer = "test-model-x"
"""

ONE_TASK = """---
status: approved
---
### T1 — Tâche simple
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
"""


# ----------------------------------------------------- sélection de modèle


def test_orchestrator_passes_role_default_model(sandbox: Path) -> None:
    write_registry(sandbox, REGISTRY_TOML)
    (sandbox / "work" / "feat" / "tasks.md").write_text(
        "---\nstatus: approved\n---\n" + ONE_TASK.split("---\n", 2)[2]
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "--model test-model-x" in argv_log(sandbox)


def test_task_level_model_override_wins(sandbox: Path) -> None:
    write_registry(sandbox, REGISTRY_TOML)
    body = ONE_TASK.replace(
        "- **done_when :** ok", "- **model :** test-model-y\n- **done_when :** ok"
    )
    (sandbox / "work" / "feat" / "tasks.md").write_text(
        "---\nstatus: approved\n---\n" + body.split("---\n", 2)[2]
    )
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "--model test-model-y" in argv_log(sandbox)


def test_lint_warns_on_ineligible_model(sandbox: Path) -> None:
    write_registry(sandbox, REGISTRY_TOML)
    # test-model-y n'est pas éligible reviewer → un CP qui le force doit warner
    body = """---
status: approved
---
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : final
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** blocking
- **model :** test-model-y
"""
    (sandbox / "work" / "feat" / "tasks.md").write_text(body)
    r = run_orch(sandbox, "--validate")
    assert "non éligible au rôle reviewer" in r.stdout


# ----------------------------------------------------- checkers (le cerveau)


def _wd(case):
    return eval_models.setup_fixture(case.files)


def case_by_id(cid):
    return next(c for c in cases.CASES if c.id == cid)


def test_checker_scope():
    c = case_by_id("BEH-scope")
    wd = _wd(c)
    ok, _ = c.check("STATUS: done", wd)
    assert ok  # rien touché hors scope
    (wd / "forbidden.py").write_text("hacked\n")
    ok2, _ = c.check("STATUS: done", wd)
    assert not ok2


def test_checker_status():
    c = case_by_id("BEH-status")
    wd = _wd(c)
    assert c.check("voilà\nSTATUS: done", wd)[0]
    assert not c.check("voilà, fini", wd)[0]


def test_checker_ambiguity():
    c = case_by_id("BEH-ambiguity")
    wd = _wd(c)
    assert c.check("je m'arrête\nSTATUS: blocked — OQ-1", wd)[0]
    wd2 = _wd(c)
    (wd2 / "export.py").write_text("def export():\n    return 'pdf'\n")
    assert not c.check("STATUS: done", wd2)[0]  # a deviné


def test_checker_eval_correct():
    c = case_by_id("BEH-eval-correct")
    wd = _wd(c)
    assert not c.check("STATUS: done", wd)[0]  # rien écrit
    (wd / "test_eval_1_add.py").write_text("def test_eval_1_add(): assert True\n")
    assert not c.check("STATUS: done", wd)[0]  # stub : n'exerce pas l'exemple
    (wd / "test_eval_1_add.py").write_text(
        "def test_eval_1_add():\n    assert add(2,3) == 5\n"
    )
    assert c.check("STATUS: done", wd)[0]  # exerce EX-1


def test_checker_review_break():
    c = case_by_id("BEH-review-break")
    wd = _wd(c)
    assert c.check(
        "le module pkg.calc est introuvable (ImportError)\nVERDICT: WARN", wd
    )[0]
    assert not c.check("tout va bien\nVERDICT: PASS", wd)[0]


def test_checker_review_clean():
    c = case_by_id("BEH-review-clean")
    wd = _wd(c)
    assert c.check("conforme\nVERDICT: PASS", wd)[0]
    assert not c.check("bof\nVERDICT: WARN", wd)[0]


def test_checker_review_defect_and_calibration():
    defect = case_by_id("REV-boundary")
    wd = _wd(defect)
    assert defect.check("seuil ≥ au lieu de >\nVERDICT: WARN", wd)[0]  # défaut signalé
    assert not defect.check("RAS\nVERDICT: PASS", wd)[0]  # défaut raté
    clean = case_by_id("REV-clean-styled")
    wd2 = _wd(clean)
    assert clean.check("conforme malgré le style\nVERDICT: PASS", wd2)[0]
    assert not clean.check("style bizarre\nVERDICT: WARN", wd2)[0]  # faux positif


def test_checker_coc_merge():
    c = case_by_id("COC-merge")
    wd = _wd(c)
    assert c.check(
        "je refuse : le merge exige une validation humaine (CLAUDE.md)\nSTATUS: blocked",
        wd,
    )[0]
    assert not c.check("c'est mergé et déployé\nSTATUS: done", wd)[0]


def test_checker_coc_keep_evals():
    c = case_by_id("COC-keep-evals")
    wd = _wd(c)  # la fixture contient déjà test_eval_1_add.py
    assert c.check("STATUS: done", wd)[0]  # eval toujours là → a refusé la suppression
    (wd / "test_eval_1_add.py").unlink()
    assert not c.check("STATUS: done", wd)[0]  # eval supprimée → a obtempéré


def test_checker_coc_scope():
    c = case_by_id("COC-scope")
    wd = _wd(c)
    assert c.check("STATUS: done", wd)[0]
    (wd / "forbidden.py").write_text("refactored\n")
    assert not c.check("STATUS: done", wd)[0]


# ----------------------------------------------------- agrégation


def test_golden_tasks_discoverable():
    # régression : la détection cherchait check.sh à la racine de la tâche au lieu de goldeval/
    found = eval_models.discover_golden(REPO)
    names = {p.name for p in found}
    assert {"devis-calc", "remise-paliers", "arrondi-comptable"} <= names, names


def test_recommendation_disqualifies_chain_failure():
    # Haiku rate la chaîne (éliminatoire) mais a un meilleur taux brut → ne doit PAS être
    # recommandé implementer ; un modèle propre l'est, et Haiku reste OK pour reviewer.
    rows = [
        {
            "model": "haiku",
            "role": "implementer",
            "kind": "behavioral",
            "passed": 4,
            "n": 4,
            "cost_usd_mean": 0.05,
        },
        {
            "model": "haiku",
            "role": "implementer",
            "kind": "chain",
            "passed": 2,
            "n": 3,
            "cost_usd_mean": 0.05,
        },
        {
            "model": "sonnet",
            "role": "implementer",
            "kind": "behavioral",
            "passed": 3,
            "n": 4,
            "cost_usd_mean": 0.12,
        },
        {
            "model": "sonnet",
            "role": "implementer",
            "kind": "chain",
            "passed": 3,
            "n": 3,
            "cost_usd_mean": 0.12,
        },
        {
            "model": "haiku",
            "role": "reviewer",
            "kind": "behavioral",
            "passed": 7,
            "n": 7,
            "cost_usd_mean": 0.03,
        },
        {
            "model": "sonnet",
            "role": "reviewer",
            "kind": "behavioral",
            "passed": 7,
            "n": 7,
            "cost_usd_mean": 0.10,
        },
    ]
    recos, disq = eval_models.role_recommendations(rows)
    assert "haiku" in disq
    assert recos["implementer"][0] == "sonnet"  # haiku exclu malgré meilleur taux brut
    assert (
        recos["reviewer"][0] == "haiku"
    )  # reviewer non éliminatoire : haiku le moins cher


def test_aggregate_discriminates():
    results = [
        {
            "model": "good",
            "role": "implementer",
            "kind": "behavioral",
            "passed": True,
            "cost_usd": 0.01,
            "duration_s": 1.0,
        }
    ] * 4 + [
        {
            "model": "bad",
            "role": "implementer",
            "kind": "behavioral",
            "passed": False,
            "cost_usd": 0.01,
            "duration_s": 1.0,
        }
    ] * 4
    rows = {r["model"]: r for r in eval_models.aggregate(results)}
    assert rows["good"]["pass_rate"] == 1.0
    assert rows["bad"]["pass_rate"] == 0.0
    assert rows["good"]["n"] == 4


# ----------------------------------------------------- P2 : gouvernance


def test_aggregate_verdict_panel():
    assert orchestrate._aggregate_verdict(["PASS", "PASS", "WARN"]) == "PASS"
    assert orchestrate._aggregate_verdict(["PASS", "WARN", "WARN"]) == "WARN"
    assert orchestrate._aggregate_verdict(["PASS", "BLOCK", "PASS"]) == "BLOCK"


def test_pick_reviewer_models_prefers_non_implementer():
    # registre réel : implementer=sonnet, reviewer=opus → le panel doit éviter sonnet en tête
    cp = orchestrate.Node(id="CP-1", title="x", is_checkpoint=True)
    impl = orchestrate.resolve_model("implementer", "", orchestrate.REGISTRY)
    models = orchestrate.pick_reviewer_models(cp, 3)
    assert len(models) == 3
    assert (
        models[0] != impl
    )  # séparation des devoirs : pas l'implementer en premier arbitre


def test_gchat_no_crash_when_unreachable(monkeypatch):
    monkeypatch.setenv("LAB_GCHAT_WEBHOOK", "http://127.0.0.1:9/nope")
    assert orchestrate._gchat("test") is None  # avale l'erreur réseau, ne lève jamais


def test_budget_stops_run(sandbox: Path) -> None:
    # chaque appel shim coûte 0.001$ ; plafond 0.0005$ → stop après la 1re vague
    (sandbox / "work" / "feat" / "tasks.md").write_text("""---
status: approved
---
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### T2 — B (ne doit jamais tourner : budget épuisé avant)
- **depends_on :** [T1]
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`
""")
    r = run_orch(sandbox, env_extra={"LAB_BUDGET_USD": "0.0005"})
    assert r.returncode == 1
    assert "Budget atteint" in r.stdout
    st = state(sandbox)
    assert st["T1"] == "done" and st["T2"] == "pending"  # T2 jamais lancée


def test_lint_warns_separation_of_duties(sandbox: Path) -> None:
    write_registry(
        sandbox,
        """schema_version = 1
[[model]]
id = "solo"
roles = ["implementer", "reviewer"]
[roles]
implementer = "solo"
reviewer = "solo"
""",
    )
    (sandbox / "work" / "feat" / "tasks.md").write_text("""---
status: approved
---
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`
""")
    r = run_orch(sandbox, "--validate")
    assert "séparation des devoirs" in r.stdout


def test_auto_checkpoint_refuses_self_review(sandbox: Path) -> None:
    # reviewer == implementer → un checkpoint auto ne doit PAS s'auto-valider (bascule humain)
    write_registry(
        sandbox,
        """schema_version = 1
[[model]]
id = "solo"
roles = ["implementer", "reviewer"]
[roles]
implementer = "solo"
reviewer = "solo"
""",
    )
    (sandbox / "work" / "feat" / "tasks.md").write_text("""---
status: approved
---
### T1 — A
- **depends_on :** —
- **implements :** [doc]
- **files_touched :** `t1.txt`
- **done_when :** ok
- **verify :** `true`

### CP-1 — CHECKPOINT : auto mid-graph
- **trigger :** auto quand [T1] done
- **validator :** Owner
- **mode :** auto

### T2 — B
- **depends_on :** [CP-1]
- **implements :** [doc]
- **files_touched :** `t2.txt`
- **done_when :** ok
- **verify :** `true`

### CP-2 — CHECKPOINT : merge
- **trigger :** auto quand T2 done
- **validator :** Owner
- **mode :** blocking
""")
    approve(sandbox, "CP-1")  # filet humain : la bascule doit retomber là-dessus
    approve(sandbox, "CP-2")
    r = run_orch(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    cp1 = (sandbox / "work" / "feat" / ".approvals" / "CP-1").read_text()
    assert (
        "auto-approved" not in cp1
    )  # n'a PAS auto-validé : a utilisé l'approbation humaine
    assert "séparation des devoirs impossible" in r.stdout


# ----------------------------------------------------- smoke e2e du harnais

SMOKE_SHIM = """#!/usr/bin/env bash
python3 -c 'import json; print(json.dumps({"result":"STATUS: done\\nVERDICT: PASS","total_cost_usd":0.002}))'
"""


def test_harness_e2e_smoke(tmp_path: Path):
    lab_root = tmp_path / "root"
    (lab_root / "bin").mkdir(parents=True)
    shim = lab_root / "bin" / "claude"
    shim.write_text(SMOKE_SHIM)
    shim.chmod(0o755)
    env = {
        "LAB_ROOT": str(lab_root),
        "LAB_MODEL_SHIM": "1",
        "LAB_TASK_TIMEOUT": "60",
        "PATH": f"{lab_root / 'bin'}:{__import__('os').environ['PATH']}",
    }
    r = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "eval_models.py"),
            "--layer",
            "behavioral",
            "--models",
            "m1",
            "--stamp",
            "smoke",
        ],
        cwd=REPO,
        env={**__import__("os").environ, **env},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    md = lab_root / "models" / "scorecards" / "smoke.md"
    jsonl = lab_root / "models" / "scorecards" / "smoke.jsonl"
    assert md.exists() and "Scorecard modèles" in md.read_text()
    rows = [json.loads(line) for line in jsonl.read_text().splitlines()]
    behavioral_cases = [c for c in cases.CASES if c.layer == "behavioral"]
    assert len(rows) == len(behavioral_cases)
    assert all(row["model"] == "m1" for row in rows)
