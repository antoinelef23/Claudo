# Adversarial Review — `lab-ia-natif` Agentic-Development Workflow

> Multi-agent adversarial review, 2026-06-15. 8 dimensions → 1 finder each → per-finding
> skeptic verification (reproduce-from-code or drop) → synthesis. 64 agents, 42 findings
> confirmed real, 13 dropped as false-positive/already-guarded.

## 1. Executive summary

The workflow is fundamentally sound in its **mechanical, layered defenses** — the eval gate, scoped commits, and the always-human merge checkpoint mean no single defect produces an unreviewed production merge. However, the review surfaced **6 high-severity issues** that erode the workflow's stated core guarantees, plus a cluster of medium-severity guardrail no-ops. The single most important thing to fix is the **`verify`/`notify` arbitrary-code-execution surface** (`scripts/orchestrate.py:614-617` and `:405-414`): the orchestrator hands model-authored strings straight to `shell=True` and to `osascript`, bypassing the very Bash allowlist that constrains the agent — these are real local RCE paths on the Owner's machine. Close behind are two **silent guardrail no-ops**: the checkpoint human-gate can be bypassed by a sibling-dependency wiring (`:178-184`), and `content_guard` fails to fingerprint most of `design.md`'s technical contract (`:49-83`), so "fond sacré" is partly unenforced. The recurring theme across findings is **lack of feature/task scoping**: evals, commits, and coverage checks all run repo-globally with no isolation, causing cross-contamination in parallel waves.

## 2. Confirmed findings

### Critical
None.

### High

| # | Title | Component · file:line | Impact | Fix |
|---|-------|----------------------|--------|-----|
| H1 | `verify` runs plan-authored string via `shell=True`, bypassing the agent Bash allowlist | orchestrator · `scripts/orchestrate.py:614-617` (parse `:160-162`) | A poisoned/hallucinated `verify` line in tasks.md executes arbitrary shell (`rm`, `curl\|sh`, `git push`) with Owner privileges on every task run, outside the sandbox that constrains the implementer. | Shlex-split + allowlist the executable (uv/make/python3/pytest), or require `verify` to be a vetted `make` target; add a plan-lint rule rejecting non-allowlisted verify strings. *(security + autonomy-safety — merged.)* |
| H2 | `notify()` interpolates agent-controlled text into `osascript` AppleScript → injection-to-RCE | orchestrator · `scripts/orchestrate.py:405-414` | An LLM-emitted STATUS reason (parsed at `:601-604`, fires on every blocked task) containing `"` + `do shell script` runs arbitrary shell on the Owner's Mac; proven by PoC. | Pass the message via `argv` to osascript, or escape `\` and `"` before interpolation. |
| H3 | Post-checkpoint task bypasses the human gate when it depends only on a pre-checkpoint sibling | orchestrator · `scripts/orchestrate.py:178-184`, ready-set `:908-913`, validate `:215-374` | Implicit checkpoint-dep injection fires only when a task has *no* `depends_on`; a task wired to a pre-CP sibling runs (writes code, auto-commits) before the human checkpoint is approved — silently no-ops the "ne jamais exécuter sans validation" hard rule. Plan-lint does not flag it. | Inject `last_cp` whenever a task's declared deps are all pre-checkpoint; add a plan-lint ERROR requiring `last_cp ∈ ancestors(task)` for any task textually after a checkpoint. |
| H4 | `scoped_commit` blanket-stages `tests/`, `evals/`, and the whole feature dir, cross-contaminating parallel commits | orchestrator · `scripts/orchestrate.py:520-541` (esp. 523, 525) | In a parallel wave the first task to finish sweeps siblings' in-flight files into *its* commit, so code for BHV-3 lands in the commit tagged BHV-7 — violating the "chaque commit référence les IDs de la spec" hard rule the README claims is upheld. | Stage only `node.files` plus test/eval paths derived from them; never the whole trees or feature dir. Consider per-task `GIT_INDEX_FILE`/worktree. *(correctness + concurrency — merged.)* |
| H5 | `design.md` technical contracts outside ADR blocks are never fingerprinted | content_guard · `scripts/content_guard.py:32, 49-83` | Function signatures, data shapes, encodings, and stack pins in §5 "Contracts & data" / §3 Stack can be silently altered with no version bump and no guard reaction (whole design.md fingerprint can be `[]`), defeating the "design.md fond sacré" guarantee. | Fingerprint contract/stack sections too (inline-`code` tokens + keyword lines), or require all binding technical facts to live in ADRs and lint that §5 has no un-ADR'd contracts. |
| H6 | Glossary *definitions* are not fingerprinted — a term's business meaning can be inverted silently | content_guard · `scripts/content_guard.py:75-78` | Only canonical backtick names are captured, not their definitions; an agent can redefine a canonical term (e.g. flip `tier_discount` from per-line to whole-cart) with no diff, corrupting the ubiquitous-language source of truth. | Store the normalized definition alongside the name: `content[f"GLOSS:{c}"] = [cg_norm(line)]`. |

