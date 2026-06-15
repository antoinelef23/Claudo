# Lab IA-natif — image SANDBOX pour exécuter l'orchestrateur hors-Mac.
#
# ⚠️ MODÈLE DE MENACE : l'orchestrateur lance du code écrit par un modèle (l'implementer tourne
# avec `--permission-mode acceptEdits` + une whitelist Bash incluant python3/uv/make → exécution
# de code arbitraire PAR CONCEPTION). Cette image est jetable et SANS secret : ne JAMAIS y monter
# de credentials prod (SSH, gcloud, AWS…), ne lui donner que la clé API Anthropic, et contrôler
# l'egress réseau (voir scripts/run_sandboxed.sh + docs/DEPLOYMENT.md).
FROM python:3.12-slim

# git (commits scopés) + node/npm (CLI claude) + build essentials minimaux
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# uv (gestion des deps du lab) + CLI claude headless (le runtime des agents)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && npm install -g @anthropic-ai/claude-code

# Utilisateur non-root : l'agent ne tourne jamais en root dans le sandbox
RUN useradd -m -u 10001 lab
WORKDIR /lab

# Deps d'abord (cache) puis le code
COPY --chown=lab:lab pyproject.toml uv.lock* ./
RUN uv sync --frozen 2>/dev/null || uv sync
COPY --chown=lab:lab . .
RUN chown -R lab:lab /lab
USER lab

# CLI claude réauthentifiée via ANTHROPIC_API_KEY (passée au `docker run`, jamais bakée)
ENV LAB_NO_NOTIFY=1 \
    LAB_APPROVALS_DIR=/approvals

# Usage : docker run ... lab-ia-natif work/ma-feature  (voir scripts/run_sandboxed.sh)
ENTRYPOINT ["python3", "scripts/orchestrate.py"]
CMD ["--help"]
