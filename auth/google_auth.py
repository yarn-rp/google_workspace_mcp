# auth/google_auth.py

import asyncio
import json
import jwt
import logging
import os

from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from auth.scopes import OAUTH_STATE_TO_SESSION_ID_MAP, SCOPES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Constants
def get_default_credentials_dir():
    """Get the default credentials directory path, preferring user-specific locations."""
    # Check for explicit environment variable override
    if os.getenv("GOOGLE_MCP_CREDENTIALS_DIR"):
        return os.getenv("GOOGLE_MCP_CREDENTIALS_DIR")

    # Use user home directory for credentials storage
    home_dir = os.path.expanduser("~")
    if home_dir and home_dir != "~":  # Valid home directory found
        return os.path.join(home_dir, ".google_workspace_mcp", "credentials")

    # Fallback to current working directory if home directory is not accessible
    return os.path.join(os.getcwd(), ".credentials")


DEFAULT_CREDENTIALS_DIR = get_default_credentials_dir()

# Centralized Client Secrets Path Logic
_client_secrets_env = os.getenv("GOOGLE_CLIENT_SECRET_PATH") or os.getenv(
    "GOOGLE_CLIENT_SECRETS"
)
if _client_secrets_env:
    CONFIG_CLIENT_SECRETS_PATH = _client_secrets_env
else:
    # Assumes this file is in auth/ and client_secret.json is in the root
    CONFIG_CLIENT_SECRETS_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "client_secret.json",
    )

# --- Helper Functions ---


def _find_any_credentials(
    base_dir: str = DEFAULT_CREDENTIALS_DIR,
) -> Optional[Credentials]:
    """
    Find and load credentials from environment variables.
    Used in single-user mode to bypass session-to-OAuth mapping.

    Returns:
        Credentials object from environment variables, or None if not all required vars are set.
    """

    print("IN _find_any_credentials")
    logger.info("IN _find_any_credentials")
    # Load credentials from environment variables
    token = os.getenv("GOOGLE_OAUTH_TOKEN")
    refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    token_uri = os.getenv("GOOGLE_OAUTH_TOKEN_URI", "https://oauth2.googleapis.com/token")
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    scopes_str = os.getenv("GOOGLE_OAUTH_SCOPES")
    
    # Check if all required environment variables are present
    if not all([token, refresh_token, client_id, client_secret, scopes_str]):
        logger.info("[single-user] Not all required OAuth environment variables are set")
        return None
    
    # Parse scopes from comma-separated string
    scopes = [scope.strip() for scope in scopes_str.split(",") if scope.strip()]
    
    try:
        credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )
        logger.info("[single-user] Found credentials from environment variables")
        return credentials
    except Exception as e:
        logger.warning(f"[single-user] Error creating credentials from environment variables: {e}")
        return None


def _get_user_credential_path(
    user_google_email: str, base_dir: str = DEFAULT_CREDENTIALS_DIR
) -> str:
    """Constructs the path to a user's credential file."""
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        logger.info(f"Created credentials directory: {base_dir}")
    return os.path.join(base_dir, f"{user_google_email}.json")


def save_credentials_to_file(
    user_google_email: str,
    credentials: Credentials,
    base_dir: str = DEFAULT_CREDENTIALS_DIR,
):
    """Saves user credentials to a file."""
    creds_path = _get_user_credential_path(user_google_email, base_dir)
    creds_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }
    try:
        with open(creds_path, "w") as f:
            json.dump(creds_data, f)
        logger.info(f"Credentials saved for user {user_google_email} to {creds_path}")
    except IOError as e:
        logger.error(
            f"Error saving credentials for user {user_google_email} to {creds_path}: {e}"
        )
        raise


def load_credentials_from_file(
    user_google_email: str, base_dir: str = DEFAULT_CREDENTIALS_DIR
) -> Optional[Credentials]:
    """Loads user credentials from a file."""
    creds_path = _get_user_credential_path(user_google_email, base_dir)
    if not os.path.exists(creds_path):
        logger.info(
            f"No credentials file found for user {user_google_email} at {creds_path}"
        )
        return None

    try:
        with open(creds_path, "r") as f:
            creds_data = json.load(f)

        # Parse expiry if present
        expiry = None
        if creds_data.get("expiry"):
            try:
                expiry = datetime.fromisoformat(creds_data["expiry"])
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Could not parse expiry time for {user_google_email}: {e}"
                )

        credentials = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes"),
            expiry=expiry,
        )
        logger.debug(
            f"Credentials loaded for user {user_google_email} from {creds_path}"
        )
        return credentials
    except (IOError, json.JSONDecodeError, KeyError) as e:
        logger.error(
            f"Error loading or parsing credentials for user {user_google_email} from {creds_path}: {e}"
        )
        return None


