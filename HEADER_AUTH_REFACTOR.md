# Blueprint Agent Firebase Authentication Refactor

## Overview

The authentication system has been completely refactored to use Blueprint Agent IDs with Firebase integration instead of direct access tokens, environment variables, stored credentials, or OAuth flows.

## Key Changes

### 1. New Authentication Flow

**Before:**
- Checked environment variables for full OAuth credentials
- Fell back to stored credential files
- Attempted token refresh using client_id/client_secret
- Initiated interactive OAuth flow if no valid credentials

**After:**
- Extracts Blueprint Agent ID from HTTP request headers
- Queries Firebase Firestore to get agent's authenticators subcollection
- Retrieves Google access token from the appropriate authenticator
- Creates minimal credentials object with the access token
- No refresh capability (tokens are expected to be managed externally)
- No interactive OAuth flows

### 2. Header Support

The system now looks for Blueprint Agent credentials in the following headers:

1. `X-Blueprint-Agent-Id: <agent_id>` (required)
2. `X-Blueprint-API-Key: <api_key>` (not validated currently)

### 3. New Files Added

#### `auth/firebase_service.py`
- Firebase Admin SDK integration for Firestore access
- Functions to retrieve agents and their authenticators subcollection
- Google access token extraction from authenticator documents
- Support for both current (`google-calendar-*`) and future (`google`) authenticator naming

#### `auth/header_middleware.py`
- Middleware to extract Blueprint Agent credentials from HTTP headers
- Queries Firebase to get Google access tokens
- Sets tokens in request context using `contextvars`
- Automatically integrated with FastMCP server

#### Updated `core/context.py`
- Added `set_access_token_from_headers()` function
- Enhanced context management for Firebase-sourced tokens

### 4. Modified Functions

#### `get_authenticated_google_service()` in `auth/google_auth.py`
- Completely rewritten to use Firebase-based authentication
- Simplified error handling with Blueprint-specific messages
- Removed all OAuth flow, refresh, and file-based credential logic

#### New Helper Functions in `auth/firebase_service.py`
- `get_agent_by_id()`: Retrieves agent document from Firestore
- `get_agent_authenticators()`: Gets authenticators subcollection
- `extract_google_access_token_from_authenticators()`: Extracts Google token
- `get_google_access_token_for_agent()`: Main function combining all steps

#### Existing Helper Functions in `auth/google_auth.py`
- `_get_access_token_from_headers()`: Extracts token from context (unchanged)
- `_create_credentials_from_access_token()`: Creates minimal credentials object (unchanged)

## Usage

### Client Side
Send requests with the Blueprint Agent credentials in headers:

```bash
# Blueprint Agent authentication
curl -H "X-Blueprint-Agent-Id: bea33dad-9b5b-4fe1-8d45-634085aa5771" \
     -H "X-Blueprint-API-Key: your-api-key-here" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     http://localhost:8000/mcp/

# Example with MCP tools/list call
curl -X POST \
     -H "X-Blueprint-Agent-Id: bea33dad-9b5b-4fe1-8d45-634085aa5771" \
     -H "X-Blueprint-API-Key: your-api-key-here" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' \
     http://localhost:8000/mcp/
```

### Server Side
The middleware automatically:
1. Extracts the Blueprint Agent ID from request headers
2. Queries Firebase Firestore for the agent's authenticators subcollection
3. Retrieves the Google access token from the appropriate authenticator
4. Sets the token in the request context
5. Makes it available to all Google service authentication calls

## Benefits

1. **Centralized Authentication**: All authentication data is managed in Firebase Firestore
2. **Agent-Based**: Each Blueprint Agent has its own set of authenticators
3. **Stateless**: Each request is self-contained with agent-specific authentication
4. **Secure**: No tokens stored on the MCP server, retrieved fresh from Firebase per request
5. **Scalable**: Supports multiple agents with different Google accounts
6. **Future-Proof**: Designed to transition from `google-calendar-*` to `google` authenticator naming

## Migration Notes

- **Breaking Change**: The server no longer handles token refresh or OAuth flows
- **Firebase Dependency**: Requires Firebase Admin SDK and Firestore access to `polletask-dev` project
- **Agent Requirement**: All requests must include a valid Blueprint Agent ID
- **No Backward Compatibility**: Environment variable and file-based authentication are no longer used
- **Middleware Required**: The Blueprint auth middleware must be active for authentication to work
- **Authenticator Naming**: Currently supports `google-calendar-*` naming, will transition to `google` in the future

## Error Handling

The system handles various error scenarios:

### Agent Not Found
- Logs warning when Blueprint Agent ID doesn't exist in Firestore
- Returns appropriate error message to client

### No Authenticators
- Logs warning when agent has no authenticators subcollection
- Attempts fallback to main agent document (legacy support)

### No Google Authenticator
- Logs available authenticator types for debugging
- Provides clear error message about missing Google authentication

### Firebase Connection Issues
- Handles Firebase initialization failures gracefully
- Provides detailed error messages for debugging

### Invalid Access Tokens
- Validates token format and content
- Logs token extraction attempts for debugging

## Testing

The refactor has been tested with a comprehensive test suite that verifies:
- Firebase connection to `polletask-dev` project ✅
- Context token storage and retrieval ✅
- Agent document retrieval from Firestore ✅
- Authenticators subcollection access ✅
- Google access token extraction from authenticators ✅
- Complete authentication flow end-to-end ✅

All tests pass successfully, confirming the Firebase Blueprint authentication system works as expected.

## Firebase Structure

The system expects the following Firestore structure:

```
/agents/{agentId}
  - Main agent document with metadata
  
/agents/{agentId}/authenticators/{authenticatorId}
  - Authenticator documents containing access tokens
  - Current naming: google-calendar-{userId}
  - Future naming: google
  - Token field: accessToken (or access_token)
```

## Dependencies Added

- `firebase-admin>=7.1.0`: Firebase Admin SDK for server-side access
- `google-cloud-firestore>=2.21.0`: Firestore client library

The refactor is complete and working correctly. The MCP server now uses Blueprint Agent IDs to fetch Google OAuth access tokens from Firebase Firestore, providing a centralized and scalable authentication solution.
