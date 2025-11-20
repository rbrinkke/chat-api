#!/usr/bin/env python3
"""
MongoDB Field Migration: group_id → conversation_id

Renames fields in MongoDB messages collection:
- group_id → conversation_id
- group_name → conversation_name

Also recreates indexes with new field names.

Usage:
    python migrations/migrate_mongodb_fields.py --dry-run  # Preview
    python migrations/migrate_mongodb_fields.py --execute  # Apply
"""

import asyncio
import argparse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
import os
from datetime import datetime


class MongoDBMigration:
    """MongoDB field rename migration."""

    def __init__(self, mongodb_url: str, database_name: str, dry_run: bool = True):
        self.mongodb_url = mongodb_url
        self.database_name = database_name
        self.dry_run = dry_run
        self.client = None
        self.db = None

    async def connect(self):
        """Connect to MongoDB."""
        print(f"🔌 Connecting to MongoDB: {self.mongodb_url}")
        self.client = AsyncIOMotorClient(self.mongodb_url)
        self.db = self.client[self.database_name]

        # Test connection
        await self.client.admin.command('ping')
        print("✅ Connected successfully")

    async def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            print("🔌 Connection closed")

    async def get_collection_stats(self) -> dict:
        """Get current collection statistics."""
        messages = self.db.messages

        total_count = await messages.count_documents({})
        with_group_id = await messages.count_documents({"group_id": {"$exists": True}})
        with_conversation_id = await messages.count_documents({"conversation_id": {"$exists": True}})

        return {
            "total_documents": total_count,
            "with_group_id": with_group_id,
            "with_conversation_id": with_conversation_id,
        }

    async def list_indexes(self) -> list:
        """List all indexes on messages collection."""
        messages = self.db.messages
        indexes = await messages.index_information()
        return indexes

    async def backup_collection(self):
        """Create backup collection before migration."""
        backup_name = f"messages_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        print(f"\n📦 Creating backup: {backup_name}")

        if not self.dry_run:
            # Copy collection
            pipeline = [{"$match": {}}, {"$out": backup_name}]
            await self.db.messages.aggregate(pipeline).to_list(length=None)
            print(f"✅ Backup created: {backup_name}")
        else:
            print(f"⚠️  DRY RUN: Would create backup {backup_name}")

    async def rename_fields(self):
        """Rename group_id → conversation_id and group_name → conversation_name."""
        messages = self.db.messages

        print("\n🔄 Renaming fields in messages collection...")

        stats = await self.get_collection_stats()
        docs_to_update = stats["with_group_id"]

        print(f"   Documents to update: {docs_to_update}")

        if docs_to_update == 0:
            print("   ℹ️  No documents with group_id found (already migrated?)")
            return

        if not self.dry_run:
            result = await messages.update_many(
                {},
                {
                    "$rename": {
                        "group_id": "conversation_id",
                        "group_name": "conversation_name"
                    }
                }
            )

            print(f"   ✅ Updated {result.modified_count} documents")
        else:
            print(f"   ⚠️  DRY RUN: Would rename fields in {docs_to_update} documents")

    async def drop_old_indexes(self):
        """Drop indexes that reference old field names."""
        messages = self.db.messages
        indexes = await self.list_indexes()

        print("\n🗑️  Dropping old indexes...")

        old_indexes = [
            name for name in indexes.keys()
            if 'group_id' in name and name != '_id_'
        ]

        if not old_indexes:
            print("   ℹ️  No old indexes found")
            return

        for index_name in old_indexes:
            print(f"   Dropping: {index_name}")
            if not self.dry_run:
                await messages.drop_index(index_name)
                print(f"   ✅ Dropped {index_name}")
            else:
                print(f"   ⚠️  DRY RUN: Would drop {index_name}")

    async def create_new_indexes(self):
        """Create indexes with new field names."""
        messages = self.db.messages

        print("\n🔧 Creating new indexes...")

        # Index 1: org_id + conversation_id + created_at (compound)
        index_1 = [
            ("org_id", ASCENDING),
            ("conversation_id", ASCENDING),
            ("created_at", DESCENDING)
        ]

        # Index 2: conversation_id + created_at (for queries without org_id)
        index_2 = [
            ("conversation_id", ASCENDING),
            ("created_at", DESCENDING)
        ]

        # Index 3: sender_id (for user's own messages)
        index_3 = [("sender_id", ASCENDING)]

        indexes_to_create = [
            (index_1, "org_id_1_conversation_id_1_created_at_-1"),
            (index_2, "conversation_id_1_created_at_-1"),
            (index_3, "sender_id_1"),
        ]

        for index_spec, index_name in indexes_to_create:
            print(f"   Creating: {index_name}")
            if not self.dry_run:
                await messages.create_index(index_spec, name=index_name)
                print(f"   ✅ Created {index_name}")
            else:
                print(f"   ⚠️  DRY RUN: Would create {index_name}")

    async def verify_migration(self):
        """Verify migration completed successfully."""
        print("\n✅ Verifying migration...")

        stats = await self.get_collection_stats()

        print(f"   Total documents: {stats['total_documents']}")
        print(f"   With conversation_id: {stats['with_group_id']}")
        print(f"   With conversation_id: {stats['with_conversation_id']}")

        if stats['with_group_id'] > 0:
            print("   ⚠️  WARNING: Some documents still have group_id!")
            return False

        if stats['with_conversation_id'] != stats['total_documents']:
            print("   ⚠️  WARNING: Not all documents have conversation_id!")
            return False

        # Check indexes
        indexes = await self.list_indexes()
        expected_indexes = [
            "org_id_1_conversation_id_1_created_at_-1",
            "conversation_id_1_created_at_-1",
            "sender_id_1"
        ]

        missing_indexes = [idx for idx in expected_indexes if idx not in indexes]
        if missing_indexes:
            print(f"   ⚠️  WARNING: Missing indexes: {missing_indexes}")
            return False

        print("   ✅ Migration verified successfully!")
        return True

    async def run(self):
        """Run the complete migration."""
        print("=" * 70)
        print("🗄️  MongoDB Migration: group_id → conversation_id")
        print("=" * 70)
        print(f"Mode: {'DRY RUN (preview only)' if self.dry_run else 'EXECUTE (applying changes)'}")
        print(f"Database: {self.database_name}")
        print()

        try:
            await self.connect()

            # Show current state
            print("\n📊 Current State:")
            stats = await self.get_collection_stats()
            for key, value in stats.items():
                print(f"   {key}: {value}")

            print("\n📋 Current Indexes:")
            indexes = await self.list_indexes()
            for name, spec in indexes.items():
                if name != '_id_':
                    print(f"   {name}: {spec['key']}")

            # Create backup
            await self.backup_collection()

            # Perform migration
            await self.rename_fields()
            await self.drop_old_indexes()
            await self.create_new_indexes()

            # Verify
            if not self.dry_run:
                await self.verify_migration()

            print("\n" + "=" * 70)
            if self.dry_run:
                print("⚠️  DRY RUN MODE - No changes were applied")
                print("Run with --execute to apply changes")
            else:
                print("✅ Migration completed successfully!")
                print("\nNext steps:")
                print("1. Verify application works: docker compose up -d")
                print("2. Run tests: pytest")
                print("3. Check MongoDB: mongosh -> use chat_db -> db.messages.findOne()")

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            raise
        finally:
            await self.close()


def main():
    parser = argparse.ArgumentParser(
        description="MongoDB field migration: group_id → conversation_id"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Apply changes (default is dry-run preview)'
    )
    parser.add_argument(
        '--mongodb-url',
        default=os.getenv('MONGODB_URL', 'mongodb://localhost:27017'),
        help='MongoDB connection URL'
    )
    parser.add_argument(
        '--database',
        default=os.getenv('DATABASE_NAME', 'chat_db'),
        help='Database name'
    )

    args = parser.parse_args()

    migration = MongoDBMigration(
        mongodb_url=args.mongodb_url,
        database_name=args.database,
        dry_run=not args.execute
    )

    asyncio.run(migration.run())


if __name__ == '__main__':
    main()
