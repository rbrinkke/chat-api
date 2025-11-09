from fastapi import APIRouter, Depends, status, Query
from app.middleware.auth import get_current_user
from app.services.chat_service import ChatService
from app.schemas.message import (
    MessageCreate,
    MessageUpdate,
    MessageResponse,
    MessageListResponse
)
from app.core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.post(
    "/groups/{group_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_message(
    group_id: str,
    message_data: MessageCreate,
    current_user: str = Depends(get_current_user)
):
    """Create a new message in a group."""
    logger.info("api_create_message", group_id=group_id, user_id=current_user)

    chat_service = ChatService()
    message = await chat_service.create_message(
        group_id=group_id,
        sender_id=current_user,
        content=message_data.content
    )

    return MessageResponse(
        id=str(message.id),
        group_id=message.group_id,
        sender_id=message.sender_id,
        content=message.content,
        created_at=message.created_at,
        updated_at=message.updated_at,
        is_deleted=message.is_deleted
    )

@router.get(
    "/groups/{group_id}/messages",
    response_model=MessageListResponse,
    status_code=status.HTTP_200_OK
)
async def get_messages(
    group_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Messages per page"),
    current_user: str = Depends(get_current_user)
):
    """Get paginated message history for a group."""
    logger.info("api_get_messages",
               group_id=group_id,
               user_id=current_user,
               page=page,
               page_size=page_size)

    chat_service = ChatService()
    messages, total = await chat_service.get_messages(
        group_id=group_id,
        user_id=current_user,
        page=page,
        page_size=page_size
    )

    has_more = (page * page_size) < total

    return MessageListResponse(
        messages=[
            MessageResponse(
                id=str(msg.id),
                group_id=msg.group_id,
                sender_id=msg.sender_id,
                content=msg.content,
                created_at=msg.created_at,
                updated_at=msg.updated_at,
                is_deleted=msg.is_deleted
            )
            for msg in messages
        ],
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
async def update_message(
    message_id: str,
    message_data: MessageUpdate,
    current_user: str = Depends(get_current_user)
):
    """Update an existing message (only by sender)."""
    logger.info("api_update_message", message_id=message_id, user_id=current_user)

    chat_service = ChatService()
    message = await chat_service.update_message(
        message_id=message_id,
        user_id=current_user,
        new_content=message_data.content
    )

    return MessageResponse(
        id=str(message.id),
        group_id=message.group_id,
        sender_id=message.sender_id,
        content=message.content,
        created_at=message.created_at,
        updated_at=message.updated_at,
        is_deleted=message.is_deleted
    )

@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_message(
    message_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a message (soft delete, only by sender)."""
    logger.info("api_delete_message", message_id=message_id, user_id=current_user)

    chat_service = ChatService()
    await chat_service.delete_message(
        message_id=message_id,
        user_id=current_user
    )

    return None
