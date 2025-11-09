from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.models.group import Group
from app.models.message import Message
from app.config import settings
import logging

logger = logging.getLogger(__name__)


async def init_db():
    """Initialize database connection and Beanie ODM."""
    try:
        # Create Motor client
        client = AsyncIOMotorClient(settings.MONGODB_URL)

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
