"""
Register chat-api-service OAuth client in Auth-API database.
"""

import asyncio
import asyncpg
from argon2 import PasswordHasher
from argon2.profiles import RFC_9106_LOW_MEMORY

# OAuth client configuration
CLIENT_ID = "chat-api-service"
CLIENT_NAME = "Chat API Service"
CLIENT_SECRET = "your-service-secret-change-in-production"  # Must match chat-api .env
CLIENT_TYPE = "confidential"  # Service-to-service client
GRANT_TYPES = ["client_credentials"]
ALLOWED_SCOPES = ["groups:read"]
REDIRECT_URIS = []  # Not used for client_credentials
REQUIRE_PKCE = False  # Not applicable for client_credentials
REQUIRE_CONSENT = False  # Service-to-service, no user consent
IS_FIRST_PARTY = True  # Internal service

# Database configuration
DB_HOST = "localhost"
DB_PORT = 5441  # From docker ps - activity-postgres-db
DB_NAME = "activitydb"
DB_USER = "auth_api_user"
DB_PASSWORD = "auth_api_secure_password_change_in_prod"


async def hash_client_secret(secret: str) -> str:
    """Hash client secret using Argon2id (same as Auth-API)."""
    ph = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)
    return ph.hash(secret)


async def register_client():
    """Register OAuth client in Auth-API database."""

    print("\n" + "="*80)
    print("OAUTH CLIENT REGISTRATION")
    print("="*80 + "\n")

    try:
        # Hash the client secret
        print(f"1. Hashing client secret...")
        client_secret_hash = await hash_client_secret(CLIENT_SECRET)
        print(f"   ✅ Secret hashed (Argon2id)")
        print(f"   Hash: {client_secret_hash[:50]}...\n")

        # Connect to database
        print(f"2. Connecting to Auth-API database...")
        print(f"   Host: {DB_HOST}:{DB_PORT}")
        print(f"   Database: {DB_NAME}")

        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        print(f"   ✅ Connected to database\n")

        # Get a user UUID for created_by (required field)
        print(f"2.5. Getting user UUID for created_by...")
        created_by_user = await conn.fetchval(
            "SELECT id FROM activity.users LIMIT 1"
        )
        if not created_by_user:
            print(f"   ❌ No users found in database. Please create a user first.")
            await conn.close()
            return False

        print(f"   ✅ Using user {created_by_user} as creator\n")

        # Check if client already exists
        print(f"3. Checking if client exists...")
        existing = await conn.fetchrow(
            "SELECT client_id FROM activity.oauth_clients WHERE client_id = $1",
            CLIENT_ID
        )

        if existing:
            print(f"   ⚠️  Client '{CLIENT_ID}' already exists")
            print(f"   Updating client secret...\n")

            await conn.execute(
                """
                UPDATE activity.oauth_clients
                SET client_secret_hash = $1,
                    grant_types = $2,
                    allowed_scopes = $3
                WHERE client_id = $4
                """,
                client_secret_hash,
                GRANT_TYPES,
                ALLOWED_SCOPES,
                CLIENT_ID
            )
            print(f"   ✅ Client updated\n")
        else:
            print(f"   Client does not exist, creating...\n")

            # Insert OAuth client using stored procedure
            print(f"4. Registering OAuth client (using sp_create_oauth_client)...")
            result_id = await conn.fetchval(
                """
                SELECT activity.sp_create_oauth_client(
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
                )
                """,
                CLIENT_ID,  # p_client_id
                CLIENT_NAME,  # p_client_name
                CLIENT_TYPE,  # p_client_type
                REDIRECT_URIS,  # p_redirect_uris
                ALLOWED_SCOPES,  # p_allowed_scopes
                client_secret_hash,  # p_client_secret_hash
                IS_FIRST_PARTY,  # p_is_first_party
                "Service-to-service OAuth client for Chat API to access group data",  # p_description
                None,  # p_logo_uri
                created_by_user,  # p_created_by
            )
            print(f"   ✅ OAuth client registered (ID: {result_id})\n")

            # Update grant_types (stored procedure doesn't set this)
            await conn.execute(
                "UPDATE activity.oauth_clients SET grant_types = $1 WHERE client_id = $2",
                GRANT_TYPES,
                CLIENT_ID
            )
            print(f"   ✅ Grant types updated to {GRANT_TYPES}\n")

        # Verify registration
        print(f"5. Verifying registration...")
        result = await conn.fetchrow(
            """
            SELECT client_id, client_name, client_type, grant_types, allowed_scopes
            FROM activity.oauth_clients
            WHERE client_id = $1
            """,
            CLIENT_ID
        )

        print(f"   ✅ Client verified:")
        print(f"   - Client ID: {result['client_id']}")
        print(f"   - Client Name: {result['client_name']}")
        print(f"   - Client Type: {result['client_type']}")
        print(f"   - Grant Types: {result['grant_types']}")
        print(f"   - Allowed Scopes: {result['allowed_scopes']}")

        await conn.close()

        print("\n" + "="*80)
        print("✅ SUCCESS - OAuth client registered in Auth-API!")
        print("Chat-API can now acquire service tokens from Auth-API.")
        print("="*80 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ REGISTRATION FAILED: {type(e).__name__}: {str(e)}\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(register_client())
    exit(0 if success else 1)
