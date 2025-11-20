"""
ChatService - Message operations with multi-tenant org_id validation

Architecture:
- Auth-API is Single Source of Truth for groups
- GroupService fetches group data with org_id validation
- Messages stored in MongoDB with org_id for tenant isolation
- All operations validate: group.org_id == message.org_id == token.org_id

Security Model:
- Multi-tenant isolation via org_id
- Group authorization via GroupService (Auth-API)
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
from app.services.group_service import get_group_service, GroupDetails, GroupService
from app.core import metrics

logger = get_logger(__name__)


class ChatService:
    """
    Service for handling chat operations with multi-tenant org_id validation.

    All operations validate:
    1. User is member of group (via GroupService)
    2. Group belongs to user's organization (group.org_id == token.org_id)
    3. Message operations respect sender ownership

    Security:
    - Multi-tenant isolation via org_id filtering
    - Group authorization via Auth-API
    - Message ownership validation
    """

    def __init__(self, group_service: GroupService):
        """Initialize ChatService with GroupService."""
        self.group_service = group_service

    async def create_message(
        self,
        group_id: str,
        org_id: str,
        sender_id: str,
        content: str,
        user_token: str = None
    ) -> Message:
        """
        Create a new message in a group.

        Security Flow:
        1. Validate group exists and user is member (GroupService)
        2. Validate group.org_id == org_id (multi-tenant security)
        3. Create message with org_id, group_id, group_name
        4. Broadcast to WebSocket connections

        Args:
            group_id: Group UUID from Auth-API
            org_id: Organization UUID from user's JWT token
            sender_id: User UUID from JWT token
            content: Message content (already sanitized)

        Returns:
            Created Message object

        Raises:
            NotFoundError: Group not found
            ForbiddenError: User not authorized for group or org_id mismatch
        """
        start_time = time.time()

        try:
            # Verify user has access to the group AND org_id matches
            group = await self._verify_group_access(group_id, org_id, sender_id, user_token)

            # Create message with org_id and denormalized group_name
            message = Message(
                org_id=org_id,
                group_id=group_id,
                group_name=group.name,
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
                group_id=group_id,
                org_id=org_id,
                sender_id=sender_id
            )

            # Broadcast via WebSocket
            await manager.broadcast_to_group(
                group_id,
                {
                    "type": "new_message",
                    "message": {
                        "id": str(message.id),
                        "org_id": message.org_id,
                        "group_id": message.group_id,
                        "group_name": message.group_name,
                        "sender_id": message.sender_id,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "updated_at": message.updated_at.isoformat(),
                        "is_deleted": message.is_deleted
                    }
                }
            )

            # Track successful message creation
            metrics.messages_created_total.labels(group_id=group_id).inc()

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
                group_id=group_id
            ).observe(duration)

    async def get_messages(
        self,
        group_id: str,
        org_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 50,
        user_token: str = None
    ) -> Tuple[List[Message], int]:
        """
        Get paginated messages for a group with org_id filtering.

        Security Flow:
        1. Validate group exists and user is member (GroupService)
        2. Validate group.org_id == org_id (multi-tenant security)
        3. Query messages with compound filter: (org_id, group_id, is_deleted)
        4. MongoDB index optimized: (org_id, group_id, created_at)

        Args:
            group_id: Group UUID from Auth-API
            org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token
            page: Page number (1-indexed)
            page_size: Messages per page (max 100)

        Returns:
            Tuple of (messages, total_count)

        Performance:
        - Uses aggregation pipeline for single-roundtrip query
        - Compound index on (org_id, group_id, created_at)
        - Redis-cached group validation

        Raises:
            NotFoundError: Group not found
            ForbiddenError: User not authorized or org_id mismatch
        """
        # Verify user has access to the group AND org_id matches
        await self._verify_group_access(group_id, org_id, user_id, user_token)

        # Calculate skip
        skip = (page - 1) * page_size

        # Use aggregation pipeline for optimal performance
        # CRITICAL: Filter by BOTH org_id AND group_id for multi-tenant isolation
        pipeline = [
            # Match org_id + group_id + non-deleted (uses compound index)
            {
                "$match": {
                    "org_id": org_id,
                    "group_id": group_id,
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
            group_id=group_id,
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
        group_id: str,
        org_id: str,
        user_id: str,
        new_content: str,
        user_token: str = None
    ) -> Message:
        """
        Update a message (only by sender).

        Security Flow:
        1. Fetch message from MongoDB
        2. Validate message.group_id == group_id (URL consistency)
        3. Validate message.org_id == org_id (multi-tenant security)
        4. Validate message.sender_id == user_id (ownership)
        5. Update content and broadcast

        Args:
            message_id: Message ObjectId string
            group_id: Group UUID from URL path
            org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token
            new_content: Updated message content (already sanitized)

        Returns:
            Updated Message object

        Raises:
            NotFoundError: Message not found or group_id mismatch
            ForbiddenError: Not message sender or org_id mismatch
        """
        start_time = time.time()

        try:
            # Get message - Beanie auto-converts string to ObjectId
            message = await Message.get(message_id)
            if not message:
                raise NotFoundError("Message not found")

            # CRITICAL: Validate group_id matches URL (prevents information leakage)
            # Return 404 (not 400/403) to avoid revealing message existence in other groups
            if message.group_id != group_id:
                logger.warning(
                    "message_group_mismatch",
                    message_id=message_id,
                    url_group_id=group_id,
                    message_group_id=message.group_id,
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
                message.group_id,
                {
                    "type": "message_updated",
                    "message": {
                        "id": str(message.id),
                        "org_id": message.org_id,
                        "group_id": message.group_id,
                        "group_name": message.group_name,
                        "sender_id": message.sender_id,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "updated_at": message.updated_at.isoformat(),
                        "is_deleted": message.is_deleted
                    }
                }
            )

            # Track successful update
            metrics.messages_updated_total.labels(group_id=message.group_id).inc()

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
                group_id=message.group_id if 'message' in locals() else "unknown"
            ).observe(duration)

    async def delete_message(
        self,
        message_id: str,
        group_id: str,
        org_id: str,
        user_id: str,
        user_token: str = None,
        is_admin: bool = False
    ):
        """
        Soft delete a message (by sender or admin).

        Security Flow:
        1. Fetch message from MongoDB
        2. Validate message.group_id == group_id (URL consistency)
        3. Validate message.org_id == org_id (multi-tenant security)
        4. Validate message.sender_id == user_id (ownership) OR is_admin=True
        5. Soft delete and broadcast

        Args:
            message_id: Message ObjectId string
            group_id: Group UUID from URL path
            org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token
            user_token: Raw JWT token (optional)
            is_admin: True if user has chat:admin permission (bypasses ownership check)

        Raises:
            NotFoundError: Message not found or group_id mismatch
            ForbiddenError: Not message sender or org_id mismatch
        """
        start_time = time.time()

        try:
            # Get message - Beanie auto-converts string to ObjectId
            message = await Message.get(message_id)
            if not message:
                raise NotFoundError("Message not found")

            # CRITICAL: Validate group_id matches URL (prevents information leakage)
            # Return 404 (not 400/403) to avoid revealing message existence in other groups
            if message.group_id != group_id:
                logger.warning(
                    "message_group_mismatch",
                    message_id=message_id,
                    url_group_id=group_id,
                    message_group_id=message.group_id,
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
                message.group_id,
                {
                    "type": "message_deleted",
                    "message_id": str(message.id)
                }
            )

            # Track successful deletion
            metrics.messages_deleted_total.labels(group_id=message.group_id).inc()

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
                group_id=message.group_id if 'message' in locals() else "unknown"
            ).observe(duration)

    async def _verify_group_access(
        self,
        group_id: str,
        expected_org_id: str,
        user_id: str,
        user_token: str = None
    ) -> GroupDetails:
        """
        Verify user has access to group AND group belongs to user's organization.

        Security Checks:
        1. Group exists in Auth-API
        2. Group.org_id == expected_org_id (multi-tenant isolation)
        3. User is member of group (user_id in group.member_ids)

        Args:
            group_id: Group UUID from Auth-API
            expected_org_id: Organization UUID from user's JWT token
            user_id: User UUID from JWT token

        Returns:
            GroupDetails if all checks pass

        Raises:
            NotFoundError: Group not found
            ForbiddenError: User not authorized or org_id mismatch

        Performance:
            - Redis-cached group lookups (300s TTL)
            - Auth-API called only on cache miss
            - Org_id validation happens in GroupService
        """
        # GroupService handles:
        # 1. Fetch from Auth-API (with caching)
        # 2. Validate group.org_id == expected_org_id
        # 3. Returns None if unauthorized
        group = await self.group_service.get_group_details(
            group_id=group_id,
            expected_org_id=expected_org_id,
            user_token=user_token
        )

        if not group:
            logger.warning(
                "group_access_denied",
                group_id=group_id,
                org_id=expected_org_id,
                user_id=user_id,
                reason="group_not_found_or_org_mismatch"
            )
            raise NotFoundError("Group not found")

        # Verify user is member of the group
        if user_id not in group.member_ids:
            logger.warning(
                "user_not_member_of_group",
                group_id=group_id,
                org_id=expected_org_id,
                user_id=user_id
            )
            raise ForbiddenError("You don't have access to this group")

        return group
