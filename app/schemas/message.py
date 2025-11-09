from pydantic import BaseModel, Field
from datetime import datetime
from typing import List


class MessageCreate(BaseModel):
    """Schema for creating a new message."""
    content: str = Field(..., min_length=1, max_length=10000)


class MessageUpdate(BaseModel):
    """Schema for updating a message."""
    content: str = Field(..., min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: str
    group_id: str
    sender_id: str
    content: str
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Schema for paginated message list."""
    messages: List[MessageResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
