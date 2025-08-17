# auth/simple_middleware.py
"""
Simple middleware that adds Google access token to requests based on Blueprint Agent ID.
This middleware only adds authentication headers and forwards the request normally.
"""

import logging
from typing import Callable, Optional
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


async def simple_auth_middleware(request: Request, call_next: Callable) -> Response:
    """
    Simple middleware that:
    1. Extracts X-Blueprint-Agent-Id from headers OR accepts any session token
    2. Gets Google access token from Firebase (if agent ID provided)
    3. Adds Authorization header with Bearer token
    4. Forwards request normally
    """
    
    # Extract Blueprint Agent ID
    agent_id = request.headers.get('X-Blueprint-Agent-Id') or request.headers.get('x-blueprint-agent-id')
    
    # Extract session token for MCP Inspector
    session_token = None
    auth_header = request.headers.get('authorization') or request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        session_token = auth_header[7:]  # Remove 'Bearer ' prefix
    
    # Also check other session token headers
    if not session_token:
        for header_name in ['X-Session-Token', 'x-session-token', 'Session-Token', 'session-token']:
            session_token = request.headers.get(header_name)
            if session_token:
                break
    
    if agent_id:
        try:
            # Get Google access token and email from Firebase
            from auth.firebase_service import get_google_credentials_for_agent
            access_token, email = await get_google_credentials_for_agent(agent_id)
            
            if access_token:
                # Create new headers with Authorization
                new_headers = dict(request.headers)
                new_headers['Authorization'] = f'Bearer {access_token}'
                
                # Create new request with updated headers
                request._headers = new_headers
                logger.info(f"✅ Added Google access token for agent: {agent_id}")
            else:
                logger.warning(f"⚠️ No Google access token found for agent: {agent_id}")
            
            # Log email information for user reference
            if email:
                logger.info(f"📧 Agent email available: {email}")
                logger.info(f"💡 To use tools, pass user_google_email='{email}' as parameter")
            else:
                logger.warning(f"⚠️ No email found for agent: {agent_id}")
                
        except Exception as e:
            logger.error(f"❌ Error getting credentials for agent {agent_id}: {e}")
    elif session_token:
        logger.info(f"✅ MCP session token accepted: {session_token[:10]}...")
        # Accept any session token for MCP Inspector - no Firebase lookup needed
    else:
        logger.debug("No Blueprint Agent ID or session token found in request headers")
    
    # Forward request normally
    response = await call_next(request)
    return response


def setup_simple_auth_middleware(app):
    """
    Add the simple auth middleware to a FastAPI/Starlette application.
    """
    app.add_middleware(
        lambda app, handler: lambda request: simple_auth_middleware(request, handler)
    )
    logger.info("✅ Simple auth middleware added to application")
