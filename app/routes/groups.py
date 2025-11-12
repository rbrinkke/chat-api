from fastapi import APIRouter, Depends, status
from app.services.chat_service import ChatService
from app.dependencies import get_chat_service, require_permission, AuthContext
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
    auth_context: AuthContext = Depends(require_permission("chat:read")),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Get all groups the current user has access to.

    Requires permission: chat:read
    """
    logger.info(
        "api_get_groups",
        user_id=auth_context.user_id,
        org_id=auth_context.org_id
    )

    groups = await chat_service.get_user_groups(auth_context.user_id)

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
    auth_context: AuthContext = Depends(require_permission("chat:read")),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Get a specific group by ID.

    Requires permission: chat:read
    """
    logger.info(
        "api_get_group",
        group_id=group_id,
        user_id=auth_context.user_id,
        org_id=auth_context.org_id
    )

    group = await chat_service.get_group(group_id, auth_context.user_id)

    return GroupResponse(
        id=str(group.id),
        name=group.name,
        description=group.description,
        authorized_user_ids=group.authorized_user_ids,
        created_at=group.created_at
    )
