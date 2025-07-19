import logging
import os
from typing import Optional
from importlib import metadata

from fastapi.responses import JSONResponse

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request

from auth.oauth_callback_server import get_oauth_redirect_uri

# Import shared configuration
from auth.scopes import (
    OAUTH_STATE_TO_SESSION_ID_MAP,
    USERINFO_EMAIL_SCOPE,
    OPENID_SCOPE,
    CALENDAR_READONLY_SCOPE,
    CALENDAR_EVENTS_SCOPE,
    DRIVE_READONLY_SCOPE,
    DRIVE_FILE_SCOPE,
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    GMAIL_MODIFY_SCOPE,
    GMAIL_LABELS_SCOPE,
    BASE_SCOPES,
    CALENDAR_SCOPES,
    DRIVE_SCOPES,
    GMAIL_SCOPES,
    DOCS_READONLY_SCOPE,
    DOCS_WRITE_SCOPE,
    CHAT_READONLY_SCOPE,
    CHAT_WRITE_SCOPE,
    CHAT_SPACES_SCOPE,
    CHAT_SCOPES,
    SHEETS_READONLY_SCOPE,
    SHEETS_WRITE_SCOPE,
    SHEETS_SCOPES,
    FORMS_BODY_SCOPE,
    FORMS_BODY_READONLY_SCOPE,
    FORMS_RESPONSES_READONLY_SCOPE,
    FORMS_SCOPES,
    SLIDES_SCOPE,
    SLIDES_READONLY_SCOPE,
    SLIDES_SCOPES,
    TASKS_SCOPE,
    TASKS_READONLY_SCOPE,
    TASKS_SCOPES,
    SCOPES
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKSPACE_MCP_PORT = int(os.getenv("PORT", os.getenv("WORKSPACE_MCP_PORT", 8000)))
WORKSPACE_MCP_BASE_URI = os.getenv("WORKSPACE_MCP_BASE_URI", "http://localhost")
USER_GOOGLE_EMAIL = os.getenv("USER_GOOGLE_EMAIL", None)

# Transport mode detection (will be set by main.py)
_current_transport_mode = "stdio"  # Default to stdio

# Basic MCP server instance
server = FastMCP(
    name="google_workspace",
    server_url=f"{WORKSPACE_MCP_BASE_URI}:{WORKSPACE_MCP_PORT}/mcp",
    port=WORKSPACE_MCP_PORT,
    host="0.0.0.0"
)

def set_transport_mode(mode: str):
    """Set the current transport mode for OAuth callback handling."""
    global _current_transport_mode
    _current_transport_mode = mode
    logger.info(f"Transport mode set to: {mode}")

def get_oauth_redirect_uri_for_current_mode() -> str:
    """Get OAuth redirect URI based on current transport mode."""
    return get_oauth_redirect_uri(WORKSPACE_MCP_PORT, WORKSPACE_MCP_BASE_URI)

# Health check endpoint
@server.custom_route("/health", methods=["GET"])
async def health_check(request: Request):
    """Health check endpoint for container orchestration."""
    try:
        version = metadata.version("workspace-mcp")
    except metadata.PackageNotFoundError:
        version = "dev"
    return JSONResponse({
        "status": "healthy",
        "service": "workspace-mcp",
        "version": version,
        "transport": _current_transport_mode
    })

# --- Public tool: refresh_auth ---

@server.tool()
async def refresh_auth() -> str:
    """Refresh Google OAuth access token using the stored refresh token (non-interactive).

    Usage: Call this tool whenever an operation fails due to expired/invalid
    credentials. It attempts to refresh the access token in-place so that
    subsequent calls succeed without requiring any browser-based authentication.
    """

    from auth.google_auth import refresh_auth as _refresh_auth  # Lazy import to avoid cycles

    try:
        await _refresh_auth()
        return "✅ Google OAuth access token refreshed successfully. Please retry your previous command."
    except Exception as e:
        logger.error("refresh_auth tool failed: %s", e, exc_info=True)
        raise Exception(f"Failed to refresh Google auth token: {e}")
