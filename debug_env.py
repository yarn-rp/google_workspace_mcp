#!/usr/bin/env python3
"""
Debug script to check environment variables for OAuth credentials.
Run this to verify what OAuth environment variables are available.
"""

import os
import sys

def main():
    print("🔍 OAuth Environment Variables Debug")
    print("=" * 40)
    
    oauth_env_vars = [
        'GOOGLE_OAUTH_CLIENT_ID',
        'GOOGLE_OAUTH_CLIENT_SECRET', 
        'GOOGLE_OAUTH_ACCESS_TOKEN',
        'GOOGLE_OAUTH_REFRESH_TOKEN',
        'GOOGLE_OAUTH_TOKEN_URI',
        'GOOGLE_OAUTH_REDIRECT_URI',
        'X_BLUEPRINT_AGENT_ID',
        'BLUEPRINT_AGENT_ID',
        'X-Blueprint-Agent-Id'
    ]
    
    found_vars = 0
    for var in oauth_env_vars:
        value = os.getenv(var)
        if value:
            # Show first 10 chars for debugging but hide full value
            display_value = f"SET ({value[:10]}...)" if len(value) > 10 else f"SET ({value})"
            print(f"✅ {var}: {display_value}")
            found_vars += 1
        else:
            print(f"❌ {var}: NOT SET")
    
    print(f"\n📊 Summary: {found_vars}/{len(oauth_env_vars)} variables set")
    
    if found_vars == 0:
        print("\n⚠️  No OAuth environment variables found!")
        print("   Make sure to set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET")
        print("   These are required for token refresh to work properly.")
        return 1
    
    # Check for minimum required variables
    required_vars = ['GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET']
    missing_required = [var for var in required_vars if not os.getenv(var)]
    
    if missing_required:
        print(f"\n❌ Missing required variables: {', '.join(missing_required)}")
        print("   These are essential for OAuth token refresh functionality.")
        return 1
    else:
        print(f"\n✅ All required OAuth variables are set!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
