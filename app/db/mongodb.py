from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.models.group import Group
from app.models.message import Message
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def init_db():
    """
    Initialize database connection and Beanie ODM.

    Connection pool configuration:
    - maxPoolSize=50: Maximum number of connections (prevents exhaustion)
    - minPoolSize=10: Pre-allocated connections (reduces latency)
    - maxIdleTimeMS=45000: Close idle connections after 45s
    - serverSelectionTimeoutMS=5000: Fail fast if MongoDB is down
    """
    try:
        # Create Motor client with production-grade connection pooling
        client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            maxPoolSize=50,              # Max concurrent connections
            minPoolSize=10,               # Keep warm connections ready
            maxIdleTimeMS=45000,          # Close idle connections after 45s
            serverSelectionTimeoutMS=5000,  # Timeout for server selection (fail fast)
            retryWrites=True,             # Automatically retry write operations
            retryReads=True,              # Automatically retry read operations
        )

        # Test connection
        await client.admin.command('ping')
        logger.info(f"Successfully connected to MongoDB at {settings.MONGODB_URL}")

        # Initialize beanie with the database and document models
        await init_beanie(
            database=client[settings.DATABASE_NAME],
            document_models=[Group, Message]
        )

        logger.info("Beanie ODM initialized successfully")

    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def close_db(client: AsyncIOMotorClient):
    """Close database connection."""
    if client:
        client.close()
        logger.info("MongoDB connection closed")
