---
name: commit
description: Writes a structured git commit whose body records WHY the change exists (the workshop decision, the resolved OQ, the trade-off), not just what changed. Use when committing artifact or code changes in the AI-Native Lab so the reasoning lands in git history where agents can mine it. Honors the content_guard fusible (substance change ⇒ version bump). Same format as the orchestrator's auto-commits.
---

# /commit — put the "why" in git

You produce a commit in the lab's canonical format (see `docs/commit-format.md`). The
repo is the memory: the diff already says *what* changed — your job is to capture *why*,
so a future reader or agent recovers the reasoning with `git log` instead of re-litigating
the choice.

## Step 1 — Inspect what is staged

```bash
git status --short
git diff --cached --stat
git diff --cached
```

If nothing is staged, look at the working tree and **stage only the intended scope**
(never `git add -A`; in this repo the untracked `deploy/.last-url`, `sbom.json`,
`work/repartition/`, `work/webhook-*/` must never be committed). Confirm scope with the
user if ambiguous.

## Step 2 — Derive the facts

- **feature** — the `work/<feature>/` the change belongs to (or the repo area for infra).
- **node** — the task/checkpoint id (`T3`, `CP-1`) if this maps to one; else omit.
- **Spec-IDs** — every `INV/BHV/EX/EVAL/NG/OQ/ADR` the diff implements or touches. Grep
  the diff and the artifact for them; don't invent IDs that aren't in `spec.md`.
- **Version bump?** — did a *substance* line (an ID assertion, glossary name, KPI) of
  `spec.md`/`design.md` change? If yes, the artifact's `version:` MUST be bumped in this
  same commit. Verify mechanically: `just check-content` (or
  `python3 scripts/content_guard.py --git work/<feature>/spec.md`) must pass. If it fails,
  the substance changed without a bump — fix that before committing. Record the bump in
  the `Version-Bump:` trailer.

## Step 3 — Write the WHY (the actual point)

One to three sentences of reasoning. Sources, in order of value:
1. The workshop / session context you're in right now (what the Owner just decided and why).
2. The OQ being resolved, the ADR being applied, the trade-off being made.
3. For a hand-written (non-generated) line: the justification that makes it a *deliberate*
   exception ("every hand-written line is a justified exception, recorded in the commit").

Write *why it changed*, not *what changed*. Bad: "update calc.py". Good: "BHV-2a was
ambiguous on the exact-threshold case; the workshop ruled strictly-greater (a €X order is
below the tier), so the discount predicate uses `>` not `>=`."

## Step 4 — Compose and commit

Build the message exactly per `docs/commit-format.md`: subject `type(feature): node title
[IDs]`, blank line, `Why: …`, blank line, then the trailers (`Spec-IDs`, `Artifacts`,
`Version-Bump` if any, `Checkpoint` if any, `Run: owner`). Show it to the user, then:

```bash
git commit -m "$(cat <<'EOF'
<the full composed message>
EOF
)"
```

Do **not** add a Claude/AI co-author trailer unless the user's global convention requires
it. Do not push unless asked.

## Guardrails

- Never weaken the fusible: a substance change without a `version:` bump is a defect, not a
  thing to commit around.
- Keep the subject's `[IDs]`/`[auto]` tag — the reviewer agent greps it for traceability.
- One coherent change per commit; if the staged diff spans unrelated reasons, split it.
