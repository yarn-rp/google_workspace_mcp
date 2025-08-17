# auth/firebase_service.py

import logging
import os
from typing import Optional, Dict, Any
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

# Global Firebase app instance
_firebase_app: Optional[firebase_admin.App] = None
_firestore_client: Optional[firestore.Client] = None

def initialize_firebase() -> None:
    """
    Initialize Firebase Admin SDK with Application Default Credentials.
    
    This function uses the Google Cloud CLI authentication or service account
    credentials to connect to the polletask-dev project.
    """
    global _firebase_app, _firestore_client
    
    if _firebase_app is not None:
        logger.debug("Firebase already initialized")
        return
    
    try:
        # Use Application Default Credentials (gcloud auth application-default login)
        # or service account key if GOOGLE_APPLICATION_CREDENTIALS is set
        cred = credentials.ApplicationDefault()
        
        # Initialize Firebase with the polletask-dev project
        _firebase_app = firebase_admin.initialize_app(cred, {
            'projectId': 'polletask-dev'
        })
        
        # Initialize Firestore client
        _firestore_client = firestore.client()
        
        logger.info("Firebase initialized successfully for project: polletask-dev")
        
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise


def get_firestore_client() -> firestore.Client:
    """
    Get the Firestore client instance.
    
    Returns:
        The Firestore client instance
        
    Raises:
        RuntimeError: If Firebase is not initialized
    """
    if _firestore_client is None:
        initialize_firebase()
    
    if _firestore_client is None:
        raise RuntimeError("Firestore client not available. Firebase initialization failed.")
    
    return _firestore_client


