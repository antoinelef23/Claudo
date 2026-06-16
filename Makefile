# Lab IA-natif — cibles standard. Tous les hooks et l'orchestrateur passent par ici.
# Les cibles sont tolérantes : tant que le projet Python n'existe pas (pas de pyproject.toml),
# elles no-op proprement pour ne pas casser les hooks sur le squelette vide.

.PHONY: install lint lint-check test evals gate ci validate run security secrets-baseline mutation coverage deps-check sbom

# Plan-lint d'une feature : make validate FEATURE=work/ma-feature
validate:
	@test -n "$(FEATURE)" || { echo "usage: make validate FEATURE=work/ma-feature"; exit 1; }
	@python3 scripts/orchestrate.py "$(FEATURE)" --validate

# Run orchestré en avant-plan : make run FEATURE=work/ma-feature [SUPERVISED=1]
# `caffeinate` (macOS) empêche la veille pendant un run long ; absent ailleurs → on s'en passe.
run:
	@test -n "$(FEATURE)" || { echo "usage: make run FEATURE=work/ma-feature"; exit 1; }
	@CAFF=$$(command -v caffeinate); \
	$${CAFF:+$$CAFF -i} python3 scripts/orchestrate.py "$(FEATURE)" $(if $(SUPERVISED),--supervised,)

# Garde-fou fond/forme : make check-content FEATURE=work/ma-feature
# Échoue si le FOND de spec/design a changé sans bump de version (reformat ≠ amendement).
check-content:
	@test -n "$(FEATURE)" || { echo "usage: make check-content FEATURE=work/ma-feature"; exit 1; }
	@python3 scripts/content_guard.py --git "$(FEATURE)/spec.md"
	@if [ -f "$(FEATURE)/design.md" ]; then python3 scripts/content_guard.py --git "$(FEATURE)/design.md"; fi

# Éval des modèles : make eval-models [LIVE=1] [LAYER=behavioral|chain|scorecard|all] [MODELS=a,b]
# Sans LIVE : refuse (campagne facturée). LIVE=1 appelle les vrais modèles du registre.
eval-models:
	@python3 scripts/eval_models.py --layer $(or $(LAYER),all) $(if $(LIVE),--live,) $(if $(MODELS),--models $(MODELS),)

install:
	@if [ -f pyproject.toml ]; then uv sync; else echo "[install] pas de pyproject.toml — skip"; fi

lint:
	@if [ -f pyproject.toml ]; then \
		uv run ruff check --fix . && uv run ruff format .; \
	else echo "[lint] pas de pyproject.toml — skip"; fi

# Lint NON mutant pour la CI : échoue si le code n'est pas clean/formaté (jamais de --fix).
lint-check:
	@if [ -f pyproject.toml ]; then \
		uv run ruff check . && uv run ruff format --check .; \
	else echo "[lint-check] pas de pyproject.toml — skip"; fi

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

# Gate sécurité MÉCANIQUE (déterministe, sans modèle) — complète la revue agentique
# `security-reviewer` au checkpoint. SAST (bandit) + CVE des dépendances RUNTIME (pip-audit,
# scope --no-dev : on ne gate pas sur une CVE d'un outil de dev non livré) + secrets (detect-secrets).
security:
	@if [ -f pyproject.toml ]; then \
		set -e; \
		DIRS="scripts"; [ -d src ] && DIRS="src scripts"; \
		echo "→ bandit (SAST) sur $$DIRS"; \
		uv run bandit -q -r $$DIRS -c pyproject.toml --severity-level medium --confidence-level medium; \
		echo "→ pip-audit (CVE dépendances runtime)"; \
		if uv export --no-dev --no-emit-project --quiet -o .audit-reqs.txt 2>/dev/null; then \
			if uv run pip-audit -r .audit-reqs.txt; then rm -f .audit-reqs.txt; else rm -f .audit-reqs.txt; exit 1; fi; \
		else uv run pip-audit; fi; \
		echo "→ detect-secrets (secrets en clair, fichiers suivis)"; \
		[ -f .secrets.baseline ] || { echo "❌ pas de .secrets.baseline — lance: make secrets-baseline"; exit 1; }; \
		git ls-files -z | xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline; \
		echo "→ deps-check (slopsquatting : dépendances réelles sur PyPI)"; \
		uv run python scripts/deps_check.py; \
		echo "✅ security OK"; \
	else echo "[security] pas de pyproject.toml — skip"; fi

# Anti-slopsquatting seul (R-29) — vérifie l'existence PyPI des dépendances déclarées.
deps-check:
	@uv run python scripts/deps_check.py

# SBOM CycloneDX (supply-chain, D-14) — inventaire signable, attaché à l'image au déploiement.
sbom:
	@if [ -f pyproject.toml ]; then \
		uv run cyclonedx-py environment -o sbom.json && echo "✅ SBOM → sbom.json"; \
	else echo "[sbom] pas de pyproject.toml — skip"; fi

# (Re)génère la baseline detect-secrets (allowlist auditée des faux positifs). À committer.
secrets-baseline:
	@uv run detect-secrets scan > .secrets.baseline && echo "✅ .secrets.baseline régénérée"

# Anti-tautologie (R-32) : mutation testing. Injecte des bugs dans la src (cf. [tool.mutmut])
# et vérifie que les evals les ATTRAPENT. Une eval verte qui ne tue aucun mutant est un faux
# filet — typique des tests écrits par l'agent. OPT-IN (lent) : jamais dans `make ci`.
mutation:
	@if [ -f pyproject.toml ]; then \
		uv run mutmut run; uv run mutmut results; \
	else echo "[mutation] pas de pyproject.toml — skip"; fi

# Couverture de ligne (plancher) pour le code testé EN PROCESS (features). PATHS et COV_MIN
# surchargeables : `make coverage PATHS=src/webhooks COV_MIN=90`. NB : l'orchestrateur (scripts/)
# est couvert par des tests d'INTÉGRATION en sous-process → sa couverture ligne est sous-estimée,
# utiliser `make mutation` pour lui. Opt-in : jamais dans `make ci`.
coverage:
	@if [ -f pyproject.toml ]; then \
		uv run pytest -q -m "not eval" --cov=$(or $(PATHS),src) --cov-report=term-missing --cov-fail-under=$(or $(COV_MIN),0); \
	else echo "[coverage] pas de pyproject.toml — skip"; fi

gate: lint test evals security
	@echo "✅ gate OK"

# Gate de CI : identique mais lint NON mutant (échoue sur format non conforme au lieu de le corriger).
ci: lint-check test evals security
	@echo "✅ ci OK"
