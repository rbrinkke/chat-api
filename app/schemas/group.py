from pydantic import BaseModel, Field
from datetime import datetime
from typing import List


class GroupCreate(BaseModel):
    """Schema for creating a new group."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    authorized_user_ids: List[str] = Field(default_factory=list)


class GroupUpdate(BaseModel):
    """Schema for updating a group."""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    authorized_user_ids: List[str] | None = None


class GroupResponse(BaseModel):
    """Schema for group response."""
    id: str
    name: str
    description: str
    authorized_user_ids: List[str]
    created_at: datetime

    class Config:
        from_attributes = True


class GroupListResponse(BaseModel):
    """Schema for group list."""
    groups: List[GroupResponse]
    total: int
