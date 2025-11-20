from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from typing import List
import bleach


class MessageCreate(BaseModel):
    """Schema for creating a new message."""
    content: str = Field(..., min_length=1, max_length=10000)

    @field_validator('content')
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        """
        Sanitize message content to prevent XSS attacks.

        Strips all HTML/JS tags while preserving text content.
        This is a defense-in-depth measure even if the frontend sanitizes input.
        """
        # Strip all HTML tags - we're a chat API, not a rich text editor
        return bleach.clean(v, tags=[], strip=True).strip()


class MessageUpdate(BaseModel):
    """Schema for updating a message."""
    content: str = Field(..., min_length=1, max_length=10000)

    @field_validator('content')
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        """Sanitize message content to prevent XSS attacks."""
        return bleach.clean(v, tags=[], strip=True).strip()


class MessageResponse(BaseModel):
    """
    Schema for message response.

    Multi-Tenant Architecture:
    - org_id: Organization UUID for client-side filtering
    - conversation_id: Conversation UUID (maps to Auth-API group for RBAC)
    """
    id: str
    org_id: str  # Organization UUID (multi-tenant isolation)
    conversation_id: str  # Conversation UUID (maps to Auth-API group for RBAC)
    sender_id: str
    content: str
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False

    # Pydantic V2 Elegance: Replaces class Config: from_attributes = True
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, message: "Message") -> "MessageResponse":
        """
        Create MessageResponse from Message model.

        This eliminates code duplication in route handlers by providing
        a single, consistent way to convert Message models to responses.
        """
        from app.models.message import Message
        return cls(
            id=str(message.id),
            org_id=message.org_id,
            conversation_id =message.conversation_id,
            sender_id=message.sender_id,
            content=message.content,
            created_at=message.created_at,
            updated_at=message.updated_at,
            is_deleted=message.is_deleted
        )


class MessageListResponse(BaseModel):
    """Schema for paginated message list."""
    messages: List[MessageResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