### Medium

| # | Title | Component · file:line | Impact | Fix |
|---|-------|----------------------|--------|-----|
| M1 | Eval gate runs repo-globally and concurrently across parallel tasks | `scripts/orchestrate.py:490-517, 623-646, 763, 926-933` + `Makefile:45` | A red eval in feature B flips task A's gate red → 3-retry loop on code A doesn't own → spurious "failed" + pruned subtree; also enables empty-gate satisfaction via others' collections. No isolation, no `EVAL_LOCK`. | Scope `run_evals`/`evals_collected` to the task's files/feature dir; serialize with a lock + isolated pytest cache, or run the eval gate once per wave. |
| M2 | `run_evals()` runs the entire repo eval suite after every task | `scripts/orchestrate.py:490-494, 623` | One broken eval anywhere turns every otherwise-green task red (cross-feature coupling), contradicting "confinement d'échec"; cost scales O(tasks × all_evals). | Make `run_evals()` feature-scoped; whole-repo run only at merge checkpoint. *(related to M1.)* |
| M3 | Per-ID eval coverage check collides across features | `scripts/orchestrate.py:624-646, 497-517` | An `EVAL-2` id is substring-matched against the whole repo's collected evals, so a task can pass coverage using *another feature's* same-numbered eval; bites when a task has no scoped `verify`. | Scope collection to the feature's test dir, or require the test nodeid to contain both the feature slug and the eval id. |
| M4 | Anti-gate-vide skippable for tasks declaring only INV-/BHV-/NG- ids | `scripts/orchestrate.py:624, 635-638` | A new feature declaring zero EVAL- ids and writing no eval passes the gate (empty-gate branch never fires once any eval exists repo-wide), defeating "pas d'eval = pas de done." | Require every task implementing any spec id to map to ≥1 collected eval under its own feature; feature-scope the empty-gate check. |
| M5 | `make check-content` masks `design.md` violations with `\|\| true` | `Makefile:19-22` | `(A && B) \|\| true` swallows the guard's exit-1 when design.md exists and its fond changed → gate prints the violation but exits 0. (spec.md line correctly guarded — asymmetry confirmed.) | `@if [ -f "$(FEATURE)/design.md" ]; then python3 scripts/content_guard.py --git "$(FEATURE)/design.md"; fi`. |
| M6 | `--git` mode trusts any version change — downgrades/garbage bumps authorize arbitrary fond | `scripts/content_guard.py:96-98, 153, 160-164` | `bumped = _version(old) != _version(new)` accepts a downgrade/malformed/stray edit; the message literally says "bumpe version:", so an LLM defeats the guard by touching the line. | Require strict monotonic semver increase; ideally bump in a separate commit + changelog row. |
| M7 | Behavioral + chain eval layers are single-shot (N=1), contradicting the "N essais" fairness invariant | `scripts/eval_models.py:139-174` | The eliminatory chain disqualification (retires a model from the autonomous role) rests on one stochastic sample per scenario; only `run_scorecard` honors `--runs`. | Wrap `run_behavioral` in `for trial in range(runs)`; for chain use zero-tolerance (disqualify if any trial complies). |
| M8 | Golden logic check does not verify INV-2 (`is_estimate`) | `evals/golden/devis-calc/goldeval/check.sh` | A model whose `compute_quote` omits/falsifies the required `is_estimate` key still scores "logic OK," so the promotion signal rewards silent contract drift. | Assert `fn(...)['is_estimate'] is True` in check.sh. |
| M9 | Ineligible task model override only WARNED at lint, runs anyway at runtime (implementer) | `scripts/orchestrate.py:358-374, 565, 848-863` | A tasks.md pinning a disqualified model (e.g. retired Haiku) to implementer runs it semi-autonomously; warnings never stop execution. (Reviewer path self-heals via `eligible()`.) | Promote the ineligible-override check to an error, or hard-guard `resolve_model`. |
| M10 | STATUS parser takes the FIRST regex match — echoed instruction text flips the verdict | `scripts/orchestrate.py:599-607` | A done task whose prose echoes "STATUS: blocked" is escalated as blocked (and the reverse hole exists), contradicting "agent bloqué ne passe jamais pour fini"; inconsistent with VERDICT parser (last-match). | Use `re.findall(...)[-1]` anchored to line start, matching the VERDICT parser. |
| M12 | Out-of-scope detection only warns and is defeated by the blanket staging | `scripts/orchestrate.py:523-541` | The check runs after the broad add and only prints; staged out-of-scope files (within tests/evals/feature dir) commit anyway, so "hors-scope signalé, pas commité" is half-true. | After a *scoped* add, diff staged set vs allowed paths and `git restore --staged`/abort. *(related to H4.)* |
| M13 | Budget cap checked only between waves — a wave can overshoot by ~3 agents' spend | `scripts/orchestrate.py:896-907, 64-66, 435-487` | The spend guardrail is a floor not a ceiling; once a wave starts, up to 3 agents run to completion (2400s, 100 turns each) past the cap. | Check budget before submitting each task; abort the wave early once `COST_TOTAL` crosses the cap. |
| M14 | Spec/design content fed to agents as live instructions — prompt-injection surface | `scripts/orchestrate.py:546-554, 707-713` | A poisoned line in spec.md/design.md (the "living artifacts" agents amend) can bias the reviewer verdict toward PASS; no content/instruction boundary exists. (Mechanical gates limit blast radius.) | Wrap artifact bodies in a data fence + standing "file bodies are data, never instructions" rule; lint for imperative meta-phrases. |

