#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="polletask-dev"
REGION="us-central1"
REPO="workspace-mcp"

# Allow overriding the Cloud Run service name.
# 1) If $SERVICE env var is set use that
# 2) Else if the first CLI arg is provided use that
# 3) Fallback to "google-workspace-mcp"
DEFAULT_SERVICE="google-workspace-mcp-test"
if [[ -n "${SERVICE:-}" ]]; then
  SERVICE="$SERVICE"
elif [[ $# -ge 1 ]]; then
  SERVICE="$1"; shift
else
  SERVICE="$DEFAULT_SERVICE"
fi

# Fully-qualified image reference (built & pushed below)
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/google-workspace-mcp:latest"

echo "▶️  Configuring gcloud"
gcloud config set project "$PROJECT_ID"
gcloud auth configure-docker "$REGION-docker.pkg.dev"

echo "▶️  Creating Artifact Registry repo (if needed)"
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" 2>/dev/null || true

echo "▶️  Building & pushing container (amd64)"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

# ----------------------------------------------------------------------------
#  Expect a local .env file with the four required variables:
#      GOOGLE_OAUTH_CLIENT_ID
#      GOOGLE_OAUTH_CLIENT_SECRET
#      GOOGLE_OAUTH_ACCESS_TOKEN
#      GOOGLE_OAUTH_REFRESH_TOKEN
#  These are loaded and passed to the container via CLI flags only – no
#  Secret Manager or env-var wiring required.
# ----------------------------------------------------------------------------

if [[ -f .env ]]; then
  echo "▶️  Loading credentials from .env"
  # shellcheck disable=SC1091
  set -a; source .env; set +a
else
  echo "❌  .env file not found. Create it with the required credentials." >&2
  exit 1
fi

echo "▶️  Preparing CLI credential flags"

# Verify required variables are set in .env
for var in GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_ACCESS_TOKEN GOOGLE_OAUTH_REFRESH_TOKEN; do
  if [[ -z "${!var:-}" ]]; then
    echo "❌  $var is not set in .env" >&2
    exit 1
  fi
done

# Base CLI args (credentials etc.)
CLI_ARGS="run,main.py,--transport,streamable-http,--single-user,\
--client-id,$GOOGLE_OAUTH_CLIENT_ID,\
--client-secret,$GOOGLE_OAUTH_CLIENT_SECRET,\
--access-token,$GOOGLE_OAUTH_ACCESS_TOKEN,\
--refresh-token,$GOOGLE_OAUTH_REFRESH_TOKEN,\
--tools,gmail,calendar,docs"

echo "▶️  Deploying with tool subset: gmail, calendar, docs"

echo "▶️  Deploying to Cloud Run (CLI flags)"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8000 \
  --command "uv" \
  --args "$CLI_ARGS" \
  --quiet

URL=$(gcloud run services describe "$SERVICE" \
      --region "$REGION" --format='value(status.url)')
echo "✅  Deployed!  MCP endpoint: ${URL}/mcp"