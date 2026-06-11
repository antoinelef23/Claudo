# Lab IA-natif — cibles standard. Tous les hooks et l'orchestrateur passent par ici.
# Les cibles sont tolérantes : tant que le projet Python n'existe pas (pas de pyproject.toml),
# elles no-op proprement pour ne pas casser les hooks sur le squelette vide.

.PHONY: install lint test evals gate validate run

# Plan-lint d'une feature : make validate FEATURE=work/ma-feature
validate:
	@test -n "$(FEATURE)" || { echo "usage: make validate FEATURE=work/ma-feature"; exit 1; }
	@python3 scripts/orchestrate.py "$(FEATURE)" --validate

# Run orchestré en avant-plan : make run FEATURE=work/ma-feature [SUPERVISED=1]
run:
	@test -n "$(FEATURE)" || { echo "usage: make run FEATURE=work/ma-feature"; exit 1; }
	@caffeinate -i python3 scripts/orchestrate.py "$(FEATURE)" $(if $(SUPERVISED),--supervised,)

install:
	@if [ -f pyproject.toml ]; then uv sync; else echo "[install] pas de pyproject.toml — skip"; fi

lint:
	@if [ -f pyproject.toml ]; then \
		uv run ruff check --fix . && uv run ruff format .; \
	else echo "[lint] pas de pyproject.toml — skip"; fi

test:
	@if [ -f pyproject.toml ]; then \
		uv run pytest -q -m "not eval"; \
	else echo "[test] pas de pyproject.toml — skip"; fi

# Merge gate : pas d'eval verte, pas de merge (spec.md §7)
# pytest sort 5 quand aucune eval n'est collectée : pas une erreur ici — c'est
# l'orchestrateur (anti-gate-vide) qui décide si des evals DEVAIENT exister.
evals:
	@if [ -f pyproject.toml ] && ls tests evals 2>/dev/null | grep -q .; then \
		uv run pytest -q -m eval; rc=$$?; \
		if [ $$rc -eq 5 ]; then echo "[evals] aucune eval collectée — rien à gater"; exit 0; fi; \
		exit $$rc; \
	else echo "[evals] pas encore d'evals — skip"; fi

gate: lint test evals
	@echo "✅ gate OK"
