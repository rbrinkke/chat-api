"""
Create missing MongoDB indexes for Chat API multi-tenant refactor.

Creates:
1. Compound index: (org_id, sender_id) for user message queries
2. Verifies existing compound index: (org_id, group_id, created_at)
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27019")
DATABASE_NAME = os.getenv("DATABASE_NAME", "chat_db")


async def create_indexes():
    """Create missing indexes."""

    print("\n" + "="*80)
    print("CREATE MISSING MONGODB INDEXES")
    print("="*80 + "\n")

    try:
        # Connect
        print(f"1. Connecting to MongoDB...")
        print(f"   URL: {MONGODB_URL}")
        print(f"   Database: {DATABASE_NAME}")

        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        messages = db["messages"]

        print(f"   ✅ Connected\n")

        # List existing indexes
        print(f"2. Current indexes:")
        indexes = await messages.list_indexes().to_list(length=None)
        for idx in indexes:
            keys = idx.get("key", {})
            name = idx.get("name", "")
            key_desc = ", ".join([f"{k}: {v}" for k, v in keys.items()])
            print(f"   - {name}: ({key_desc})")

        print()

        # Check if org_id_sender_id index exists
        print(f"3. Checking for (org_id, sender_id) index...")
        has_sender_index = any(
            list(idx.get("key", {}).keys()) == ["org_id", "sender_id"]
            for idx in indexes
        )

        if has_sender_index:
            print(f"   ✅ Index already exists - skipping\n")
        else:
            print(f"   ❌ Index missing - creating now...")

            # Create the index
            result = await messages.create_index(
                [("org_id", 1), ("sender_id", 1)],
                name="org_id_1_sender_id_1",
                background=True
            )

            print(f"   ✅ Index created: {result}\n")

        # Verify all required indexes exist
        print(f"4. Final verification...")
        indexes = await messages.list_indexes().to_list(length=None)

        required = [
            ["org_id", "group_id", "created_at"],
            ["org_id", "sender_id"]
        ]

        found = []
        for idx in indexes:
            keys = list(idx.get("key", {}).keys())
            if keys in required:
                found.append(keys)
                print(f"   ✅ Index {idx['name']} - OK")

        missing = [req for req in required if req not in found]
        if missing:
            print(f"\n   ❌ Still missing: {missing}")
        else:
            print(f"\n   ✅ All required indexes present!")

        print("\n" + "="*80)
        print("✅ INDEX CREATION COMPLETE")
        print("="*80 + "\n")

        client.close()
        return True

    except Exception as e:
        print(f"\n❌ FAILED: {type(e).__name__}: {str(e)}\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(create_indexes())
    exit(0 if success else 1)