def load_client_secrets_from_env() -> Optional[Dict[str, Any]]:
    """
    Loads the client secrets from environment variables.

    Environment variables used:
        - GOOGLE_OAUTH_CLIENT_ID: OAuth 2.0 client ID
        - GOOGLE_OAUTH_CLIENT_SECRET: OAuth 2.0 client secret
        - GOOGLE_OAUTH_REDIRECT_URI: (optional) OAuth redirect URI

    Returns:
        Client secrets configuration dict compatible with Google OAuth library,
        or None if required environment variables are not set.
    """
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")

    if client_id and client_secret:
        # Create config structure that matches Google client secrets format
        web_config = {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        }

        # Add redirect_uri if provided via environment variable
        if redirect_uri:
            web_config["redirect_uris"] = [redirect_uri]

        # Return the full config structure expected by Google OAuth library
        config = {"web": web_config}

        logger.info("Loaded OAuth client credentials from environment variables")
        return config

    logger.debug("OAuth client credentials not found in environment variables")
    return None


def load_client_secrets(client_secrets_path: str) -> Dict[str, Any]:
    """
    Loads the client secrets from environment variables (preferred) or from the client secrets file.

    Priority order:
    1. Environment variables (GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET)
    2. File-based credentials at the specified path

    Args:
        client_secrets_path: Path to the client secrets JSON file (used as fallback)

    Returns:
        Client secrets configuration dict

    Raises:
        ValueError: If client secrets file has invalid format
        IOError: If file cannot be read and no environment variables are set
    """
    # First, try to load from environment variables
    env_config = load_client_secrets_from_env()
    if env_config:
        # Extract the "web" config from the environment structure
        return env_config["web"]

    # Fall back to loading from file
    try:
        with open(client_secrets_path, "r") as f:
            client_config = json.load(f)
            # The file usually contains a top-level key like "web" or "installed"
            if "web" in client_config:
                logger.info(
                    f"Loaded OAuth client credentials from file: {client_secrets_path}"
                )
                return client_config["web"]
            elif "installed" in client_config:
                logger.info(
                    f"Loaded OAuth client credentials from file: {client_secrets_path}"
                )
                return client_config["installed"]
            else:
                logger.error(
                    f"Client secrets file {client_secrets_path} has unexpected format."
                )
                raise ValueError("Invalid client secrets file format")
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Error loading client secrets file {client_secrets_path}: {e}")
        raise


def check_client_secrets() -> Optional[str]:
    """
    Checks for the presence of OAuth client secrets, either as environment
    variables or as a file.

    Returns:
        An error message string if secrets are not found, otherwise None.
    """
    env_config = load_client_secrets_from_env()
    if not env_config and not os.path.exists(CONFIG_CLIENT_SECRETS_PATH):
        logger.error(
            f"OAuth client credentials not found. No environment variables set and no file at {CONFIG_CLIENT_SECRETS_PATH}"
        )
        return f"OAuth client credentials not found. Please set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables or provide a client secrets file at {CONFIG_CLIENT_SECRETS_PATH}."
    return None


def create_oauth_flow(
    scopes: List[str], redirect_uri: str, state: Optional[str] = None
) -> Flow:
    """Creates an OAuth flow using environment variables or client secrets file."""
    # Try environment variables first
    env_config = load_client_secrets_from_env()
    if env_config:
        # Use client config directly
        flow = Flow.from_client_config(
            env_config, scopes=scopes, redirect_uri=redirect_uri, state=state
        )
        logger.debug("Created OAuth flow from environment variables")
        return flow

    # Fall back to file-based config
    if not os.path.exists(CONFIG_CLIENT_SECRETS_PATH):
        raise FileNotFoundError(
            f"OAuth client secrets file not found at {CONFIG_CLIENT_SECRETS_PATH} and no environment variables set"
        )

    flow = Flow.from_client_secrets_file(
        CONFIG_CLIENT_SECRETS_PATH,
        scopes=scopes,
        redirect_uri=redirect_uri,
        state=state,
    )
    logger.debug(
        f"Created OAuth flow from client secrets file: {CONFIG_CLIENT_SECRETS_PATH}"
    )
    return flow


