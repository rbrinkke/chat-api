from fastapi import APIRouter, Depends, status
from app.middleware.auth import get_current_user
from app.services.chat_service import ChatService
from app.schemas.group import GroupResponse, GroupListResponse
from app.core.logging_config import get_logger
from bson import ObjectId

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/groups",
    response_model=GroupListResponse,
    status_code=status.HTTP_200_OK
)
async def get_user_groups(
    current_user: str = Depends(get_current_user)
):
    """Get all groups the current user has access to."""
    logger.info("api_get_groups", user_id=current_user)

    chat_service = ChatService()
    groups = await chat_service.get_user_groups(current_user)

    return GroupListResponse(
        groups=[
            GroupResponse(
                id=str(group.id),
                name=group.name,
                description=group.description,
                authorized_user_ids=group.authorized_user_ids,
                created_at=group.created_at
            )
            for group in groups
        ],
        total=len(groups)
    )


@router.get(
    "/groups/{group_id}",
    response_model=GroupResponse,
    status_code=status.HTTP_200_OK
)
async def get_group(
    group_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get a specific group by ID."""
    logger.info("api_get_group", group_id=group_id, user_id=current_user)

    chat_service = ChatService()
    group = await chat_service.get_group(group_id, current_user)

    return GroupResponse(
        id=str(group.id),
        name=group.name,
        description=group.description,
        authorized_user_ids=group.authorized_user_ids,
        created_at=group.created_at
    )
