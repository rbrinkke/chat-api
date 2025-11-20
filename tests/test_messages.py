"""
Tests for message endpoints.

Tests cover:
- Creating messages
- Retrieving paginated messages
- Updating own messages
- Deleting own messages
- Authorization checks
- Input validation
"""

import pytest
from httpx import AsyncClient


class TestMessageCreation:
    """Tests for POST /api/chat/conversations/{conversation_id}/messages"""

    @pytest.mark.asyncio
    async def test_create_message_success(
        self, test_client: AsyncClient, test_group, auth_headers
    ):
        """Test successful message creation."""
        response = await test_client.post(
            f"/api/chat/groups/{test_group.id}/messages",
            json={"content": "Hello, world!"},
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Hello, world!"
        assert data["sender_id"] == "test-user-123"
        assert data["group_id"] == str(test_group.id)
        assert data["is_deleted"] is False

    @pytest.mark.asyncio
    async def test_create_message_unauthorized(
        self, test_client: AsyncClient, test_group, unauthorized_auth_headers
    ):
        """Test message creation fails for unauthorized user."""
        response = await test_client.post(
            f"/api/chat/groups/{test_group.id}/messages",
            json={"content": "I shouldn't be able to send this"},
            headers=unauthorized_auth_headers
        )

        assert response.status_code == 403
        assert "access" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_message_invalid_group(
        self, test_client: AsyncClient, auth_headers
    ):
        """Test message creation fails for non-existent group."""
        fake_group_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
        response = await test_client.post(
            f"/api/chat/groups/{fake_group_id}/messages",
            json={"content": "Test"},
            headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_message_invalid_objectid(
        self, test_client: AsyncClient, auth_headers
    ):
        """Test message creation fails with invalid ObjectId format."""
        response = await test_client.post(
            "/api/chat/groups/invalid-id/messages",
            json={"content": "Test"},
            headers=auth_headers
        )

        assert response.status_code == 400
        assert "Invalid" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_message_xss_sanitization(
        self, test_client: AsyncClient, test_group, auth_headers
    ):
        """Test that HTML/JS is stripped from message content (XSS prevention)."""
        response = await test_client.post(
            f"/api/chat/groups/{test_group.id}/messages",
            json={"content": "<script>alert('XSS')</script>Hello"},
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        # Should strip script tags
        assert "<script>" not in data["content"]
        assert "Hello" in data["content"]

    @pytest.mark.asyncio
    async def test_create_message_empty_content(
        self, test_client: AsyncClient, test_group, auth_headers
    ):
        """Test that empty messages are rejected."""
        response = await test_client.post(
            f"/api/chat/groups/{test_group.id}/messages",
            json={"content": ""},
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error


class TestMessageRetrieval:
    """Tests for GET /api/chat/conversations/{conversation_id}/messages"""

    @pytest.mark.asyncio
    async def test_get_messages_success(
        self, test_client: AsyncClient, test_group, test_message, auth_headers
    ):
        """Test successful message retrieval."""
        response = await test_client.get(
            f"/api/chat/groups/{test_group.id}/messages",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "total" in data
        assert "page" in data
        assert data["total"] >= 1
        assert len(data["messages"]) >= 1

    @pytest.mark.asyncio
    async def test_get_messages_pagination(
        self, test_client: AsyncClient, test_group, auth_headers
    ):
        """Test message pagination."""
        # Create multiple messages
        from app.models.message import Message
        for i in range(10):
            msg = Message(
                conversation_id =str(test_group.id),
                sender_id="test-user-123",
                content=f"Message {i}"
            )
            await msg.insert()

        # Test first page
        response = await test_client.get(
            f"/api/chat/groups/{test_group.id}/messages?page=1&page_size=5",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 5
        assert data["has_more"] is True

        # Test second page
        response = await test_client.get(
            f"/api/chat/groups/{test_group.id}/messages?page=2&page_size=5",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 5


class TestMessageUpdate:
    """Tests for PUT /api/chat/messages/{message_id}"""

    @pytest.mark.asyncio
    async def test_update_own_message(
        self, test_client: AsyncClient, test_message, auth_headers
    ):
        """Test that users can update their own messages."""
        response = await test_client.put(
            f"/api/chat/messages/{test_message.id}",
            json={"content": "Updated content"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated content"

    @pytest.mark.asyncio
    async def test_update_others_message_forbidden(
        self, test_client: AsyncClient, test_db, test_group, unauthorized_auth_headers
    ):
        """Test that users cannot update others' messages."""
        # Create message from different user
        from app.models.message import Message
        message = Message(
            conversation_id =str(test_group.id),
            sender_id="test-user-456",
            content="Someone else's message"
        )
        await message.insert()

        response = await test_client.put(
            f"/api/chat/messages/{message.id}",
            json={"content": "Trying to edit someone else's message"},
            headers=unauthorized_auth_headers
        )

        assert response.status_code in [403, 404]  # Forbidden or not found


class TestMessageDeletion:
    """Tests for DELETE /api/chat/messages/{message_id}"""

    @pytest.mark.asyncio
    async def test_soft_delete_own_message(
        self, test_client: AsyncClient, test_message, auth_headers
    ):
        """Test soft deletion of own message."""
        response = await test_client.delete(
            f"/api/chat/messages/{test_message.id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify message is soft-deleted (not hard-deleted)
        from app.models.message import Message
        message = await Message.get(test_message.id)
        assert message is not None
        assert message.is_deleted is True