# --- Core OAuth Logic ---


async def start_auth_flow(
    mcp_session_id: Optional[str],
    user_google_email: Optional[str],
    service_name: str,  # e.g., "Google Calendar", "Gmail" for user messages
    redirect_uri: str,  # Added redirect_uri as a required parameter
) -> str:
    """
    Initiates the Google OAuth flow and returns an actionable message for the user.

    Args:
        mcp_session_id: The active MCP session ID.
        user_google_email: The user's specified Google email, if provided.
        service_name: The name of the Google service requiring auth (for user messages).
        redirect_uri: The URI Google will redirect to after authorization.

    Returns:
        A formatted string containing guidance for the LLM/user.

    Raises:
        Exception: If the OAuth flow cannot be initiated.
    """
    initial_email_provided = bool(
        user_google_email
        and user_google_email.strip()
        and user_google_email.lower() != "default"
    )
    user_display_name = (
        f"{service_name} for '{user_google_email}'"
        if initial_email_provided
        else service_name
    )

    logger.info(
        f"[start_auth_flow] Initiating auth for {user_display_name} (session: {mcp_session_id}) with global SCOPES."
    )

    try:
        if "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ and (
            "localhost" in redirect_uri or "127.0.0.1" in redirect_uri
        ):  # Use passed redirect_uri
            logger.warning(
                "OAUTHLIB_INSECURE_TRANSPORT not set. Setting it for localhost/local development."
            )
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        oauth_state = os.urandom(16).hex()
        if mcp_session_id:
            OAUTH_STATE_TO_SESSION_ID_MAP[oauth_state] = mcp_session_id
            logger.info(
                f"[start_auth_flow] Stored mcp_session_id '{mcp_session_id}' for oauth_state '{oauth_state}'."
            )

        flow = create_oauth_flow(
            scopes=SCOPES,  # Use global SCOPES
            redirect_uri=redirect_uri,  # Use passed redirect_uri
            state=oauth_state,
        )

        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        logger.info(
            f"Auth flow started for {user_display_name}. State: {oauth_state}. Advise user to visit: {auth_url}"
        )

        message_lines = [
            f"**ACTION REQUIRED: Google Authentication Needed for {user_display_name}**\n",
            f"To proceed, the user must authorize this application for {service_name} access using all required permissions.",
            "**LLM, please present this exact authorization URL to the user as a clickable hyperlink:**",
            f"Authorization URL: {auth_url}",
            f"Markdown for hyperlink: [Click here to authorize {service_name} access]({auth_url})\n",
            "**LLM, after presenting the link, instruct the user as follows:**",
            "1. Click the link and complete the authorization in their browser.",
        ]
        session_info_for_llm = (
            f" (this will link to your current session {mcp_session_id})"
            if mcp_session_id
            else ""
        )

        if not initial_email_provided:
            message_lines.extend(
                [
                    f"2. After successful authorization{session_info_for_llm}, the browser page will display the authenticated email address.",
                    "   **LLM: Instruct the user to provide you with this email address.**",
                    "3. Once you have the email, **retry their original command, ensuring you include this `user_google_email`.**",
                ]
            )
        else:
            message_lines.append(
                f"2. After successful authorization{session_info_for_llm}, **retry their original command**."
            )

        message_lines.append(
            f"\nThe application will use the new credentials. If '{user_google_email}' was provided, it must match the authenticated account."
        )
        return "\n".join(message_lines)

    except FileNotFoundError as e:
        error_text = f"OAuth client credentials not found: {e}. Please either:\n1. Set environment variables: GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET\n2. Ensure '{CONFIG_CLIENT_SECRETS_PATH}' file exists"
        logger.error(error_text, exc_info=True)
        raise Exception(error_text)
    except Exception as e:
        error_text = f"Could not initiate authentication for {user_display_name} due to an unexpected error: {str(e)}"
        logger.error(
            f"Failed to start the OAuth flow for {user_display_name}: {e}",
            exc_info=True,
        )
        raise Exception(error_text)


