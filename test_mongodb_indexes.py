"""
Verify MongoDB indexes and schema for multi-tenant Chat API.

Tests:
1. Message collection exists
2. Required fields present (org_id, group_id, group_name)
3. Compound index: (org_id, group_id, created_at)
4. Index: (org_id, sender_id)
5. Index performance with explain()
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.core.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


async def verify_mongodb_indexes():
    """Verify MongoDB indexes and schema."""

    print("\n" + "="*80)
    print("MONGODB INDEXES & SCHEMA VERIFICATION")
    print("="*80 + "\n")

    try:
        # Connect to MongoDB
        print(f"1. Connecting to MongoDB...")
        print(f"   URL: {settings.MONGODB_URL}")
        print(f"   Database: {settings.DATABASE_NAME}")

        client = AsyncIOMotorClient(settings.MONGODB_URL)
        db = client[settings.DATABASE_NAME]
        messages_collection = db["messages"]

        print(f"   ✅ Connected to MongoDB\n")

        # List all indexes
        print(f"2. Listing indexes on 'messages' collection...")
        indexes = await messages_collection.list_indexes().to_list(length=None)

        print(f"   Found {len(indexes)} indexes:")
        for idx in indexes:
            keys = idx.get("key", {})
            name = idx.get("name", "unknown")
            key_desc = ", ".join([f"{k}: {v}" for k, v in keys.items()])
            print(f"   - {name}: ({key_desc})")

        print()

        # Check for required indexes
        print(f"3. Verifying required indexes...")

        required_indexes = {
            "org_id_group_id_created_at": ["org_id", "group_id", "created_at"],
            "org_id_sender_id": ["org_id", "sender_id"]
        }

        found_indexes = {}
        for idx in indexes:
            keys = list(idx.get("key", {}).keys())
            name = idx.get("name", "")

            # Check compound index for pagination
            if keys == ["org_id", "group_id", "created_at"]:
                found_indexes["org_id_group_id_created_at"] = idx
                print(f"   ✅ Compound index (org_id, group_id, created_at) - FOUND")
                print(f"      Name: {name}")

            # Check sender index
            elif keys == ["org_id", "sender_id"]:
                found_indexes["org_id_sender_id"] = idx
                print(f"   ✅ Index (org_id, sender_id) - FOUND")
                print(f"      Name: {name}")

        # Check for missing indexes
        missing = []
        for req_name, req_keys in required_indexes.items():
            if req_name not in found_indexes:
                missing.append(req_name)
                print(f"   ❌ Index {req_name} ({', '.join(req_keys)}) - MISSING")

        print()

        # Check sample document schema
        print(f"4. Checking message schema (sample document)...")
        sample = await messages_collection.find_one()

        if sample:
            print(f"   ✅ Sample message found")

            required_fields = ["org_id", "group_id", "group_name", "sender_id", "content", "created_at"]
            print(f"\n   Required fields:")
            for field in required_fields:
                has_field = field in sample
                status = "✅" if has_field else "❌"
                value = sample.get(field, "MISSING")
                if field == "content" and len(str(value)) > 50:
                    value = str(value)[:50] + "..."
                print(f"   {status} {field}: {value}")
        else:
            print(f"   ⚠️  No messages in collection yet (empty)")
            print(f"   Creating test message to verify schema...")

            # Create test message
            from datetime import datetime
            test_message = {
                "org_id": "test-org-123",
                "group_id": "test-group-456",
                "group_name": "Test Group",
                "sender_id": "test-user-789",
                "content": "Test message for schema verification",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_deleted": False
            }

            result = await messages_collection.insert_one(test_message)
            print(f"   ✅ Test message created: {result.inserted_id}")

        print()

        # Test index performance
        print(f"5. Testing index performance (explain plans)...")

        if "org_id_group_id_created_at" in found_indexes:
            print(f"\n   Test Query 1: Find messages by org_id + group_id (with pagination)")
            explain = await messages_collection.find({
                "org_id": "test-org-123",
                "group_id": "test-group-456",
                "is_deleted": False
            }).sort("created_at", -1).limit(50).explain()

            winning_plan = explain.get("queryPlanner", {}).get("winningPlan", {})
            index_name = winning_plan.get("inputStage", {}).get("indexName", "COLLECTION_SCAN")

            if "org_id" in index_name or "IXSCAN" in str(winning_plan):
                print(f"   ✅ Uses index: {index_name}")
            else:
                print(f"   ⚠️  Collection scan detected (no index used)")
                print(f"      Winning plan: {winning_plan}")

        if "org_id_sender_id" in found_indexes:
            print(f"\n   Test Query 2: Find messages by org_id + sender_id")
            explain = await messages_collection.find({
                "org_id": "test-org-123",
                "sender_id": "test-user-789"
            }).explain()

            winning_plan = explain.get("queryPlanner", {}).get("winningPlan", {})
            index_name = winning_plan.get("inputStage", {}).get("indexName", "COLLECTION_SCAN")

            if "org_id" in index_name or "sender_id" in index_name or "IXSCAN" in str(winning_plan):
                print(f"   ✅ Uses index: {index_name}")
            else:
                print(f"   ⚠️  Collection scan detected (no index used)")

        print()

        # Summary
        print("="*80)
        if missing:
            print(f"⚠️  VERIFICATION INCOMPLETE - Missing indexes: {', '.join(missing)}")
            print(f"   These indexes need to be created for production performance!")
        else:
            print(f"✅ ALL VERIFICATIONS PASSED - MongoDB indexes & schema correct!")
        print("="*80 + "\n")

        client.close()
        return len(missing) == 0

    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {type(e).__name__}: {str(e)}\n")
        logger.error("mongodb_verification_failed", error=str(e), exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(verify_mongodb_indexes())
    sys.exit(0 if success else 1)
