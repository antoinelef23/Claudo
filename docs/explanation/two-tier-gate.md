# The two-tier gate: offline evals vs live verification

The lab's headline property is that a feature can be built and merged **code-first,
offline, cheaply** — a run costs a few dollars and needs no live credentials. That is not
an accident; it is the direct consequence of one choice: **the gate runs against fakes.**
This page explains why that choice is right, what it deliberately does *not* prove, and
the second tier that closes the gap without giving up the fast inner loop.

## Why the offline gate is fake-backed (and must stay that way)

The [architecture](architecture.md) is ports-and-adapters with injectable transports:
every external dependency (a DB, a model, an auth server, an object store) sits behind a
port, and the eval gate wires a **fake** adapter. That is what lets `just evals` run in
milliseconds, in CI, on any laptop, with no secrets — and it is why the orchestrator's
inner loop (implement → gate → commit, per task, in parallel) is cheap enough to run
dozens of times a feature.

Making that inner loop hit real systems would destroy the property that makes the lab
usable: it would need credentials, cost money and wall-clock, be non-deterministic, and
couple every task to infrastructure. So the offline, fake-backed gate is **Tier 1**, and
it stays exactly as it is.

## What Tier 1 cannot prove

Fakes verify the **contract**, not the **integration**. A green Tier-1 suite says "given
the port's contract, the code is correct." It says nothing about whether the *real*
adapter behind that port actually works: whether the SQL migration applies, whether the
auth token actually validates, whether the model returns the shape you assumed, whether
per-user OAuth scopes are right.

This is the honest limit surfaced by the first long external run: every feature deferred
its real adapter "to deploy", so the harder, riskier half — the live integrations — sat
**entirely outside** the eval-gated loop. "Validated by the lab" quietly meant "the
contract holds with fakes", which is not the same as "the live path works". Left
implicit, that reads as more assurance than it is.

## Tier 2: live / integration checks, run separately

The fix is not to make Tier 1 live — it is to make the live half a **first-class, named
tier that runs on its own schedule**, so the gap is closed *and* visible, without slowing
the inner loop. Tier 2 splits by what a check needs:

| | Marker | Runner | Backing | When |
|---|---|---|---|---|
| **Integration** | `@pytest.mark.integration` | `just integration` | containers / emulators (Postgres, Keycloak, …) — deterministic, no secrets | CI job, separate from the merge gate |
| **Live** | `@pytest.mark.live` | `LIVE=1 just live` | real services (Vertex, per-user OAuth, staging) — creds, cost | manual / pre-deploy; refuses without `LIVE=1` |

Two deliberate boundaries:

- **Tier 2 is never the merge gate.** `just test` and the orchestrator's gate exclude
  `integration` and `live`, so the inner loop stays fast and offline. Tier 2 is a
  *pre-deploy* stage.
- **`live` fails closed on cost.** Like `just eval-models` without `--live`, `just live`
  refuses unless `LIVE=1` is set — you never bill a real service or leak a run into CI by
  accident. `integration` needs no secrets (containers), so it *is* CI-able.

Where possible, prefer **integration over live**: Postgres and Keycloak both have
containers, so a Cloud SQL or auth adapter can be exercised for real, deterministically,
with no cloud account. Reserve `live` for what genuinely has no offline stand-in
(a hosted model, a real OAuth consent screen).

## How a feature declares its Tier 2

The spec's [§7 gate section](../../lab/templates/spec.md) carries both tiers. §7.1 is the
familiar eval table (Tier 1). §7.2 lists the live/integration checks, with one standing
rule: **if a non-goal in §6 defers an integration "to deploy", it must have a Tier-2
check in §7.2.** That rule is the whole point — it converts an invisible deferral ("the
real adapter is wired later, trust us") into a named, runnable obligation.

The checks themselves live in the **project**, not the lab: the lab has no live adapters
of its own, so `just integration` / `just live` no-op cleanly in the lab repo and become
real only where a project (with real adapters) wires them. The lab's contribution is the
*convention* — the markers, the recipe seams, the spec section — not the tests.

## The trade-off, stated plainly

Tier 1 buys speed and cost by proving contracts, not systems. Tier 2 buys live assurance
at the price of infrastructure and a separate run. Keeping them **separate** is what lets
you have both: a cheap loop you run constantly, and a live tier you run before you ship —
with the spec making sure the second one is never silently skipped. Related: the same
instinct that keeps mechanical obligations in the gate rather than in an agent's prompt
(see [why the lab does not let an agent edit its own agent](agent-self-evolution.md)).