def handle_auth_callback(
    scopes: List[str],
    authorization_response: str,
    redirect_uri: str,
    credentials_base_dir: str = DEFAULT_CREDENTIALS_DIR,
    session_id: Optional[str] = None,
    client_secrets_path: Optional[
        str
    ] = None,  # Deprecated: kept for backward compatibility
) -> Tuple[str, Credentials]:
    """
    Handles the callback from Google, exchanges the code for credentials,
    fetches user info, determines user_google_email, saves credentials (file & session),
    and returns them.

    Args:
        scopes: List of OAuth scopes requested.
        authorization_response: The full callback URL from Google.
        redirect_uri: The redirect URI.
        credentials_base_dir: Base directory for credential files.
        session_id: Optional MCP session ID to associate with the credentials.
        client_secrets_path: (Deprecated) Path to client secrets file. Ignored if environment variables are set.

    Returns:
        A tuple containing the user_google_email and the obtained Credentials object.

    Raises:
        ValueError: If the state is missing or doesn't match.
        FlowExchangeError: If the code exchange fails.
        HttpError: If fetching user info fails.
    """
    try:
        # Log deprecation warning if old parameter is used
        if client_secrets_path:
            logger.warning(
                "The 'client_secrets_path' parameter is deprecated. Use GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables instead."
            )

        # Allow HTTP for localhost in development
        if "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ:
            logger.warning(
                "OAUTHLIB_INSECURE_TRANSPORT not set. Setting it for localhost development."
            )
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        flow = create_oauth_flow(scopes=scopes, redirect_uri=redirect_uri)

        # Exchange the authorization code for credentials
        # Note: fetch_token will use the redirect_uri configured in the flow
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        logger.info("Successfully exchanged authorization code for tokens.")

        # Get user info to determine user_id (using email here)
        user_info = get_user_info(credentials)
        if not user_info or "email" not in user_info:
            logger.error("Could not retrieve user email from Google.")
            raise ValueError("Failed to get user email for identification.")

        user_google_email = user_info["email"]
        logger.info(f"Identified user_google_email: {user_google_email}")

        # Save the credentials to file
        save_credentials_to_file(user_google_email, credentials, credentials_base_dir)

        # If session_id is provided, also save to session cache
        if session_id:
            # session cache removed – nothing to update
            pass

        return user_google_email, credentials

    except Exception as e:  # Catch specific exceptions like FlowExchangeError if needed
        logger.error(f"Error handling auth callback: {e}")
        raise  # Re-raise for the caller


