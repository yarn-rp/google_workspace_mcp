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
#  Firebase Blueprint Authentication Mode:
#  The MCP now uses Firebase service account for authentication.
#  It retrieves Google access tokens from Firestore based on Blueprint Agent IDs.
#  No individual OAuth credentials are needed in the environment.
# ----------------------------------------------------------------------------

echo "▶️  Configuring Firebase service account authentication"

# The service will use Application Default Credentials from the Cloud Run environment
# which automatically provides access to the polletask-dev project's Firestore

echo "▶️  Creating environment variables file for Firebase mode"
# Create a temporary env file for gcloud in YAML format
TEMP_ENV_FILE=$(mktemp)
cat > "$TEMP_ENV_FILE" << EOF
# Firebase project configuration
GOOGLE_CLOUD_PROJECT: "$PROJECT_ID"
# No OAuth credentials needed - using Firebase service account
EOF

echo "▶️  Deploying to Cloud Run with Firebase authentication"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8000 \
  --env-vars-file "$TEMP_ENV_FILE" \
  --quiet

# Clean up temporary file
rm "$TEMP_ENV_FILE"

URL=$(gcloud run services describe "$SERVICE" \
      --region "$REGION" --format='value(status.url)')
echo "✅  Deployed!  MCP endpoint: ${URL}/mcp"