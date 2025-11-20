from beanie import Document
from pydantic import Field
from datetime import datetime


class Message(Document):
    """
    MongoDB document for chat messages.

    Multi-Tenant Architecture:
    - org_id: Organization UUID for tenant isolation
    - conversation_id: Conversation UUID (maps to Auth-API group for RBAC)
    - Auth-API is Single Source of Truth for all group/conversation metadata

    Indexes:
    - Compound (org_id, conversation_id, created_at): Primary query pattern
    - Single org_id: Org-level analytics
    - Single sender_id: User message history
    """
    # Multi-tenant isolation
    org_id: str = Field(..., description="Organization UUID (tenant boundary)")

    # Conversation reference (Auth-API is Single Source of Truth)
    conversation_id: str = Field(..., description="Conversation UUID (maps to Auth-API group for RBAC)")

    # Message data
    sender_id: str = Field(..., description="User UUID who sent the message")
    content: str = Field(..., max_length=10000)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Soft delete
    is_deleted: bool = Field(default=False)

    class Settings:
        name = "messages"
        indexes = [
            # Multi-tenant compound index (PRIMARY - used for message queries)
            # Supports: WHERE org_id = ? AND conversation_id = ? ORDER BY created_at DESC
            [("org_id", 1), ("conversation_id", 1), ("created_at", -1)],

            # Single-field indexes for specific queries
            "org_id",  # Org-level analytics, admin queries
            "sender_id",  # User message history

            # Legacy compound index - KEPT for backwards compatibility during transition
            # Will be removed after full migration to org_id model
            [("conversation_id", 1), ("is_deleted", 1), ("created_at", -1)],
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "org_id": "660e8400-e29b-41d4-a716-446655440000",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "sender_id": "770e8400-e29b-41d4-a716-446655440000",
                "content": "Hello, world!",
                "is_deleted": False
            }
        }
