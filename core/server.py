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
    name="google_workspace"
)

# Configure server for Cloud Run deployment
if hasattr(server, '_app'):
    # Configure the underlying FastAPI app to listen on all interfaces
    import os
    port = int(os.getenv("PORT", WORKSPACE_MCP_PORT))
    # The actual host/port configuration will be handled by the uvicorn server
    # that FastMCP uses internally

# Setup Blueprint auth middleware to extract agent credentials and fetch Google tokens
# Note: Middleware will be set up after server initialization in main.py
logger.info("Blueprint auth middleware will be configured after server initialization")

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

# --- Authentication is handled internally, no public auth tools needed ---
