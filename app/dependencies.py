"""
Dependency injection for FastAPI routes.

Provides reusable dependencies that can be easily mocked in tests.
"""

from app.services.chat_service import ChatService


def get_chat_service() -> ChatService:
    """
    Provide ChatService instance for dependency injection.

    This allows routes to receive the service via FastAPI's Depends(),
    making it easy to mock in tests:

    Example test setup:
        app.dependency_overrides[get_chat_service] = lambda: MockChatService()
    """
    return ChatService()
