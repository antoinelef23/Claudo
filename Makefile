# Lab IA-natif — cibles standard. Tous les hooks et l'orchestrateur passent par ici.
# Les cibles sont tolérantes : tant que le projet Python n'existe pas (pas de pyproject.toml),
# elles no-op proprement pour ne pas casser les hooks sur le squelette vide.

.PHONY: install lint test evals gate

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
evals:
	@if [ -f pyproject.toml ] && ls tests evals 2>/dev/null | grep -q .; then \
		uv run pytest -q -m eval; \
	else echo "[evals] pas encore d'evals — skip"; fi

gate: lint test evals
	@echo "✅ gate OK"
