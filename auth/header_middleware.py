# auth/header_middleware.py

import logging
from typing import Optional, Callable, Any
from starlette.requests import Request
from starlette.responses import Response

from core.context import set_access_token_from_headers

logger = logging.getLogger(__name__)


def extract_blueprint_credentials_from_request(request: Request) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract Blueprint agent credentials from request headers.
    
    Looks for the following headers:
    1. X-Blueprint-Agent-Id: <agent_id>
    2. X-Blueprint-API-Key: <api_key> (not validated for now)
    3. Authorization: Bearer <token> or X-Session-Token: <token> (for MCP apps)
    
    Args:
        request: The Starlette/FastAPI request object
        
    Returns:
        Tuple of (agent_id, api_key, session_token) if found, (None, None, None) otherwise.
    """
    if not request or not hasattr(request, 'headers'):
        return None, None, None
    
    headers = request.headers
    
    # Extract Blueprint Agent ID
    agent_id = None
    for header_name in ['X-Blueprint-Agent-Id', 'x-blueprint-agent-id']:
        agent_id = headers.get(header_name)
        if agent_id:
            logger.debug(f"Found Blueprint Agent ID in {header_name} header")
            break
    
    # Extract Blueprint API Key (not validated for now)
    api_key = None
    for header_name in ['X-Blueprint-API-Key', 'x-blueprint-api-key']:
        api_key = headers.get(header_name)
        if api_key:
            logger.debug(f"Found Blueprint API Key in {header_name} header")
            break
    
    # Extract Session Token for MCP applications
    session_token = None
    # Try Authorization Bearer token first
    auth_header = headers.get('authorization') or headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        session_token = auth_header[7:]  # Remove 'Bearer ' prefix
        logger.debug("Found session token in Authorization header")
    else:
        # Try other session token headers
        for header_name in ['X-Session-Token', 'x-session-token', 'Session-Token', 'session-token']:
            session_token = headers.get(header_name)
            if session_token:
                logger.debug(f"Found session token in {header_name} header")
                break
    
    if not agent_id and not session_token:
        logger.debug("No Blueprint Agent ID or session token found in request headers")
    
    return agent_id, api_key, session_token


async def blueprint_auth_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware to extract Blueprint agent credentials from request headers,
    fetch the Google access token from Firebase, and set it in the context
    for the duration of the request.
    
    This middleware should be added to the FastMCP server to automatically
    extract Blueprint credentials from headers and make the Google access token
    available to the authentication system.
    
    Args:
        request: The incoming request
        call_next: The next middleware/handler in the chain
        
    Returns:
        The response from the next handler
    """
    # Extract Blueprint credentials from headers
    agent_id, api_key, session_token = extract_blueprint_credentials_from_request(request)
    
    # Log all headers for debugging MCP app connections
    logger.debug(f"Request headers: {dict(request.headers)}")
    
    if agent_id:
        try:
            # Import here to avoid circular imports
            from auth.firebase_service import get_google_access_token_for_agent
            
            # Get the Google access token from Firebase
            access_token = await get_google_access_token_for_agent(agent_id)
            
            if access_token:
                # Set the token in context for the duration of this request
                set_access_token_from_headers(access_token)
                logger.debug(f"Set Google access token in request context for agent: {agent_id}")
            else:
                logger.warning(f"No Google access token found for Blueprint agent: {agent_id}")
                
        except Exception as e:
            logger.error(f"Error retrieving Google access token for agent {agent_id}: {e}")
    elif session_token:
        logger.info(f"MCP session token found: {session_token[:10]}...")
        # For now, we'll accept any session token - in production you'd validate it
        # You could map session tokens to agent IDs here if needed
        logger.debug("Session token accepted - continuing without Firebase lookup")
    else:
        logger.debug("No Blueprint Agent ID or session token found in request headers")
    
    # Continue with the request
    response = await call_next(request)
    return response


def setup_auth_middleware(app: Any):
    """
    Setup the Blueprint auth middleware on a FastAPI/Starlette application.
    
    Args:
        app: The FastAPI/Starlette application instance
    """
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        app.add_middleware(BaseHTTPMiddleware, dispatch=blueprint_auth_middleware)
        logger.info("Blueprint auth middleware added to application")
    except ImportError as e:
        logger.warning(f"Could not add auth middleware: {e}")
