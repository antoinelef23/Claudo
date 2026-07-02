# Why the lab does not let an agent edit its own agent

A recurring surprise when driving the lab: the orchestrated implementer never
"self-lints", and the obvious fix — teaching it to, by editing
`.claude/agents/implementer.md` from inside a run — is **refused**. This page
explains why that refusal is correct, why it is *not* a hole in the "living
agents" design goal, and where the lever actually is.

## The observation

An agent runs under `claude -p` with edit permissions on the project. Ask it, mid-run,
to improve its own role definition (`.claude/agents/*.md`) and Claude Code's built-in
safety layer refuses it as self-modification. So the lab **cannot autonomously rewrite
its own scaffolding** during a run — even when the change looks benign ("also run the
linter before declaring done").

It is tempting to read this as a missing capability, given the lab's stated goal that
[agents evolve at the speed of the models](../../lab/models/EVOLUTION.md). It is the
opposite: it is the design working.

## Why the refusal is correct

The lab's governance is an **authority hierarchy** (see
[architecture](architecture.md) and `CLAUDE.md`'s chain of command):

> `CLAUDE.md` (hard rules) > role `.md` (behavior contract) > task prompt

The whole point of the chain-of-command eval layer (`evals/behavioral/`,
`lab/engine/eval_models.py`) is that **a task instruction must never make an agent
violate a higher rule** — merge without a human, skip the evals, go out of scope. A
model that obeys "merge without a human" is dropped from the role, whatever its raw
score.

An agent editing its own `.md` is exactly that violation, one level up: the thing being
*governed* rewriting its own *governance*, mid-run, on the strength of a task prompt. If
that were allowed, the authority hierarchy would be editable from its lowest tier — a
prompt could talk an agent into loosening its own contract, and every downstream eval
would then be measuring an agent that no longer matches its committed definition. The
refusal keeps the contract **stable within a run** and changeable only from **outside**
it. This is the same instinct as [git-as-memory](git-as-memory.md): a change to a
contract is a deliberate, recorded, human act — never an in-passing side effect.

## Where the lever actually is

The scaffolding is **living**, but it is evolved by the **Owner**, out of band, through
the measured loop — not by an agent editing itself in place. The order of intervention
is already doctrine (`EVOLUTION.md`, "help a model that understands poorly"):

1. adjust the model's **context profile** (`lab/models/profiles/`);
2. reinforce the role's **agent `.md`** — the behavior contract;
3. as a last resort, reformat spec/design under `content_guard`.

Each of these is an Owner action: a minimal patch, re-run the affected evals, keep it
only if it **raises the targeted score without regressing another**, then a governed
commit that bumps the agent's `version:`. That is what "living agents" means — continuous
but *measured, versioned, reversible* evolution — not silent self-mutation.

## The corollary: put mechanical requirements in the gate, not the prompt

The concrete symptom — "the implementer should lint before it says done" — has a cleaner
home than the agent's self-instruction anyway: the **gate**.

A requirement encoded in an agent's prompt is a request the model may or may not honor,
and (as above) the agent can't safely add it to itself. A requirement encoded in the
**gate** is mechanical: it holds for every model, needs no self-modification, and fails
closed. So the lab's answer to "make the implementer lint" is not "edit the implementer"
— it is "make lint part of what a checkpoint enforces":

- checkpoints run the **full gate** (`just gate-ci` — lint, tests, evals, brand), not
  evals alone, so lint/config drift **blocks** rather than accumulating unnoticed;
- the merge checkpoint additionally gates a **clean checkout of HEAD**, so what was
  committed — not just the working tree — must pass;
- scoped commits **fail closed** on out-of-scope edits, so nothing green-looking hides a
  dropped change.

(These are the gate-integrity guarantees added after the first long external run; see
[architecture](architecture.md) and the `tests/orchestrator/test_gate_integrity.py`
suite.) The principle generalizes: **if you find yourself wanting to teach an agent a new
mechanical obligation, add it to the gate, not to the agent's prompt.** The prompt is for
judgment; the gate is for rules.

## The trade-off, stated plainly

The lab is *not* a system that improves its own agents autonomously, and by construction
it will not become one from inside a run. Agent evolution stays a human-in-the-loop,
eval-gated, version-bumped act. That is a deliberate boundary, not a backlog item: the
last mile of governance is exactly where you want a human, and the chain-of-command layer
exists to keep it that way.