def get_credentials(
    user_google_email: Optional[str],  # Can be None if relying on session_id
    required_scopes: List[str],
    client_secrets_path: Optional[str] = None,
    credentials_base_dir: str = DEFAULT_CREDENTIALS_DIR,
    session_id: Optional[str] = None,
) -> Optional[Credentials]:
    """
    Retrieves stored credentials, prioritizing session, then file. Refreshes if necessary.
    If credentials are loaded from file and a session_id is present, they are cached in the session.
    In single-user mode, bypasses session mapping and uses any available credentials.

    Args:
        user_google_email: Optional user's Google email.
        required_scopes: List of scopes the credentials must have.
        client_secrets_path: Path to client secrets, required for refresh if not in creds.
        credentials_base_dir: Base directory for credential files.
        session_id: Optional MCP session ID.

    Returns:
        Valid Credentials object or None.
    """
    # Check for single-user mode
    print("MCP_SINGLE_USER_MODE", os.getenv("MCP_SINGLE_USER_MODE"))
    logger.info("MCP_SINGLE_USER_MODE", os.getenv("MCP_SINGLE_USER_MODE"))
    if os.getenv("MCP_SINGLE_USER_MODE") == "1":
        logger.info(
            f"[get_credentials] Single-user mode: bypassing session mapping, finding any credentials"
        )
        credentials = _find_any_credentials(credentials_base_dir)
        if not credentials:
            logger.info(
                f"[get_credentials] Single-user mode: No credentials found in {credentials_base_dir}"
            )
            return None

        # In single-user mode, if user_google_email wasn't provided, try to get it from user info
        # This is needed for proper credential saving after refresh
        if not user_google_email and credentials.valid:
            try:
                user_info = get_user_info(credentials)
                if user_info and "email" in user_info:
                    user_google_email = user_info["email"]
                    logger.debug(
                        f"[get_credentials] Single-user mode: extracted user email {user_google_email} from credentials"
                    )
            except Exception as e:
                logger.debug(
                    f"[get_credentials] Single-user mode: could not extract user email: {e}"
                )
    else:
        credentials: Optional[Credentials] = None

        # Session ID should be provided by the caller
        if not session_id:
            logger.debug("[get_credentials] No session_id provided")

        logger.debug(
            f"[get_credentials] Called for user_google_email: '{user_google_email}', session_id: '{session_id}', required_scopes: {required_scopes}"
        )

        # Attempt file-based creds
        if user_google_email:
            logger.debug(
                f"[get_credentials] No session credentials, trying file for user_google_email '{user_google_email}'."
            )
            credentials = load_credentials_from_file(
                user_google_email, credentials_base_dir
            )
            if credentials and session_id:
                logger.debug(
                    f"[get_credentials] Loaded from file for user '{user_google_email}', caching to session '{session_id}'."
                )
                # session cache removed – nothing to update

        if not credentials:
            logger.info(
                f"[get_credentials] No credentials found for user '{user_google_email}' or session '{session_id}'."
            )
            return None

    logger.debug(
        f"[get_credentials] Credentials found. Scopes: {credentials.scopes}, Valid: {credentials.valid}, Expired: {credentials.expired}"
    )

    if not all(scope in credentials.scopes for scope in required_scopes):
        logger.warning(
            f"[get_credentials] Credentials lack required scopes. Need: {required_scopes}, Have: {credentials.scopes}. User: '{user_google_email}', Session: '{session_id}'"
        )
        return None  # Re-authentication needed for scopes

    logger.debug(
        f"[get_credentials] Credentials have sufficient scopes. User: '{user_google_email}', Session: '{session_id}'"
    )

    if credentials.valid:
        logger.debug(
            f"[get_credentials] Credentials are valid. User: '{user_google_email}', Session: '{session_id}'"
        )
        return credentials
    elif credentials.expired and credentials.refresh_token:
        logger.info(
            f"[get_credentials] Credentials expired. Attempting refresh. User: '{user_google_email}', Session: '{session_id}'"
        )
        if not client_secrets_path:
            logger.error(
                "[get_credentials] Client secrets path required for refresh but not provided."
            )
            return None
        try:
            logger.debug(
                f"[get_credentials] Refreshing token using client_secrets_path: {client_secrets_path}"
            )
            # client_config = load_client_secrets(client_secrets_path) # Not strictly needed if creds have client_id/secret
            credentials.refresh(Request())
            logger.info(
                f"[get_credentials] Credentials refreshed successfully. User: '{user_google_email}', Session: '{session_id}'"
            )

            # Save refreshed credentials
            if user_google_email:  # Always save to file if email is known
                save_credentials_to_file(
                    user_google_email, credentials, credentials_base_dir
                )
            if session_id:  # Update session cache if it was the source or is active
                # session cache removed – nothing to update
                pass
            return credentials
        except RefreshError as e:
            logger.warning(
                f"[get_credentials] RefreshError - token expired/revoked: {e}. User: '{user_google_email}', Session: '{session_id}'"
            )
            # For RefreshError, we should return None to trigger reauthentication
            return None
        except Exception as e:
            logger.error(
                f"[get_credentials] Error refreshing credentials: {e}. User: '{user_google_email}', Session: '{session_id}'",
                exc_info=True,
            )
            return None  # Failed to refresh
    else:
        logger.warning(
            f"[get_credentials] Credentials invalid/cannot refresh. Valid: {credentials.valid}, Refresh Token: {credentials.refresh_token is not None}. User: '{user_google_email}', Session: '{session_id}'"
        )
        return None


