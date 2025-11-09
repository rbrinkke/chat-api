from datetime import datetime
from typing import List, Tuple
from bson import ObjectId
from app.models.group import Group
from app.models.message import Message
from app.core.exceptions import NotFoundError, ForbiddenError
from app.services.connection_manager import manager
import logging

logger = logging.getLogger(__name__)


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
        """Get paginated messages for a group."""
        # Verify user has access to the group
        await self._get_group_and_verify_access(group_id, user_id)

        # Calculate skip
        skip = (page - 1) * page_size

        # Get messages (excluding soft-deleted ones)
        messages = await Message.find(
            Message.group_id == group_id,
            Message.is_deleted == False
        ).sort(-Message.created_at).skip(skip).limit(page_size).to_list()

        # Get total count
        total = await Message.find(
            Message.group_id == group_id,
            Message.is_deleted == False
        ).count()

        return messages, total

    async def update_message(
        self,
        message_id: str,
        user_id: str,
        new_content: str
    ) -> Message:
        """Update a message (only by sender)."""
        # Get message
        message = await Message.get(ObjectId(message_id))
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
        message = await Message.get(ObjectId(message_id))
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
        """Get group and verify user has access."""
        group = await Group.get(ObjectId(group_id))
        if not group:
            raise NotFoundError("Group not found")

        if user_id not in group.authorized_user_ids:
            raise ForbiddenError("You don't have access to this group")

        return group