async def get_agent_by_id(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a Blueprint agent document from Firestore by its ID.
    
    Args:
        agent_id: The Blueprint agent ID to search for
        
    Returns:
        The agent document data if found, None otherwise
        
    Raises:
        Exception: If there's an error accessing Firestore
    """
    try:
        db = get_firestore_client()
        
        # Assuming agents are stored in a collection called 'agents'
        # You may need to adjust the collection name based on your Firestore structure
        agents_ref = db.collection('agents')
        
        # Query for the agent by ID
        # This assumes the agent_id is stored in a field called 'id' or as the document ID
        # Try document ID first
        doc_ref = agents_ref.document(agent_id)
        doc = doc_ref.get()
        
        if doc.exists:
            agent_data = doc.to_dict()
            logger.info(f"Found agent by document ID: {agent_id}")
            return agent_data
        
        # If not found by document ID, try querying by 'id' field
        query = agents_ref.where(filter=FieldFilter('id', '==', agent_id))
        docs = query.limit(1).stream()
        
        for doc in docs:
            agent_data = doc.to_dict()
            logger.info(f"Found agent by id field: {agent_id}")
            return agent_data
        
        logger.warning(f"Agent not found: {agent_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving agent {agent_id} from Firestore: {e}")
        raise


async def get_agent_authenticators(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the authenticators subcollection for a Blueprint agent.
    
    Args:
        agent_id: The Blueprint agent ID to search for
        
    Returns:
        Dictionary of authenticators if found, None otherwise
        
    Raises:
        Exception: If there's an error accessing Firestore
    """
    try:
        db = get_firestore_client()
        
        # Get the authenticators subcollection
        authenticators_ref = db.collection('agents').document(agent_id).collection('authenticators')
        
        # Get all authenticator documents
        docs = authenticators_ref.stream()
        
        authenticators = {}
        for doc in docs:
            authenticators[doc.id] = doc.to_dict()
        
        if authenticators:
            logger.info(f"Found {len(authenticators)} authenticators for agent: {agent_id}")
            logger.debug(f"Authenticator types: {list(authenticators.keys())}")
            return authenticators
        else:
            logger.warning(f"No authenticators found for agent: {agent_id}")
            return None
        
    except Exception as e:
        logger.error(f"Error retrieving authenticators for agent {agent_id}: {e}")
        raise


def extract_google_credentials_from_authenticators(authenticators: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract the Google access token and refresh token from the authenticators subcollection.
    
    Args:
        authenticators: Dictionary of authenticator documents from the subcollection
        
    Returns:
        Tuple of (access_token, refresh_token) if found, (None, None) otherwise
    """
    try:
        # Look for Google authenticator in the subcollection
        # TEMPORARY: Support both 'google' (future) and 'google-calendar' (current)
        # TODO: In the future, only 'google' will be used
        
        google_auth = None
        found_auth_key = None
        
        # Priority order: 'google' (future standard) first, then 'google-calendar' (current)
        priority_auth_keys = [
            'google',           # Future standard - preferred
            'google-calendar',  # Current implementation - temporary support
        ]
        
        # Try priority keys first
        for auth_key in priority_auth_keys:
            if auth_key in authenticators:
                google_auth = authenticators[auth_key]
                found_auth_key = auth_key
                logger.debug(f"Found Google authenticator with priority key: {auth_key}")
                break
        
        # Fallback: look for any key that contains 'google-calendar' or starts with 'google-calendar-'
        if not google_auth:
            for auth_key in authenticators.keys():
                if auth_key.startswith('google-calendar'):
                    google_auth = authenticators[auth_key]
                    found_auth_key = auth_key
                    logger.debug(f"Found Google authenticator with calendar-specific key: {auth_key}")
                    break
        
        # Last fallback: any key containing 'google'
        if not google_auth:
            for auth_key in authenticators.keys():
                if 'google' in auth_key.lower():
                    google_auth = authenticators[auth_key]
                    found_auth_key = auth_key
                    logger.debug(f"Found Google authenticator with generic google key: {auth_key}")
                    break
        
        if google_auth and found_auth_key:
            # Look for access token in various possible fields
            access_token = None
            refresh_token = None
            
            access_token_fields = [
                'access_token', 'accessToken', 'token', 
                'google_access_token', 'googleAccessToken',
                'oauth_token', 'oauthToken'
            ]
            
            refresh_token_fields = [
                'refresh_token', 'refreshToken',
                'google_refresh_token', 'googleRefreshToken',
                'oauth_refresh_token', 'oauthRefreshToken'
            ]
            
            # Extract access token
            for field in access_token_fields:
                if field in google_auth and google_auth[field]:
                    token = google_auth[field]
                    if isinstance(token, str) and token.strip():
                        access_token = token.strip()
                        logger.info(f"Found Google access token in authenticators.{found_auth_key}.{field}")
                        break
            
            # Extract refresh token
            for field in refresh_token_fields:
                if field in google_auth and google_auth[field]:
                    token = google_auth[field]
                    if isinstance(token, str) and token.strip():
                        refresh_token = token.strip()
                        logger.info(f"Found Google refresh token in authenticators.{found_auth_key}.{field}")
                        break
            
            # If no direct token fields found, check nested structures
            if not access_token or not refresh_token:
                nested_access_paths = [
                    ['credentials', 'access_token'],
                    ['credentials', 'accessToken'],
                    ['oauth', 'access_token'],
                    ['oauth', 'accessToken'],
                    ['tokens', 'access_token'],
                    ['tokens', 'accessToken'],
                ]
                
                nested_refresh_paths = [
                    ['credentials', 'refresh_token'],
                    ['credentials', 'refreshToken'],
                    ['oauth', 'refresh_token'],
                    ['oauth', 'refreshToken'],
                    ['tokens', 'refresh_token'],
                    ['tokens', 'refreshToken'],
                ]
                
                # Try to find access token in nested structures
                if not access_token:
                    for path in nested_access_paths:
                        current = google_auth
                        try:
                            for key in path:
                                current = current[key]
                            
                            if current and isinstance(current, str) and current.strip():
                                access_token = current.strip()
                                logger.info(f"Found Google access token in authenticators.{found_auth_key}.{'.'.join(path)}")
                                break
                                
                        except (KeyError, TypeError):
                            continue
                
                # Try to find refresh token in nested structures
                if not refresh_token:
                    for path in nested_refresh_paths:
                        current = google_auth
                        try:
                            for key in path:
                                current = current[key]
                            
                            if current and isinstance(current, str) and current.strip():
                                refresh_token = current.strip()
                                logger.info(f"Found Google refresh token in authenticators.{found_auth_key}.{'.'.join(path)}")
                                break
                                
                        except (KeyError, TypeError):
                            continue
            
            # Return what we found
            if access_token or refresh_token:
                return access_token, refresh_token
            
            # Log the structure for debugging
            logger.debug(f"Google authenticator '{found_auth_key}' structure: {list(google_auth.keys())}")
        
        # If no specific Google authenticator found, log all available authenticators
        logger.warning(f"No Google authenticator found. Available authenticators: {list(authenticators.keys())}")
        
        # Log structure of each authenticator for debugging
        for auth_key, auth_data in authenticators.items():
            if isinstance(auth_data, dict):
                logger.debug(f"Authenticator '{auth_key}' structure: {list(auth_data.keys())}")
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error extracting Google credentials from authenticators: {e}")
        return None, None


def extract_oauth_client_credentials_from_authenticators(authenticators: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract OAuth client credentials (client_id, client_secret) from the authenticators subcollection.
    
    This is a fallback for when these credentials are not set as environment variables.
    
    Args:
        authenticators: Dictionary of authenticator documents from the subcollection
        
    Returns:
        Tuple of (client_id, client_secret) if found, (None, None) otherwise
    """
    try:
        # Look for Google authenticator in the subcollection
        google_auth = None
        found_auth_key = None
        
        # Priority order: 'google' (future standard) first, then 'google-calendar' (current)
        priority_auth_keys = [
            'google',           # Future standard - preferred
            'google-calendar',  # Current implementation - temporary support
        ]
        
        # Try priority keys first
        for auth_key in priority_auth_keys:
            if auth_key in authenticators:
                google_auth = authenticators[auth_key]
                found_auth_key = auth_key
                logger.debug(f"Found Google authenticator with priority key: {auth_key}")
                break
        
        # Fallback: look for any key that contains 'google-calendar' or starts with 'google-calendar-'
        if not google_auth:
            for auth_key in authenticators.keys():
                if auth_key.startswith('google-calendar'):
                    google_auth = authenticators[auth_key]
                    found_auth_key = auth_key
                    logger.debug(f"Found Google authenticator with calendar-specific key: {auth_key}")
                    break
        
        # Last fallback: any key containing 'google'
        if not google_auth:
            for auth_key in authenticators.keys():
                if 'google' in auth_key.lower():
                    google_auth = authenticators[auth_key]
                    found_auth_key = auth_key
                    logger.debug(f"Found Google authenticator with generic google key: {auth_key}")
                    break
        
        if google_auth and found_auth_key:
            # Look for client credentials in various possible fields
            client_id = None
            client_secret = None
            
            client_id_fields = [
                'client_id', 'clientId', 
                'google_client_id', 'googleClientId',
                'oauth_client_id', 'oauthClientId'
            ]
            
            client_secret_fields = [
                'client_secret', 'clientSecret',
                'google_client_secret', 'googleClientSecret',
                'oauth_client_secret', 'oauthClientSecret'
            ]
            
            # Extract client_id
            for field in client_id_fields:
                if field in google_auth and google_auth[field]:
                    value = google_auth[field]
                    if isinstance(value, str) and value.strip():
                        client_id = value.strip()
                        logger.info(f"Found OAuth client_id in authenticators.{found_auth_key}.{field}")
                        break
            
            # Extract client_secret
            for field in client_secret_fields:
                if field in google_auth and google_auth[field]:
                    value = google_auth[field]
                    if isinstance(value, str) and value.strip():
                        client_secret = value.strip()
                        logger.info(f"Found OAuth client_secret in authenticators.{found_auth_key}.{field}")
                        break
            
            # If no direct fields found, check nested structures
            if not client_id or not client_secret:
                nested_client_id_paths = [
                    ['credentials', 'client_id'],
                    ['credentials', 'clientId'],
                    ['oauth', 'client_id'],
                    ['oauth', 'clientId'],
                    ['config', 'client_id'],
                    ['config', 'clientId'],
                ]
                
                nested_client_secret_paths = [
                    ['credentials', 'client_secret'],
                    ['credentials', 'clientSecret'],
                    ['oauth', 'client_secret'],
                    ['oauth', 'clientSecret'],
                    ['config', 'client_secret'],
                    ['config', 'clientSecret'],
                ]
                
                # Try to find client_id in nested structures
                if not client_id:
                    for path in nested_client_id_paths:
                        current = google_auth
                        try:
                            for key in path:
                                current = current[key]
                            
                            if current and isinstance(current, str) and current.strip():
                                client_id = current.strip()
                                logger.info(f"Found OAuth client_id in authenticators.{found_auth_key}.{'.'.join(path)}")
                                break
                                
                        except (KeyError, TypeError):
                            continue
                
                # Try to find client_secret in nested structures
                if not client_secret:
                    for path in nested_client_secret_paths:
                        current = google_auth
                        try:
                            for key in path:
                                current = current[key]
                            
                            if current and isinstance(current, str) and current.strip():
                                client_secret = current.strip()
                                logger.info(f"Found OAuth client_secret in authenticators.{found_auth_key}.{'.'.join(path)}")
                                break
                                
                        except (KeyError, TypeError):
                            continue
            
            # Return what we found
            if client_id or client_secret:
                return client_id, client_secret
        
        logger.debug(f"No OAuth client credentials found in authenticators")
        return None, None
        
    except Exception as e:
        logger.error(f"Error extracting OAuth client credentials from authenticators: {e}")
        return None, None


def extract_google_access_token_from_authenticators(authenticators: Dict[str, Any]) -> Optional[str]:
    """
    Backward compatibility function that extracts only the access token.
    
    Args:
        authenticators: Dictionary of authenticator documents from the subcollection
        
    Returns:
        The Google access token if found, None otherwise
    """
    access_token, _ = extract_google_credentials_from_authenticators(authenticators)
    return access_token


def extract_google_access_token(agent_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract the Google access token from the agent's authenticator data.
    
    Args:
        agent_data: The agent document data from Firestore
        
    Returns:
        The Google access token if found, None otherwise
    """
    try:
        # Navigate through the agent data structure to find the Google authenticator
        # This structure may need to be adjusted based on your actual Firestore schema
        
        # Based on the agent structure, let's check the most likely locations:
        # 1. providerConfig might contain authentication data
        # 2. configuration might contain auth settings
        # 3. metadata might have auth info
        # 4. Standard authenticator patterns
        
        possible_paths = [
            # Provider config patterns
            ['providerConfig', 'google', 'access_token'],
            ['providerConfig', 'google', 'accessToken'],
            ['providerConfig', 'auth', 'google', 'access_token'],
            ['providerConfig', 'auth', 'google', 'accessToken'],
            ['providerConfig', 'authenticator', 'google', 'access_token'],
            ['providerConfig', 'authenticator', 'google', 'accessToken'],
            
            # Configuration patterns
            ['configuration', 'google', 'access_token'],
            ['configuration', 'google', 'accessToken'],
            ['configuration', 'auth', 'google', 'access_token'],
            ['configuration', 'auth', 'google', 'accessToken'],
            ['configuration', 'authenticator', 'google', 'access_token'],
            ['configuration', 'authenticator', 'google', 'accessToken'],
            
            # Metadata patterns
            ['metadata', 'google', 'access_token'],
            ['metadata', 'google', 'accessToken'],
            ['metadata', 'auth', 'google', 'access_token'],
            ['metadata', 'auth', 'google', 'accessToken'],
            ['metadata', 'authenticator', 'google', 'access_token'],
            ['metadata', 'authenticator', 'google', 'accessToken'],
            
            # Standard authenticator patterns
            ['authenticator', 'google', 'access_token'],
            ['authenticators', 'google', 'access_token'],
            ['auth', 'google', 'access_token'],
            ['credentials', 'google', 'access_token'],
            ['authenticator', 'google', 'accessToken'],
            ['authenticators', 'google', 'accessToken'],
            ['auth', 'google', 'accessToken'],
            ['credentials', 'google', 'accessToken'],
            
            # Direct access patterns
            ['google_access_token'],
            ['googleAccessToken'],
            ['access_token'],
            ['accessToken'],
        ]
        
        for path in possible_paths:
            current = agent_data
            try:
                for key in path:
                    current = current[key]
                
                if current and isinstance(current, str):
                    logger.info(f"Found Google access token at path: {' -> '.join(path)}")
                    return current
                    
            except (KeyError, TypeError):
                continue
        
        # If no token found in standard paths, log the structure for debugging
        logger.warning(f"No Google access token found in agent data. Available keys: {list(agent_data.keys())}")
        
        # Log detailed structure for debugging
        for key in ['providerConfig', 'configuration', 'metadata', 'authenticator']:
            if key in agent_data:
                data = agent_data[key]
                if isinstance(data, dict):
                    logger.debug(f"{key} structure: {list(data.keys())}")
                    # Log nested structure if it's not too deep
                    for nested_key, nested_value in data.items():
                        if isinstance(nested_value, dict) and len(nested_value) < 20:
                            logger.debug(f"  {key}.{nested_key}: {list(nested_value.keys())}")
                else:
                    logger.debug(f"{key} type: {type(data)}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting Google access token from agent data: {e}")
        return None


async def get_google_access_token_for_agent(agent_id: str) -> Optional[str]:
    """
    Get the Google access token for a Blueprint agent.
    
    This is the main function that combines agent retrieval and token extraction.
    
    Args:
        agent_id: The Blueprint agent ID
        
    Returns:
        The Google access token if found, None otherwise
        
    Raises:
        Exception: If there's an error accessing Firestore
    """
    try:
        # First, verify the agent exists
        agent_data = await get_agent_by_id(agent_id)
        
        if not agent_data:
            logger.warning(f"Agent not found: {agent_id}")
            return None
        
        # Get the authenticators subcollection
        authenticators = await get_agent_authenticators(agent_id)
        
        if not authenticators:
            logger.warning(f"No authenticators found for agent: {agent_id}")
            return None
        
        # Extract the Google access token from authenticators
        access_token = extract_google_access_token_from_authenticators(authenticators)
        
        if access_token:
            logger.info(f"Successfully retrieved Google access token for agent: {agent_id}")
            return access_token
        else:
            logger.warning(f"No Google access token found in authenticators for agent: {agent_id}")
            
            # Fallback: try to extract from main agent document (legacy support)
            logger.debug("Trying fallback extraction from main agent document...")
            fallback_token = extract_google_access_token(agent_data)
            
            if fallback_token:
                logger.info(f"Found Google access token in main agent document (fallback) for agent: {agent_id}")
                return fallback_token
            
            return None
            
    except Exception as e:
        logger.error(f"Failed to get Google access token for agent {agent_id}: {e}")
        raise


async def get_google_credentials_for_agent(agent_id: str) -> tuple[Optional[str], Optional[str]]:
    """
    Get both Google access token and email for a Blueprint agent.
    
    Args:
        agent_id: The Blueprint agent ID
        
    Returns:
        Tuple of (access_token, email) if found, (None, None) otherwise
    """
    try:
        # First, verify the agent exists and get agent data
        agent_data = await get_agent_by_id(agent_id)
        
        if not agent_data:
            logger.warning(f"Agent not found: {agent_id}")
            return None, None
        
        # Extract email from agent data
        email = agent_data.get('email')
        if email:
            logger.info(f"Found agent email: {email}")
        else:
            logger.warning(f"No email found for agent: {agent_id}")
        
        # Get the authenticators subcollection
        authenticators = await get_agent_authenticators(agent_id)
        
        if not authenticators:
            logger.warning(f"No authenticators found for agent: {agent_id}")
            return None, email  # Return email even if no authenticators
        
        # Extract the Google access token from authenticators
        access_token = extract_google_access_token_from_authenticators(authenticators)
        
        if access_token:
            logger.info(f"Successfully retrieved Google access token for agent: {agent_id}")
            return access_token, email
        else:
            logger.warning(f"No Google access token found in authenticators for agent: {agent_id}")
            
            # Fallback: try to extract from main agent document (legacy support)
            access_token = extract_google_access_token(agent_data)
            
            if access_token:
                logger.info(f"Successfully retrieved Google access token from agent data for agent: {agent_id}")
                return access_token, email
            else:
                logger.warning(f"No Google access token found for agent: {agent_id}")
                return None, email  # Return email even if no access token
                
    except Exception as e:
        logger.error(f"Error getting Google credentials for agent {agent_id}: {e}")
        return None, None


async def refresh_google_access_token_for_agent(agent_id: str) -> Optional[str]:
    """
    Refresh the Google access token for a Blueprint agent using the stored refresh token.
    
    This function:
    1. Retrieves the agent's refresh token from Firebase
    2. Uses it to get a new access token from Google
    3. Updates the stored access token in Firebase
    4. Returns the new access token
    
    Args:
        agent_id: The Blueprint agent ID
        
    Returns:
        The new Google access token if refresh succeeds, None otherwise
    """
    try:
        # Get the authenticators subcollection
        authenticators = await get_agent_authenticators(agent_id)
        
        if not authenticators:
            logger.warning(f"No authenticators found for agent: {agent_id}")
            return None
        
        # Extract both access and refresh tokens
        access_token, refresh_token = extract_google_credentials_from_authenticators(authenticators)
        
        if not refresh_token:
            logger.warning(f"No refresh token found for agent: {agent_id}")
            return None
        
        # Import Google auth libraries
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google.auth.exceptions import RefreshError
        
        # Create credentials object with refresh token
        credentials = Credentials(
            token=access_token,  # Current access token (may be expired)
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,  # Will be extracted from refresh token
            client_secret=None  # Will be extracted from refresh token
        )
        
        # Attempt to refresh the token
        try:
            credentials.refresh(Request())
            new_access_token = credentials.token
            
            if new_access_token:
                # Update the access token in Firebase
                await update_google_access_token_for_agent(agent_id, new_access_token)
                logger.info(f"Successfully refreshed access token for agent: {agent_id}")
                return new_access_token
            else:
                logger.error(f"Token refresh succeeded but no new access token received for agent: {agent_id}")
                return None
                
        except RefreshError as e:
            logger.warning(f"Refresh token expired or revoked for agent {agent_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error refreshing token for agent {agent_id}: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to refresh Google access token for agent {agent_id}: {e}")
        return None


async def update_google_access_token_for_agent(agent_id: str, new_access_token: str) -> bool:
    """
    Update the Google access token for a Blueprint agent in Firebase.
    
    Args:
        agent_id: The Blueprint agent ID
        new_access_token: The new access token to store
        
    Returns:
        True if update succeeds, False otherwise
    """
    try:
        db = get_firestore_client()
        
        # Get the authenticators subcollection
        authenticators_ref = db.collection('agents').document(agent_id).collection('authenticators')
        
        # Find the Google authenticator document
        docs = authenticators_ref.stream()
        
        google_doc_ref = None
        for doc in docs:
            doc_id = doc.id
            # Check if this is a Google authenticator
            if any(keyword in doc_id.lower() for keyword in ['google', 'calendar']):
                google_doc_ref = authenticators_ref.document(doc_id)
                break
        
        if not google_doc_ref:
            logger.error(f"No Google authenticator document found for agent: {agent_id}")
            return False
        
        # Update the access token
        # Try multiple field names to ensure compatibility
        update_data = {
            'access_token': new_access_token,
            'accessToken': new_access_token,
            'google_access_token': new_access_token,
            'googleAccessToken': new_access_token
        }
        
        google_doc_ref.update(update_data)
        logger.info(f"Updated access token in Firebase for agent: {agent_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update access token for agent {agent_id}: {e}")
        return False


# Initialize Firebase when the module is imported
try:
    initialize_firebase()
except Exception as e:
    logger.warning(f"Firebase initialization failed during module import: {e}")
    logger.info("Firebase will be initialized on first use")
