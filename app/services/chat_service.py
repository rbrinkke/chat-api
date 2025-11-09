from datetime import datetime
from typing import List, Tuple
from bson import ObjectId
from bson.errors import InvalidId
from app.models.group import Group
from app.models.message import Message
from app.core.exceptions import NotFoundError, ForbiddenError, BadRequestError
from app.core.cache import cache, serialize_for_cache, deserialize_from_cache
from app.core.logging_config import get_logger
from app.services.connection_manager import manager

logger = get_logger(__name__)


def validate_object_id(id_string: str, resource_name: str = "Resource") -> ObjectId:
    """
    Safely convert a string to ObjectId with proper error handling.

    Args:
        id_string: The string to convert to ObjectId
        resource_name: Name of the resource for error messages

    Returns:
        ObjectId: Valid ObjectId instance

    Raises:
        BadRequestError: If the string is not a valid ObjectId format
    """
    try:
        return ObjectId(id_string)
    except InvalidId:
        raise BadRequestError(f"Invalid {resource_name} ID format: {id_string}")


class ChatService:
    """Service for handling chat operations."""

    async def create_message(
        self,
        group_id: str,
        sender_id: str,
        content: str
    ) -> Message:
        """Create a new message in a group."""
        # Verify user has access to the group
        group = await self._get_group_and_verify_access(group_id, sender_id)

        # Create message
        message = Message(
            group_id=group_id,
            sender_id=sender_id,
            content=content,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await message.insert()

        logger.info(f"Message created: {message.id} in group {group_id} by {sender_id}")

        # Broadcast via WebSocket
        await manager.broadcast_to_group(
            group_id,
            {
                "type": "new_message",
                "message": {
                    "id": str(message.id),
                    "group_id": message.group_id,
                    "sender_id": message.sender_id,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                    "updated_at": message.updated_at.isoformat(),
                    "is_deleted": message.is_deleted
                }
            }
        )

        return message

    async def get_messages(
        self,
        group_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Message], int]:
        """
        Get paginated messages for a group.

        Performance optimization: Uses aggregation pipeline to fetch both
        messages and total count in a single database roundtrip.
        """
        # Verify user has access to the group
        await self._get_group_and_verify_access(group_id, user_id)

        # Calculate skip
        skip = (page - 1) * page_size

        # Use aggregation pipeline for optimal performance
        # This fetches both paginated messages AND total count in ONE roundtrip
        pipeline = [
            # Match group and non-deleted messages
            {"$match": {"group_id": group_id, "is_deleted": False}},
            # Sort by newest first
            {"$sort": {"created_at": -1}},
            # Facet: Split into two parallel pipelines
            {
                "$facet": {
                    # Pipeline 1: Get paginated messages
                    "messages": [
                        {"$skip": skip},
                        {"$limit": page_size}
                    ],
                    # Pipeline 2: Get total count
                    "total": [
                        {"$count": "count"}
                    ]
                }
            }
        ]

        result = await Message.aggregate(pipeline).to_list()

        # Extract results
        if result and result[0]:
            messages_data = result[0].get("messages", [])
            total_data = result[0].get("total", [])

            # Convert dict results back to Message objects
            messages = [Message(**msg) for msg in messages_data]
            total = total_data[0]["count"] if total_data else 0
        else:
            messages = []
            total = 0

        return messages, total

    async def update_message(
        self,
        message_id: str,
        user_id: str,
        new_content: str
    ) -> Message:
        """Update a message (only by sender)."""
        # Get message
        message_id_obj = validate_object_id(message_id, "message")
        message = await Message.get(message_id_obj)
        if not message:
            raise NotFoundError("Message not found")

        # Verify sender
        if message.sender_id != user_id:
            raise ForbiddenError("You can only update your own messages")

        # Update message
        message.content = new_content
        message.updated_at = datetime.utcnow()
        await message.save()

        logger.info(f"Message updated: {message_id} by {user_id}")

        # Broadcast via WebSocket
        await manager.broadcast_to_group(
            message.group_id,
            {
                "type": "message_updated",
                "message": {
                    "id": str(message.id),
                    "group_id": message.group_id,
                    "sender_id": message.sender_id,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                    "updated_at": message.updated_at.isoformat(),
                    "is_deleted": message.is_deleted
                }
            }
        )

        return message

    async def delete_message(
        self,
        message_id: str,
        user_id: str
    ):
        """Soft delete a message (only by sender)."""
        # Get message
        message_id_obj = validate_object_id(message_id, "message")
        message = await Message.get(message_id_obj)
        if not message:
            raise NotFoundError("Message not found")

        # Verify sender
        if message.sender_id != user_id:
            raise ForbiddenError("You can only delete your own messages")

        # Soft delete
        message.is_deleted = True
        message.updated_at = datetime.utcnow()
        await message.save()

        logger.info(f"Message deleted: {message_id} by {user_id}")

        # Broadcast via WebSocket
        await manager.broadcast_to_group(
            message.group_id,
            {
                "type": "message_deleted",
                "message_id": str(message.id)
            }
        )

    async def get_group(self, group_id: str, user_id: str) -> Group:
        """Get a group by ID."""
        return await self._get_group_and_verify_access(group_id, user_id)

    async def get_user_groups(self, user_id: str) -> List[Group]:
        """Get all groups the user has access to."""
        groups = await Group.find(
            Group.authorized_user_ids == user_id
        ).to_list()
        return groups

    async def _get_group_and_verify_access(self, group_id: str, user_id: str) -> Group:
        """
        Get group and verify user has access.

        Performance optimization: Uses Redis cache to avoid repeated database queries
        for group data. Groups are cached for 5 minutes (TTL=300s).
        """
        group_id_obj = validate_object_id(group_id, "group")

        # Try cache first
        cache_key = f"group:{group_id}"
        cached_data = await cache.get(cache_key)

        if cached_data:
            # Cache hit - deserialize
            group_dict = deserialize_from_cache(cached_data)
            group = Group(**group_dict)
        else:
            # Cache miss - fetch from database
            group = await Group.get(group_id_obj)
            if not group:
                raise NotFoundError("Group not found")

            # Store in cache (5 minutes TTL)
            group_data = serialize_for_cache(group.model_dump())
            await cache.set(cache_key, group_data, ttl=300)

        # Verify access
        if user_id not in group.authorized_user_ids:
            raise ForbiddenError("You don't have access to this group")

        return group
