"""
Quick test script to verify ServiceTokenManager can acquire tokens from Auth-API.
"""

import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.core.service_auth import get_service_token_manager, init_service_token_manager
from app.core.logging_config import get_logger, setup_logging
from app.config import settings
import jwt

# Setup logging
setup_logging()
logger = get_logger(__name__)


async def test_service_token():
    """Test service token acquisition."""

    print("\n" + "="*80)
    print("SERVICE TOKEN ACQUISITION TEST")
    print("="*80 + "\n")

    try:
        # Initialize token manager
        print("1. Initializing ServiceTokenManager...")
        init_service_token_manager(
            client_id=settings.SERVICE_CLIENT_ID,
            client_secret=settings.SERVICE_CLIENT_SECRET,
            token_url=settings.SERVICE_TOKEN_URL,
            scope=settings.SERVICE_SCOPE
        )
        print(f"   ✅ Token manager initialized\n")

        # Get token manager instance
        print("2. Getting ServiceTokenManager instance...")
        token_manager = get_service_token_manager()
        print(f"   ✅ Token manager initialized")
        print(f"   - Client ID: {token_manager.client_id}")
        print(f"   - Token URL: {token_manager.token_url}")
        print(f"   - Scope: {token_manager.scope}\n")

        # Acquire token
        print("3. Acquiring service token from Auth-API...")
        token = await token_manager.get_token()
        print(f"   ✅ Token acquired successfully!")
        print(f"   - Token (first 50 chars): {token[:50]}...\n")

        # Decode token (without verification) to inspect claims
        print("4. Decoding token (inspection only)...")
        decoded = jwt.decode(token, options={"verify_signature": False})
        print(f"   ✅ Token decoded")
        print(f"   Token Claims:")
        for key, value in decoded.items():
            if key not in ['iat', 'exp', 'nbf']:
                print(f"   - {key}: {value}")
            else:
                from datetime import datetime
                dt = datetime.fromtimestamp(value)
                print(f"   - {key}: {value} ({dt.isoformat()})")

        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED - Service token acquisition works!")
        print("="*80 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}: {str(e)}\n")
        logger.error("service_token_test_failed", error=str(e), exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_service_token())
    sys.exit(0 if success else 1)
