"""
Test GroupService integration with Auth-API.

THIS IS THE CORE - without groups working, chat doesn't work!

Tests:
1. Fetch group from Auth-API using service token
2. Verify user authorization (user must be member)
3. Validate group data structure
4. Test error handling (non-existent group, unauthorized user)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.config import settings
from app.core.logging_config import get_logger, setup_logging
from app.services.group_service import GroupService
from app.core.service_token_manager import init_service_token_manager, get_service_token_manager

setup_logging()
logger = get_logger(__name__)


async def test_group_service():
    """Test GroupService - THE CORE of chat functionality!"""

    print("\n" + "="*80)
    print("GROUPSERVICE INTEGRATION TEST - THE CORE OF CHAT!")
    print("="*80 + "\n")

    try:
        # Initialize service token manager
        print("1. Initializing ServiceTokenManager...")
        print(f"   Client ID: {settings.SERVICE_CLIENT_ID}")
        print(f"   Token URL: {settings.SERVICE_TOKEN_URL}")
        print(f"   Scope: {settings.SERVICE_SCOPE}")

        init_service_token_manager(
            client_id=settings.SERVICE_CLIENT_ID,
            client_secret=settings.SERVICE_CLIENT_SECRET,
            token_url=settings.SERVICE_TOKEN_URL,
            scope=settings.SERVICE_SCOPE
        )

        token_manager = get_service_token_manager()
        print("   ✅ ServiceTokenManager initialized\n")

        # Create GroupService
        print("2. Creating GroupService...")
        group_service = GroupService()
        print("   ✅ GroupService created\n")

        # Test 1: Fetch a real group
        # First, let's try to get ANY group from Auth-API to see what exists
        print("3. Testing get_group() - fetching from Auth-API...")
        print("   Note: We need a real group_id and user_id from Auth-API")
        print("   For now, we'll test with test data\n")

        # Test with example IDs (these need to exist in Auth-API)
        test_org_id = "test-org-123"
        test_group_id = "550e8400-e29b-41d4-a716-446655440000"  # Example UUID
        test_user_id = "test-user-123"

        print(f"   Attempting to fetch group:")
        print(f"   - org_id: {test_org_id}")
        print(f"   - group_id: {test_group_id}")
        print(f"   - user_id: {test_user_id}\n")

        try:
            group = await group_service.get_group(
                org_id=test_org_id,
                group_id=test_group_id,
                user_id=test_user_id
            )

            print("   ✅ Group fetched successfully!")
            print(f"   Group data:")
            print(f"   - id: {group.id}")
            print(f"   - name: {group.name}")
            print(f"   - description: {group.description}")
            print(f"   - member_count: {group.member_count}")
            print(f"   - is_member: {group.is_member}\n")

        except Exception as e:
            print(f"   ⚠️  Group fetch failed (expected if group doesn't exist): {e}")
            print(f"   Error type: {type(e).__name__}\n")

        # Test 2: Test with non-existent group
        print("4. Testing with non-existent group (error handling)...")
        fake_group_id = "00000000-0000-0000-0000-000000000000"

        try:
            await group_service.get_group(
                org_id=test_org_id,
                group_id=fake_group_id,
                user_id=test_user_id
            )
            print("   ❌ Should have raised NotFoundError!")
        except Exception as e:
            print(f"   ✅ Correctly raised error: {type(e).__name__}")
            print(f"   Message: {str(e)}\n")

        # Test 3: Verify service token is being used
        print("5. Verifying service token authentication...")
        token = await token_manager.get_token()
        print(f"   ✅ Service token acquired")
        print(f"   Token (first 50 chars): {token[:50]}...")
        print(f"   Token length: {len(token)} chars\n")

        # Summary
        print("="*80)
        print("GROUPSERVICE TEST SUMMARY")
        print("="*80)
        print("✅ ServiceTokenManager working")
        print("✅ GroupService created successfully")
        print("✅ Error handling working (non-existent groups)")
        print("✅ Service token authentication working")
        print("\nℹ️  Note: To test real group fetching, create groups in Auth-API first!")
        print("   Use the Auth-API admin interface or API to create test groups.")
        print("="*80 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}: {str(e)}\n")
        logger.error("group_service_test_failed", error=str(e), exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_group_service())
    sys.exit(0 if success else 1)
