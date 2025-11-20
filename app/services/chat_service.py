"""
ChatService - Message operations with multi-tenant org_id validation

Architecture:
- Auth-API handles ALL permission validation via require_permission() decorator
- Messages stored in MongoDB with org_id for tenant isolation
- No group metadata stored - Auth API is Single Source of Truth

Security Model:
- Multi-tenant isolation via org_id
- Permission validation via Auth-API (happens in routes before service call)
- Message ownership validation (sender_id)
- Prevents cross-org data leaks
"""

from datetime import datetime
from typing import List, Tuple
import time
from app.models.message import Message
from app.core.exceptions import NotFoundError, ForbiddenError, BadRequestError
from app.core.logging_config import get_logger
from app.services.connection_manager import manager
from app.core import metrics

logger = get_logger(__name__)


class ChatService:
    """
    Service for handling chat operations with multi-tenant org_id validation.

    All operations validate:
    1. Permission validation happens in routes (via require_permission decorator)
    2. org_id filtering for multi-tenant isolation
    3. Message operations respect sender ownership

    Security:
    - Multi-tenant isolation via org_id filtering
    - Permission checks via Auth-API (in routes)
    - Message ownership validation
    """

    def __init__(self):
        """Initialize ChatService."""
        pass

    async def create_message(
        self,
        conversation_id: str,
        org_id: str,
        sender_id: str,
        content: str,
        user_token: str = None
    ) -> Message:
        """
        Create a new message in a conversation.

        Security Flow:
        1. Permission already validated in route (via require_permission decorator)
        2. Create message with org_id + conversation_id
        3. Broadcast to WebSocket connections

        Args:
            conversation_id: Conversation UUID (maps to Auth-API group for RBAC)
            org_id: Organization UUID from user's JWT token
            sender_id: User UUID from JWT token
            content: Message content (already sanitized)

        Returns:
            Created Message object
        """
        start_time = time.time()

        try:
            # Create message with org_id (permission already validated in route)
            message = Message(
                org_id=org_id,
                conversation_id=conversation_id,
                sender_id=sender_id,
                content=content,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            await message.insert()

            # Track MongoDB operation
            metrics.mongodb_operations_total.labels(
                operation="insert",
                collection="messages",
                status="success"
            ).inc()

            logger.info(
                "message_created",
                message_id=str(message.id),
                conversation_id =conversation_id,
                org_id=org_id,
                sender_id=sender_id
            )

            # Broadcast via WebSocket
            await manager.broadcast_to_group(
                conversation_id,
                {
                    "type": "new_message",
                    "message": {
                        "id": str(message.id),
                        "org_id": message.org_id,
                        "conversation_id": message.conversation_id,
                        "sender_id": message.sender_id,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "updated_at": message.updated_at.isoformat(),
                        "is_deleted": message.is_deleted
                    }
                }
            )

            # Track successful message creation
            metrics.messages_created_total.labels(conversation_id =conversation_id).inc()

            return message

        except Exception as e:
            # Track errors
            metrics.message_operation_errors_total.labels(
                operation="create",
                error_type=type(e).__name__
            ).inc()
            raise

        finally:
            # Track operation duration
            duration = time.time() - start_time
            metrics.message_operation_duration_seconds.labels(
                operation="create",
                conversation_id =conversation_id
            ).observe(duration)

    async def get_messages(
        self,
        conversation_id: str,
        org_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 50,
        user_token: str = None
    ) -> Tuple[List[Message], int]:
        """
        Get paginated messages for a conversation with org_id filtering.

        Security Flow:
        1. Permission already validated in route (via require_permission decorator)
        2. Query messages with compound filter: (org_id, conversation_id, is_deleted)
        3. MongoDB index optimized: (org_id, conversation_id, created_at)

        Args:
            conversation_id: Conversation UUID (maps to Auth-API group for RBAC)
            org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token
            page: Page number (1-indexed)
            page_size: Messages per page (max 100)

        Returns:
            Tuple of (messages, total_count)

        Performance:
        - Uses aggregation pipeline for single-roundtrip query
        - Compound index on (org_id, conversation_id, created_at)
        """
        # Permission already validated in route

        # Calculate skip
        skip = (page - 1) * page_size

        # Use aggregation pipeline for optimal performance
        # CRITICAL: Filter by BOTH org_id AND conversation_id for multi-tenant isolation
        pipeline = [
            # Match org_id + conversation_id + non-deleted (uses compound index)
            {
                "$match": {
                    "org_id": org_id,
                    "conversation_id": conversation_id,
                    "is_deleted": False
                }
            },
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

        logger.info(
            "messages_fetched",
            conversation_id =conversation_id,
            org_id=org_id,
            page=page,
            page_size=page_size,
            total=total,
            returned=len(messages)
        )

        return messages, total

    async def update_message(
        self,
        message_id: str,
        conversation_id: str,
        org_id: str,
        user_id: str,
        new_content: str,
        user_token: str = None
    ) -> Message:
        """
        Update a message (only by sender).

        Security Flow:
        1. Fetch message from MongoDB
        2. Validate message.conversation_id == conversation_id (URL consistency)
        3. Validate message.org_id == org_id (multi-tenant security)
        4. Validate message.sender_id == user_id (ownership)
        5. Update content and broadcast

        Args:
            message_id: Message ObjectId string
            conversation_id: Group UUID from URL path
            org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token
            new_content: Updated message content (already sanitized)

        Returns:
            Updated Message object

        Raises:
            NotFoundError: Message not found or conversation_id mismatch
            ForbiddenError: Not message sender or org_id mismatch
        """
        start_time = time.time()

        try:
            # Get message - Beanie auto-converts string to ObjectId
            message = await Message.get(message_id)
            if not message:
                raise NotFoundError("Message not found")

            # CRITICAL: Validate conversation_id matches URL (prevents information leakage)
            # Return 404 (not 400/403) to avoid revealing message existence in other groups
            if message.conversation_id != conversation_id:
                logger.warning(
                    "message_group_mismatch",
                    message_id=message_id,
                    url_group_id=conversation_id,
                    message_group_id=message.conversation_id,
                    user_id=user_id,
                    reason="group_id_mismatch_returns_404"
                )
                raise NotFoundError("Message not found")

            # CRITICAL: Validate org_id matches (multi-tenant security)
            if message.org_id != org_id:
                logger.error(
                    "cross_org_message_update_attempt_blocked",
                    message_id=message_id,
                    message_org_id=message.org_id,
                    token_org_id=org_id,
                    user_id=user_id,
                    security_violation=True
                )
                raise ForbiddenError("Not authorized to update this message")

            # Verify sender ownership
            if message.sender_id != user_id:
                raise ForbiddenError("You can only update your own messages")

            # Update message
            message.content = new_content
            message.updated_at = datetime.utcnow()
            await message.save()

            # Track MongoDB operation
            metrics.mongodb_operations_total.labels(
                operation="update",
                collection="messages",
                status="success"
            ).inc()

            logger.info(
                "message_updated",
                message_id=message_id,
                org_id=org_id,
                user_id=user_id
            )

            # Broadcast via WebSocket
            await manager.broadcast_to_group(
                message.conversation_id,
                {
                    "type": "message_updated",
                    "message": {
                        "id": str(message.id),
                        "org_id": message.org_id,
                        "conversation_id": message.conversation_id,
                        "sender_id": message.sender_id,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "updated_at": message.updated_at.isoformat(),
                        "is_deleted": message.is_deleted
                    }
                }
            )

            # Track successful update
            metrics.messages_updated_total.labels(conversation_id =message.conversation_id).inc()

            return message

        except Exception as e:
            # Track errors
            metrics.message_operation_errors_total.labels(
                operation="update",
                error_type=type(e).__name__
            ).inc()
            raise

        finally:
            # Track operation duration
            duration = time.time() - start_time
            metrics.message_operation_duration_seconds.labels(
                operation="update",
                conversation_id =message.conversation_id if 'message' in locals() else "unknown"
            ).observe(duration)

    async def delete_message(
        self,
        message_id: str,
        conversation_id: str,
        org_id: str,
        user_id: str,
        user_token: str = None,
        is_admin: bool = False
    ):
        """
        Soft delete a message (by sender or admin).

        Security Flow:
        1. Fetch message from MongoDB
        2. Validate message.conversation_id == conversation_id (URL consistency)
        3. Validate message.org_id == org_id (multi-tenant security)
        4. Validate message.sender_id == user_id (ownership) OR is_admin=True
        5. Soft delete and broadcast

        Args:
            message_id: Message ObjectId string
            conversation_id: Group UUID from URL path
            org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token
            user_token: Raw JWT token (optional)
            is_admin: True if user has chat:admin permission (bypasses ownership check)

        Raises:
            NotFoundError: Message not found or conversation_id mismatch
            ForbiddenError: Not message sender or org_id mismatch
        """
        start_time = time.time()

        try:
            # Get message - Beanie auto-converts string to ObjectId
            message = await Message.get(message_id)
            if not message:
                raise NotFoundError("Message not found")

            # CRITICAL: Validate conversation_id matches URL (prevents information leakage)
            # Return 404 (not 400/403) to avoid revealing message existence in other groups
            if message.conversation_id != conversation_id:
                logger.warning(
                    "message_group_mismatch",
                    message_id=message_id,
                    url_group_id=conversation_id,
                    message_group_id=message.conversation_id,
                    user_id=user_id,
                    reason="group_id_mismatch_returns_404"
                )
                raise NotFoundError("Message not found")

            # CRITICAL: Validate org_id matches (multi-tenant security)
            if message.org_id != org_id:
                logger.error(
                    "cross_org_message_delete_attempt_blocked",
                    message_id=message_id,
                    message_org_id=message.org_id,
                    token_org_id=org_id,
                    user_id=user_id,
                    security_violation=True
                )
                raise ForbiddenError("Not authorized to delete this message")

            # Verify sender ownership OR admin permission
            if not is_admin and message.sender_id != user_id:
                logger.warning(
                    "non_admin_delete_attempt_blocked",
                    message_id=message_id,
                    message_sender_id=message.sender_id,
                    requesting_user_id=user_id,
                    reason="not_owner_and_not_admin"
                )
                raise ForbiddenError("You can only delete your own messages")

            # Soft delete
            message.is_deleted = True
            message.updated_at = datetime.utcnow()
            await message.save()

            # Track MongoDB operation
            metrics.mongodb_operations_total.labels(
                operation="update",
                collection="messages",
                status="success"
            ).inc()

            logger.info(
                "message_deleted",
                message_id=message_id,
                org_id=org_id,
                user_id=user_id
            )

            # Broadcast via WebSocket
            await manager.broadcast_to_group(
                message.conversation_id,
                {
                    "type": "message_deleted",
                    "message_id": str(message.id)
                }
            )

            # Track successful deletion
            metrics.messages_deleted_total.labels(conversation_id =message.conversation_id).inc()

        except Exception as e:
            # Track errors
            metrics.message_operation_errors_total.labels(
                operation="delete",
                error_type=type(e).__name__
            ).inc()
            raise

        finally:
            # Track operation duration
            duration = time.time() - start_time
            metrics.message_operation_duration_seconds.labels(
                operation="delete",
                conversation_id =message.conversation_id if 'message' in locals() else "unknown"
            ).observe(duration)