def get_user_info(credentials: Credentials) -> Optional[Dict[str, Any]]:
    """Fetches basic user profile information (requires userinfo.email scope)."""
    if not credentials or not credentials.valid:
        logger.error("Cannot get user info: Invalid or missing credentials.")
        return None
    try:
        # Using googleapiclient discovery to get user info
        # Requires 'google-api-python-client' library
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()
        logger.info(f"Successfully fetched user info: {user_info.get('email')}")
        return user_info
    except HttpError as e:
        logger.error(f"HttpError fetching user info: {e.status_code} {e.reason}")
        # Handle specific errors, e.g., 401 Unauthorized might mean token issue
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching user info: {e}")
        return None


# --- NEW: Environment-based Credentials Loader ---


def _load_credentials_from_env(required_scopes: List[str]) -> Optional[Credentials]:
    """Create a ``google.oauth2.credentials.Credentials`` instance from environment variables.

    This enables fully non-interactive authentication – useful when the MCP is run
    in a headless or server environment where the OAuth flow cannot be completed
    by a human user.

    Expected environment variables (all **must** be provided):
        GOOGLE_OAUTH_ACCESS_TOKEN   – Current access token
        GOOGLE_OAUTH_REFRESH_TOKEN – Long-lived refresh token
        GOOGLE_OAUTH_CLIENT_ID     – OAuth 2.0 client ID
        GOOGLE_OAUTH_CLIENT_SECRET – OAuth 2.0 client secret

    Optional environment variables:
        GOOGLE_OAUTH_TOKEN_URI     – Token endpoint (defaults to Google standard)
        GOOGLE_OAUTH_SCOPES        – Comma-separated list of scopes attached to the
                                      provided tokens. If omitted, ``required_scopes``
                                      will be used so that downstream checks pass.
        GOOGLE_OAUTH_EXPIRY        – RFC3339/ISO formatted expiry timestamp of the
                                      *access* token. If omitted we assume the token
                                      is currently valid and rely on the refresh
                                      token for renewal when required.

    Returns:
        Credentials instance **or** ``None`` if the minimum set of variables is
        not present.
    """
    access_token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN") or os.getenv("GOOGLE_ACCESS_TOKEN")
    refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN") or os.getenv("GOOGLE_REFRESH_TOKEN")
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

    # Abort early if mandatory details are missing
    if not all([access_token, refresh_token, client_id, client_secret]):
        return None

    token_uri = os.getenv("GOOGLE_OAUTH_TOKEN_URI", "https://oauth2.googleapis.com/token")

    # Determine scopes attached to the credentials
    scopes_env = os.getenv("GOOGLE_OAUTH_SCOPES")
    if scopes_env:
        scopes_list = [s.strip() for s in scopes_env.split(",") if s.strip()]
    else:
        scopes_list = required_scopes  # best effort – pass through what the caller needs

    # Parse optional expiry – if not provided, we purposely mark the access token
    # as *already expired* so that google-auth's built-in refresh mechanism kicks
    # in automatically on the very first request. This prevents a stale access
    # token from triggering an unnecessary interactive OAuth flow.
    expiry_str = os.getenv("GOOGLE_OAUTH_EXPIRY")
    expiry_dt: Optional[datetime] = None
    if expiry_str:
        try:
            expiry_dt = datetime.fromisoformat(expiry_str)
        except ValueError:
            logger.warning("GOOGLE_OAUTH_EXPIRY is not a valid ISO/RFC3339 timestamp – ignoring.")
    # If no expiry provided, leave it as None. google-auth will automatically
    # refresh the token on-demand when it receives a 401/invalid_grant response.
    # Setting an artificial past expiry caused some hosting environments to
    # attempt an immediate refresh that can fail due to network or quota and
    # unnecessarily trigger the interactive OAuth flow.
    else:
        expiry_dt = None

    logger.info("Loaded Google credentials from environment variables – using non-interactive auth path.")

    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes_list,
        expiry=expiry_dt,
    )


# --- Internal Token Refresh Helper ---