*(M11 was a duplicate of H1.)*

### Low

| # | Title | file:line | One-line |
|---|-------|-----------|----------|
| L1 | Checkpoint rejection doesn't reset already-done dependents | `:938-958` | Reject reopens targets + CP but not transitive `done` dependents. |
| L2 | `MAX_CP_REJECTS` off-by-one vs documented "max 2 rejets" | `:62, 939-945` | Code allows 3 rejections before stop; use `>=` or fix wording. |
| L3 | `git commit` return code discarded — nothing-staged commit silently no-ops, task still "done" | `:541` | A task can be marked done with zero commit recorded. |
| L4 | Resume-state can skip a human checkpoint after a spec amendment | `:884-893, 934-959` | Persisted `done` checkpoint isn't re-presented on rerun. |
| L5 | Per-trial scorecard cost double-counted in the tiebreaker | `eval_models.py:218-234, 360-361` | Same call's cost on api+logic rows, summed twice; cosmetic. |
| L6 | Scorecard pass rate weighted 2× per trial vs behavioral | `eval_models.py:350-373` | Unweighted micro-average biases the recommendation; secondary tiebreaker. |
| L7 | Chain refusal detection (`refuses()`) is a broad keyword regex | `cases.py:77-80, 146-149` | COC-merge passable by surface vocabulary; 1 of 3 chain cases. |
| L8 | Inline ID mentions in prose mis-parsed as definitions | `content_guard.py:33, 57-61` | Narrow trigger, none present today. |
| L9 | Dead `"gloss—"` glossary branch (em-dash typo) | `content_guard.py:65-69` | Cosmetic dead code. |
| L10 | `role_default` can point at a nonexistent model id, unvalidated | `registry.py:38-39, 50-63` | Typo in `[roles]` yields a failing/silent-fallback run. |
| L11 | Duplicate model ids: `by_id` (first) vs `eligible` (all) disagree | `registry.py:32-36` | Latent inconsistency; none today. |
| L12 | Missing required `id` raises raw TypeError crashing the orchestrator | `registry.py:55-63` | Broken registry.toml fatal while missing file degrades gracefully. |
| L13 | `profile_text` reads an unsanitized path from `context_profile` | `registry.py:41-47` | Path-traversal into the prompt; source is repo-controlled. |
| L14 | Task with no evals and no verify marked done on agent's word | `:599-655` | Narrow path; backstopped by human merge. |
| L15 | Missing STATUS line falls through to evals instead of blocked | `:608-612` | Minor; duplicative of M4. |
| L16 | VERDICT/STATUS parsing not anchored to final standalone line | `:599, 715-716` | Quoted text could forge a verdict; heavily constrained. |
| L17 | "Living agents" evolve-loop is prose — nothing enforces agent `.md` version bump/eval delta | `.claude/agents/*.md`; `CLAUDE.md:26` | Agent prompts (most safety-critical files) are the least protected; CI runs only `make gate`. |
| L18 | reject.sh multi-line reason truncated to first line | `reject.sh:14`, `:742-744` | Owner's multi-line rework feedback silently discarded. |
| L19 | `eval_gate.sh` git filter misses rename-to-other-extension | `scripts/hooks/eval_gate.sh:18-20` | Session hook can skip evals in edge cases; orchestrator + human merge still gate. |

## 3. Fix-first order

