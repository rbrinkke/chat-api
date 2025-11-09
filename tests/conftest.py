"""
Pytest configuration and shared fixtures for Chat API tests.

This file provides reusable test fixtures including:
- Test client for API endpoints
- Test database setup/teardown
- Mock authentication
- Sample test data
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.main import app
from app.models.group import Group
from app.models.message import Message
from app.config import settings


# Configure pytest-asyncio
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db():
    """
    Provide a clean test database for each test.

    Uses a separate database to avoid interfering with development data.
    Automatically cleaned up after each test.
    """
    # Connect to test database
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_chat_db"]

    # Initialize Beanie with test database
    await init_beanie(database=db, document_models=[Group, Message])

    yield db

    # Cleanup: drop test database
    await client.drop_database("test_chat_db")
    client.close()


@pytest.fixture
async def test_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP client for testing API endpoints.

    Automatically handles database setup/teardown via test_db fixture.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def test_group_data():
    """Provide sample group data for tests."""
    return {
        "name": "Test Group",
        "description": "A test group for unit tests",
        "authorized_user_ids": ["test-user-123", "test-user-456"]
    }


@pytest.fixture
async def test_group(test_db, test_group_data):
    """Create and return a test group in the database."""
    group = Group(**test_group_data)
    await group.insert()
    return group


@pytest.fixture
def test_message_data(test_group):
    """Provide sample message data for tests."""
    return {
        "group_id": str(test_group.id),
        "sender_id": "test-user-123",
        "content": "Test message content"
    }


@pytest.fixture
async def test_message(test_db, test_group, test_message_data):
    """Create and return a test message in the database."""
    message = Message(**test_message_data)
    await message.insert()
    return message


@pytest.fixture
def auth_headers():
    """
    Provide authentication headers with a valid JWT token.

    NOTE: This is a mock token for testing. In production tests,
    you would generate a real JWT token using your auth service.
    """
    from jose import jwt
    from datetime import datetime, timedelta

    payload = {
        "sub": "test-user-123",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def unauthorized_auth_headers():
    """Provide authentication headers for a user not in the test group."""
    from jose import jwt
    from datetime import datetime, timedelta

    payload = {
        "sub": "unauthorized-user-999",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    return {"Authorization": f"Bearer {token}"}
