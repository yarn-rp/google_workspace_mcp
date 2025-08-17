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


def extract_google_access_token_from_authenticators(authenticators: Dict[str, Any]) -> Optional[str]:
    """
    Extract the Google access token from the authenticators subcollection.
    
    Args:
        authenticators: Dictionary of authenticator documents from the subcollection
        
    Returns:
        The Google access token if found, None otherwise
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
            token_fields = [
                'access_token', 'accessToken', 'token', 
                'google_access_token', 'googleAccessToken',
                'oauth_token', 'oauthToken'
            ]
            
            for field in token_fields:
                if field in google_auth and google_auth[field]:
                    token = google_auth[field]
                    if isinstance(token, str) and token.strip():
                        logger.info(f"Found Google access token in authenticators.{found_auth_key}.{field}")
                        return token.strip()
            
            # If no direct token field, check nested structures
            nested_paths = [
                ['credentials', 'access_token'],
                ['credentials', 'accessToken'],
                ['oauth', 'access_token'],
                ['oauth', 'accessToken'],
                ['tokens', 'access_token'],
                ['tokens', 'accessToken'],
            ]
            
            for path in nested_paths:
                current = google_auth
                try:
                    for key in path:
                        current = current[key]
                    
                    if current and isinstance(current, str) and current.strip():
                        logger.info(f"Found Google access token in authenticators.{found_auth_key}.{'.'.join(path)}")
                        return current.strip()
                        
                except (KeyError, TypeError):
                    continue
            
            # Log the structure for debugging
            logger.debug(f"Google authenticator '{found_auth_key}' structure: {list(google_auth.keys())}")
        
        # If no specific Google authenticator found, log all available authenticators
        logger.warning(f"No Google authenticator found. Available authenticators: {list(authenticators.keys())}")
        
        # Log structure of each authenticator for debugging
        for auth_key, auth_data in authenticators.items():
            if isinstance(auth_data, dict):
                logger.debug(f"Authenticator '{auth_key}' structure: {list(auth_data.keys())}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting Google access token from authenticators: {e}")
        return None


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
            access_token = extract_google_access_token_from_agent_data(agent_data)
            
            if access_token:
                logger.info(f"Successfully retrieved Google access token from agent data for agent: {agent_id}")
                return access_token, email
            else:
                logger.warning(f"No Google access token found for agent: {agent_id}")
                return None, email  # Return email even if no access token
                
    except Exception as e:
        logger.error(f"Error getting Google credentials for agent {agent_id}: {e}")
        return None, None


# Initialize Firebase when the module is imported
try:
    initialize_firebase()
except Exception as e:
    logger.warning(f"Firebase initialization failed during module import: {e}")
    logger.info("Firebase will be initialized on first use")
