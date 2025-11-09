from fastapi import APIRouter, Depends, status, Query, Request
from app.middleware.auth import get_current_user
from app.services.chat_service import ChatService
from app.dependencies import get_chat_service
from app.schemas.message import (
    MessageCreate,
    MessageUpdate,
    MessageResponse,
    MessageListResponse
)
from app.core.logging_config import get_logger
from app.core.rate_limit import limiter

router = APIRouter()
logger = get_logger(__name__)

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
    current_user: str = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Create a new message in a group."""
    logger.info("api_create_message", group_id=group_id, user_id=current_user)

    message = await chat_service.create_message(
        group_id=group_id,
        sender_id=current_user,
        content=message_data.content
    )

    return MessageResponse.from_model(message)

@router.get(
    "/groups/{group_id}/messages",
    response_model=MessageListResponse,
    status_code=status.HTTP_200_OK
)
async def get_messages(
    group_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Messages per page"),
    current_user: str = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Get paginated message history for a group."""
    logger.info("api_get_messages",
               group_id=group_id,
               user_id=current_user,
               page=page,
               page_size=page_size)

    messages, total = await chat_service.get_messages(
        group_id=group_id,
        user_id=current_user,
        page=page,
        page_size=page_size
    )

    has_more = (page * page_size) < total

    return MessageListResponse(
        messages=[MessageResponse.from_model(msg) for msg in messages],
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
    current_user: str = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Update an existing message (only by sender)."""
    logger.info("api_update_message", message_id=message_id, user_id=current_user)

    message = await chat_service.update_message(
        message_id=message_id,
        user_id=current_user,
        new_content=message_data.content
    )

    return MessageResponse.from_model(message)

@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
@limiter.limit("30/minute")  # Same as update
async def delete_message(
    request: Request,
    message_id: str,
    current_user: str = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Delete a message (soft delete, only by sender)."""
    logger.info("api_delete_message", message_id=message_id, user_id=current_user)

    await chat_service.delete_message(
        message_id=message_id,
        user_id=current_user
    )

    return None
