from fastapi import APIRouter, Depends, status, Query, Request
from app.services.chat_service import ChatService
from app.core.oauth_validator import require_scope, OAuthToken
from app.schemas.message import (
    MessageCreate,
    MessageUpdate,
    MessageResponse,
    MessageListResponse
)
from app.core.logging_config import get_logger
from app.core.rate_limit import limiter
from app.services.group_service import get_group_service, GroupService

router = APIRouter()
logger = get_logger(__name__)


def get_chat_service(group_service: GroupService = Depends(get_group_service)) -> ChatService:
    return ChatService(group_service=group_service)

@router.post(
    "/groups/{group_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED
)
@limiter.limit("20/minute")  # Prevent message spam
async def create_message(
    request: Request,
    group_id: str,
    message_data: MessageCreate,
    token: OAuthToken = Depends(require_scope("chat:write")),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Create a new message in a group.

    Multi-Tenant Security:
    - Validates group.org_id == token.org_id (via ChatService)
    - Validates user is member of group (via GroupService)
    - Message stored with org_id for tenant isolation

    Requires OAuth scope: chat:write
    """
    logger.info(
        "api_create_message",
        group_id=group_id,
        org_id=token.org_id,
        user_id=token.user_id
    )

    message = await chat_service.create_message(
        group_id=group_id,
        org_id=token.org_id,
        sender_id=token.user_id,
        content=message_data.content
    )

    return message

@router.get(
    "/groups/{group_id}/messages",
    response_model=MessageListResponse,
    status_code=status.HTTP_200_OK
)
async def get_messages(
    group_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Messages per page"),
    token: OAuthToken = Depends(require_scope("chat:read")),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Get paginated message history for a group.

    Multi-Tenant Security:
    - Validates group.org_id == token.org_id (via ChatService)
    - Filters messages by org_id (MongoDB compound index)
    - Only returns messages from user's organization

    Requires OAuth scope: chat:read
    """
    logger.info(
        "api_get_messages",
        group_id=group_id,
        org_id=token.org_id,
        user_id=token.user_id,
        page=page,
        page_size=page_size
    )

    messages, total = await chat_service.get_messages(
        group_id=group_id,
        org_id=token.org_id,
        user_id=token.user_id,
        page=page,
        page_size=page_size
    )

    has_more = (page * page_size) < total

    return MessageListResponse(
        messages=messages,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more
    )

@router.put(
    "/messages/{message_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK
)
@limiter.limit("30/minute")  # Slightly higher than create, as edits are less spammy
async def update_message(
    request: Request,
    message_id: str,
    message_data: MessageUpdate,
    token: OAuthToken = Depends(require_scope("chat:write")),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Update an existing message (only by sender).

    Multi-Tenant Security:
    - Validates message.org_id == token.org_id (via ChatService)
    - Validates message.sender_id == token.user_id (ownership)
    - Prevents cross-org message updates

    Requires OAuth scope: chat:write
    """
    logger.info(
        "api_update_message",
        message_id=message_id,
        org_id=token.org_id,
        user_id=token.user_id
    )

    message = await chat_service.update_message(
        message_id=message_id,
        org_id=token.org_id,
        user_id=token.user_id,
        new_content=message_data.content
    )

    return message

@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
@limiter.limit("30/minute")  # Same as update
async def delete_message(
    request: Request,
    message_id: str,
    token: OAuthToken = Depends(require_scope("chat:write")),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Delete a message (soft delete, only by sender).

    Multi-Tenant Security:
    - Validates message.org_id == token.org_id (via ChatService)
    - Validates message.sender_id == token.user_id (ownership)
    - Prevents cross-org message deletions

    Requires OAuth scope: chat:write
    """
    logger.info(
        "api_delete_message",
        message_id=message_id,
        org_id=token.org_id,
        user_id=token.user_id
    )

    await chat_service.delete_message(
        message_id=message_id,
        org_id=token.org_id,
        user_id=token.user_id
    )

    return None