async def refresh_auth() -> None:
    """Refresh the OAuth access token using the refresh token provided via environment variables.

    This helper is intended for *internal* use only. It is **not** exposed as an MCP
    tool.  The function:
      1. Re-creates a ``Credentials`` instance from the current environment
         (using ``_load_credentials_from_env``).
      2. Calls ``credentials.refresh(Request())`` in a thread-pool so that the
         blocking HTTP request does not block the event-loop.
      3. Updates the ``GOOGLE_OAUTH_ACCESS_TOKEN`` and ``GOOGLE_OAUTH_EXPIRY``
         environment variables in-place so that future credential loads (within
         the same process) benefit from the newly-fetched access token.

    Raises:
        RuntimeError: If no refreshable credentials can be constructed from the
                       environment.
        Exception:     If the refresh operation itself fails for any reason.
    """

    from auth.scopes import SCOPES  # Imported here to avoid circular imports

    # Step 1: Load credentials from the environment.
    credentials = _load_credentials_from_env(list(SCOPES))
    if not credentials or not credentials.refresh_token:
        raise RuntimeError(
            "No refreshable Google OAuth credentials found in environment variables."
        )

    # Step 2: Perform the refresh in a background thread.
    try:
        await asyncio.to_thread(credentials.refresh, Request())
    except Exception as refresh_err:
        logger.error("Failed to refresh OAuth credentials: %s", refresh_err, exc_info=True)
        raise

    # Step 3: Persist the fresh access token (and expiry) back into the env so
    # that subsequent calls that rely on `_load_credentials_from_env` pick up the
    # new values automatically.
    if credentials.token:
        os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"] = credentials.token
    if credentials.expiry:
        os.environ["GOOGLE_OAUTH_EXPIRY"] = credentials.expiry.isoformat()

    logger.info("Successfully refreshed access token via refresh_auth().")


# --- Header-based Authentication ---

def _get_access_token_from_headers() -> Optional[str]:
    """
    Extract the access token from request headers or get it from Firebase using Blueprint Agent ID.
    
    This function tries multiple approaches:
    1. Check context variables (set by middleware)
    2. Look for Blueprint Agent ID in environment/context and fetch token from Firebase
    3. Look for direct access token headers (legacy)
    
    Returns:
        The access token string if found, None otherwise.
    """
    # Check if token is available in context vars (set by middleware)
    from core.context import get_injected_oauth_credentials
    injected_creds = get_injected_oauth_credentials()
    if injected_creds and isinstance(injected_creds, dict):
        access_token = injected_creds.get('access_token')
        if access_token:
            logger.debug("Found access token in injected credentials context")
            return access_token
    
    # Try to get Blueprint Agent ID from environment or context
    # This is a fallback for when middleware doesn't run (MCP protocol)
    agent_id = None
    
    # Check environment variables (can be set by MCP client)
    agent_id = os.getenv('X_BLUEPRINT_AGENT_ID') or os.getenv('BLUEPRINT_AGENT_ID')
    
    if agent_id:
        logger.info(f"Found Blueprint Agent ID in environment: {agent_id}")
        try:
            # Import here to avoid circular imports
            import asyncio
            from auth.firebase_service import get_google_access_token_for_agent
            
            # Get access token from Firebase
            access_token = asyncio.run(get_google_access_token_for_agent(agent_id))
            if access_token:
                logger.info(f"Successfully retrieved access token from Firebase for agent: {agent_id}")
                return access_token
            else:
                logger.warning(f"No access token found in Firebase for agent: {agent_id}")
        except Exception as e:
            logger.error(f"Error getting access token from Firebase for agent {agent_id}: {e}")
    
    logger.debug("No access token found in context variables or Firebase")
    return None


def _create_credentials_from_access_token(access_token: str) -> Credentials:
    """
    Create a minimal Credentials object from just an access token.
    
    Since we're not handling token refresh, we only need the access token.
    The credentials will be marked as valid but without refresh capability.
    
    Args:
        access_token: The Google OAuth access token
        
    Returns:
        A Credentials object with the access token
    """
    return Credentials(
        token=access_token,
        refresh_token=None,  # No refresh capability
        token_uri=None,      # Not needed for non-refreshable tokens
        client_id=None,      # Not needed for non-refreshable tokens
        client_secret=None,  # Not needed for non-refreshable tokens
        scopes=None,         # Will be validated by the API calls themselves
        expiry=None          # We assume the token is valid
    )


# --- Centralized Google Service Authentication ---


class GoogleAuthenticationError(Exception):
    """Exception raised when Google authentication is required or fails."""

    def __init__(self, message: str, auth_url: Optional[str] = None):
        super().__init__(message)
        self.auth_url = auth_url