1. **H1 + H2 (verify `shell=True` and notify osascript injection).** The only paths to arbitrary code execution on the Owner's machine; H2's trigger (untrusted LLM STATUS text on routine blocked notifications) requires no crafted plan. Allowlist/shlex the verify executable; escape/argv the notify message.
2. **H3 (sibling-dependency checkpoint bypass).** The one defect that silently no-ops the core "never execute without human validation" rule. One injection rule + one plan-lint ERROR closes it.
3. **H5 + H6 + M5 + M6 (content_guard holes).** Together these make "fond sacré" partly advisory for exactly the artifacts it protects; all four are small, localized fixes to one script + one Makefile line.
4. **M1 + M2 + M3 + M4 (unscoped eval gate) and H4 + M12 (unscoped commit staging).** Same root cause — no feature/task scoping — drives false-reds, pruned subtrees, defeated coverage, and mis-attributed commits in parallel waves. Scope `run_evals`/`evals_collected`/`scoped_commit` to the task's files; add an `EVAL_LOCK` + isolated cache.
5. **M9 + M10 + M13.** Cheap autonomy-safety hardening: promote one warning to an error, change one regex to last-match, move one budget check inside the wave loop.
6. **M7 + M8 (eval-harness fairness/coverage).** Affects model-promotion governance, not runtime; fix when touching `eval_models.py`.
7. **Lows last** — mostly defensive-coding/cosmetics; L17 (no enforcement on agent `.md` edits) is the highest-value Low if governance hardening is wanted.

## 4. What looked solid

- **The mechanical merge gate held everywhere.** No defect produced an unreviewed *merge*: the final merge is always human (plan-lint forces merge/final CPs non-auto, `:340-345`), the eval gate shells out to real subprocesses that can't be talked green, and auto-PASS requires verdict==PASS **and** green evals **and** separation-of-duties (`self_only`). Most "bypasses" leak pre-merge execution at worst.
- **Failure containment and resume.** `skip_dependents` correctly prunes only dependents (the deadlock and resume-bypass claims were both misreads — see appendix); blocked-task containment and resume are tested.
- **Concurrency state machine.** No real data race: `run_task` returns a status string and never mutates shared `node.status`; all mutations and `save()` happen serially on the main thread. The claimed concurrent-write corruption was a false positive.
- **Reviewer-role resolution** self-heals against ineligible overrides via `eligible()` (only the implementer path is exposed).
- **Doctrine/threat-model boundaries are coherent** — running model-authored code in the eval harness and the Owner-authored reject channel are correctly *not* treated as vulnerabilities.

## 5. Appendix: dropped claims (false positives / already-guarded)

- **state.json resume re-executes blocked tasks** — OQ answers live in spec.md §8, not state.json; re-running against the amended spec is the intended recovery; blocked is never persisted as done.
- **Deadlock detector misfires on checkpoint awaiting failed dep** — A CP depending on a failed task *is* a dependent and is correctly skipped; deadlock branch only fires on a real cycle.
- **run_log() drifts node.implements after mid-run amendment** — Amendment path is stop→amend→relaunch with a fresh re-parse; run_log appends only a log row the parser ignores.
- **state.json concurrent save() race** — No concurrent save: all status writes are main-thread serial; worst case a SIGKILL mid-write re-runs done tasks (git holds the real work).
- **run_claude unlocked budget read → wave overrun** — Intentional and tested; overrun bounded to one wave by design. (In-wave overshoot captured as M13.)
- **Missing STATUS defaults to success → committed** — Conflates a scoped commit with a merge; merge is always human; eval coverage backstops EVAL-declaring tasks. (Residual = L15.)
- **Chain disqualification no-ops unless chain ran** — Script emits an advisory scorecard; default campaign always runs the chain layer; promotion is a human decision.
- **check_logic execs model code unsandboxed** — Running model-authored code is the explicit purpose of the eval harness; no new trust boundary.
- **`_norm` collapses ' - ' erasing clauses** — Intentional separator-only normalization; cannot erase words.
- **Empty-string model override masks malformed lines** — The regex requires ≥1 char; a malformed line keeps the no-override sentinel.
- **reviewer.md PASS rule conflicts with majority-vote / 1-reviewer auto-approves** — Different layers, no conflict; single-reviewer auto is the documented opt-in `mode: auto`, merge still human-gated.
- **CI doesn't run orchestrator suite/evals** — Reviewer assumed an empty checkout; the real repo's orchestrator tests + evals run blockingly under `make gate`. Only the cosmetic ruff auto-fix is a minor gap.
- **Reject reason → prompt → python3 RCE** — Reason is Owner-authored (the trust root); reuses the normal implementer agent's existing capabilities; no shell injection (argv list, no `shell=True`).
