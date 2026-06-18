# AI-Native Lab — standard targets. All hooks and the orchestrator go through here.
# The targets are tolerant: as long as the Python project does not exist (no pyproject.toml),
# they no-op cleanly so the hooks don't break on the empty skeleton.

.PHONY: install lint lint-check test evals gate gate-ci validate run check-content check-content-ci eval-models

# Plan-lint of a feature: make validate FEATURE=work/ma-feature
validate:
	@test -n "$(FEATURE)" || { echo "usage: make validate FEATURE=work/ma-feature"; exit 1; }
	@python3 scripts/orchestrate.py "$(FEATURE)" --validate

# Orchestrated run in foreground: make run FEATURE=work/ma-feature [SUPERVISED=1]
run:
	@test -n "$(FEATURE)" || { echo "usage: make run FEATURE=work/ma-feature"; exit 1; }
	@caffeinate -i python3 scripts/orchestrate.py "$(FEATURE)" $(if $(SUPERVISED),--supervised,)

# Substance/form guardrail: make check-content FEATURE=work/ma-feature
# Fails if the SUBSTANCE of spec/design changed without a version bump (reformat ≠ amendment).
check-content:
	@test -n "$(FEATURE)" || { echo "usage: make check-content FEATURE=work/ma-feature"; exit 1; }
	@python3 scripts/content_guard.py --git "$(FEATURE)/spec.md"
	@if [ -f "$(FEATURE)/design.md" ]; then python3 scripts/content_guard.py --git "$(FEATURE)/design.md"; fi

# Substance/form guardrail in CI: compares spec/design of changed features to a base
# (finding M10/M11). All logic is in the script (testable outside Actions).
check-content-ci:
	@BASE="$(or $(BASE),origin/main)" bash scripts/ci_checks.sh

# Model eval: make eval-models [LIVE=1] [LAYER=behavioral|chain|scorecard|all] [MODELS=a,b]
# Without LIVE: refuses (billed campaign). LIVE=1 calls the real models from the registry.
eval-models:
	@python3 scripts/eval_models.py --layer $(or $(LAYER),all) $(if $(LIVE),--live,) $(if $(MODELS),--models $(MODELS),)

install:
	@if [ -f pyproject.toml ]; then uv sync; else echo "[install] no pyproject.toml — skip"; fi

lint:
	@if [ -f pyproject.toml ]; then \
		uv run ruff check --fix . && uv run ruff format .; \
	else echo "[lint] no pyproject.toml — skip"; fi

# NON-mutating lint for CI (finding L6): fails on drift instead of auto-fixing it.
lint-check:
	@if [ -f pyproject.toml ]; then \
		uv run ruff check . && uv run ruff format --check .; \
	else echo "[lint-check] no pyproject.toml — skip"; fi

test:
	@if [ -f pyproject.toml ]; then \
		uv run pytest -q -m "not eval"; \
	else echo "[test] no pyproject.toml — skip"; fi

# Merge gate: no green eval, no merge (spec.md §7)
# pytest exits 5 when no eval is collected: not an error here — it's
# the orchestrator (anti-empty-gate) that decides whether evals SHOULD have existed.
evals:
	@if [ -f pyproject.toml ] && ls tests evals 2>/dev/null | grep -q .; then \
		uv run pytest -q -m eval; rc=$$?; \
		if [ $$rc -eq 5 ]; then echo "[evals] no eval collected — nothing to gate"; exit 0; fi; \
		exit $$rc; \
	else echo "[evals] no evals yet — skip"; fi

gate: lint test evals
	@echo "✅ gate OK"

# Gate CI: NON-mutating lint (finding L6) — otherwise a fixable/format drift never
# makes CI go red (ruff --fix would silently fix it and exit 0).
gate-ci: lint-check test evals
	@echo "✅ gate-ci OK"
