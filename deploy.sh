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
#  Expect a local .env file with all required OAuth variables:
#      MCP_SINGLE_USER_MODE
#      GOOGLE_OAUTH_CLIENT_ID
#      GOOGLE_OAUTH_CLIENT_SECRET
#      GOOGLE_OAUTH_TOKEN (or GOOGLE_OAUTH_ACCESS_TOKEN)
#      GOOGLE_OAUTH_REFRESH_TOKEN
#      GOOGLE_OAUTH_SCOPES
#  These are loaded and passed to the container as environment variables.
# ----------------------------------------------------------------------------

if [[ -f .env ]]; then
  echo "▶️  Loading credentials from .env"
  # shellcheck disable=SC1091
  set -a; source .env; set +a
else
  echo "❌  .env file not found. Create it with the required credentials." >&2
  exit 1
fi

echo "▶️  Preparing environment variables for container"

# Verify required variables are set in .env
for var in MCP_SINGLE_USER_MODE GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN GOOGLE_OAUTH_SCOPES; do
  if [[ -z "${!var:-}" ]]; then
    echo "❌  $var is not set in .env" >&2
    exit 1
  fi
done

# Check for either GOOGLE_OAUTH_TOKEN or GOOGLE_OAUTH_ACCESS_TOKEN
if [[ -z "${GOOGLE_OAUTH_TOKEN:-}" && -z "${GOOGLE_OAUTH_ACCESS_TOKEN:-}" ]]; then
  echo "❌  Either GOOGLE_OAUTH_TOKEN or GOOGLE_OAUTH_ACCESS_TOKEN must be set in .env" >&2
  exit 1
fi

# Use GOOGLE_OAUTH_TOKEN if available, otherwise use GOOGLE_OAUTH_ACCESS_TOKEN
if [[ -n "${GOOGLE_OAUTH_TOKEN:-}" ]]; then
  ACCESS_TOKEN="$GOOGLE_OAUTH_TOKEN"
else
  ACCESS_TOKEN="$GOOGLE_OAUTH_ACCESS_TOKEN"
fi

echo "▶️  Creating temporary environment variables file"
# Create a temporary env file for gcloud in YAML format
TEMP_ENV_FILE=$(mktemp)
cat > "$TEMP_ENV_FILE" << EOF
MCP_SINGLE_USER_MODE: "$MCP_SINGLE_USER_MODE"
GOOGLE_OAUTH_CLIENT_ID: "$GOOGLE_OAUTH_CLIENT_ID"
GOOGLE_OAUTH_CLIENT_SECRET: "$GOOGLE_OAUTH_CLIENT_SECRET"
GOOGLE_OAUTH_TOKEN: "$ACCESS_TOKEN"
GOOGLE_OAUTH_REFRESH_TOKEN: "$GOOGLE_OAUTH_REFRESH_TOKEN"
GOOGLE_OAUTH_SCOPES: "$GOOGLE_OAUTH_SCOPES"
EOF

echo "▶️  Deploying to Cloud Run (environment variables file)"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8000 \
  --command "uv" \
  --args "run,main.py,--single-user,--transport,streamable-http,--tools,gmail,calendar,docs" \
  --env-vars-file "$TEMP_ENV_FILE" \
  --quiet

# Clean up temporary file
rm "$TEMP_ENV_FILE"

URL=$(gcloud run services describe "$SERVICE" \
      --region "$REGION" --format='value(status.url)')
echo "✅  Deployed!  MCP endpoint: ${URL}/mcp"