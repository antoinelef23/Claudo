#!/usr/bin/env bash
# Déploiement webhook-gateway → Cloud Run (D-14/D-15). Pipeline : gate vert → SBOM → build amd64
# → Artifact Registry → deploy. Mise en prod = décision humaine (ce script est lancé par l'Owner).
set -euo pipefail

PROJECT="${GCP_PROJECT:-lil-onboard-gcp}"
REGION="${GCP_REGION:-europe-west1}"
REPO="${AR_REPO:-lab-services}"
SERVICE="webhook-gateway"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo latest)"
SECRET_ACME="${GATEWAY_SECRET_ACME:-acme-test-key}"
READ_TOKEN="${GATEWAY_READ_TOKEN:-read-test-token}"

cd "$(dirname "$0")/.."

echo "▶ 1/5 — gate (make ci) + SBOM"
make ci
make sbom

echo "▶ 2/5 — requirements runtime (reproductible, sans dev)"
uv export --no-dev --no-emit-project --quiet -o deploy/requirements-runtime.txt

echo "▶ 3/5 — Artifact Registry (${REPO} @ ${REGION})"
gcloud artifacts repositories describe "$REPO" --location="$REGION" --project="$PROJECT" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker \
    --location="$REGION" --project="$PROJECT" --description="Lab services"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "▶ 4/5 — build amd64 + push (${IMAGE}:${TAG})"
docker build --platform linux/amd64 -f deploy/Dockerfile -t "${IMAGE}:${TAG}" -t "${IMAGE}:latest" .
docker push "${IMAGE}:${TAG}"
docker push "${IMAGE}:latest"

echo "▶ 5/5 — deploy Cloud Run"
gcloud run deploy "$SERVICE" \
  --image="${IMAGE}:${TAG}" \
  --region="$REGION" --project="$PROJECT" --platform=managed \
  --allow-unauthenticated \
  --cpu=1 --memory=512Mi --concurrency=80 --timeout=30 \
  --min-instances=0 --max-instances=4 \
  --set-env-vars="GATEWAY_SECRET_ACME=${SECRET_ACME},GATEWAY_READ_TOKEN=${READ_TOKEN}" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --project="$PROJECT" --format='value(status.url)')"
echo "✅ déployé : $URL"
echo "$URL" > deploy/.last-url
