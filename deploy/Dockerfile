# Image de service Cloud Run — webhook-gateway. Non-root, slim, reproductible (D-1, D-2).
# Les deps runtime viennent de `deploy/requirements-runtime.txt` (généré par deploy_gateway.sh
# depuis `uv export --no-dev` → pas de drift avec pyproject, pas d'outil de dev embarqué).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY deploy/requirements-runtime.txt /app/requirements-runtime.txt
RUN pip install --no-cache-dir -r /app/requirements-runtime.txt

COPY src/gateway /app/gateway

USER app
ENV PORT=8080
EXPOSE 8080
# Cloud Run injecte $PORT ; uvicorn sert l'app ASGI (gateway/asgi.py expose `app`).
CMD ["sh", "-c", "uvicorn gateway.asgi:app --host 0.0.0.0 --port ${PORT:-8080}"]