async def get_authenticated_google_service(
    service_name: str,  # "gmail", "calendar", "drive", "docs"
    version: str,  # "v1", "v3"
    tool_name: str,  # For logging/debugging
    user_google_email: str,  # Required - no more Optional
    required_scopes: List[str],  # Note: scopes are no longer validated since token comes pre-authorized
) -> tuple[Any, str]:
    """
    Centralized Google service authentication for all MCP tools.
    Gets credentials from Blueprint agent via Firebase and returns (service, user_email) on success.

    The authentication flow:
    1. Middleware extracts X-Blueprint-Agent-Id from request headers
    2. Middleware queries Firebase to get the agent's Google access token
    3. Middleware sets the access token in request context
    4. This function retrieves the token from context and creates Google service

    Args:
        service_name: The Google service name ("gmail", "calendar", "drive", "docs")
        version: The API version ("v1", "v3", etc.)
        tool_name: The name of the calling tool (for logging/debugging)
        user_google_email: The user's Google email address (required)
        required_scopes: List of required OAuth scopes (informational only - not validated)

    Returns:
        tuple[service, user_email] on success

    Raises:
        GoogleAuthenticationError: When authentication is required or fails
    """
    logger.info(
        f"[{tool_name}] Attempting to get authenticated {service_name} service. Email: '{user_google_email}'"
    )

    # Validate email format
    if not user_google_email or "@" not in user_google_email:
        error_msg = f"Authentication required for {tool_name}. No valid 'user_google_email' provided. Please provide a valid Google email address."
        logger.info(f"[{tool_name}] {error_msg}")
        raise GoogleAuthenticationError(error_msg)

    # Check if user_google_email contains agent ID pattern (agent_id:email@domain.com)
    agent_id = None
    actual_email = user_google_email
    
    if ':' in user_google_email and '@' in user_google_email:
        parts = user_google_email.split(':', 1)
        if len(parts) == 2:
            potential_agent_id = parts[0].strip()
            potential_email = parts[1].strip()
            # Basic UUID validation (36 chars with hyphens)
            if len(potential_agent_id) == 36 and potential_agent_id.count('-') == 4 and '@' in potential_email:
                agent_id = potential_agent_id
                actual_email = potential_email
                logger.info(f"[{tool_name}] Extracted agent ID: {agent_id}, email: {actual_email}")

    # Get access token from headers/context first
    access_token = _get_access_token_from_headers()
    
    # If no token in headers/context, try to get it from Firebase using agent ID
    if not access_token and agent_id:
        try:
            from auth.firebase_service import get_google_access_token_for_agent
            access_token = await get_google_access_token_for_agent(agent_id)
            
            if access_token:
                logger.info(f"[{tool_name}] Retrieved access token from Firebase for agent: {agent_id}")
            else:
                logger.warning(f"[{tool_name}] No access token found in Firebase for agent: {agent_id}")
                
        except Exception as e:
            logger.error(f"[{tool_name}] Error getting access token from Firebase for agent {agent_id}: {e}")
    
    if not access_token:
        if agent_id:
            error_msg = (
                f"[{tool_name}] No Google access token found for agent '{agent_id}' (email: '{actual_email}'). "
                f"Please ensure the agent exists in Firebase and has valid Google credentials."
            )
        else:
            error_msg = (
                f"[{tool_name}] No Google access token found for user '{user_google_email}'. "
                f"Please provide user_google_email in format: 'agent_id:email@domain.com' "
                f"where agent_id is your Blueprint agent ID."
            )
        logger.warning(error_msg)
        raise GoogleAuthenticationError(error_msg)

    # Create credentials from the access token
    try:
        credentials = _create_credentials_from_access_token(access_token)
        logger.info(f"[{tool_name}] Created credentials from access token for user: {actual_email}")
    except Exception as e:
        error_msg = f"[{tool_name}] Failed to create credentials from access token: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise GoogleAuthenticationError(error_msg)

    # Build the Google service
    try:
        service = build(service_name, version, credentials=credentials)
        logger.info(
            f"[{tool_name}] Successfully authenticated {service_name} service for user: {actual_email}"
        )
        return service, actual_email

    except Exception as e:
        error_msg = f"[{tool_name}] Failed to build {service_name} service: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise GoogleAuthenticationError(error_msg)
