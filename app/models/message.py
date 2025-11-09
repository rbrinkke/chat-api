from beanie import Document
from pydantic import Field
from datetime import datetime


class Message(Document):
    """MongoDB document for chat messages."""
    group_id: str = Field(..., description="ID of the group this message belongs to")
    sender_id: str = Field(..., description="ID of the user who sent the message")
    content: str = Field(..., max_length=10000)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(default=False)

    class Settings:
        name = "messages"
        indexes = [
            "group_id",
            "sender_id",
            [("group_id", 1), ("created_at", -1)],  # Compound index for pagination
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "group_id": "group-id-123",
                "sender_id": "user-uuid-1",
                "content": "Hello, world!",
                "is_deleted": False
            }
        }
