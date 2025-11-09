from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import List


class Group(Document):
    """MongoDB document for chat groups."""
    name: str = Field(..., max_length=100)
    description: str = Field(default="", max_length=500)
    authorized_user_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "groups"
        indexes = [
            "name",
            "authorized_user_ids",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "name": "General",
                "description": "General discussion group",
                "authorized_user_ids": ["user-uuid-1", "user-uuid-2"]
            }
        }
