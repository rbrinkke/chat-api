from beanie import Document
from pydantic import Field
from datetime import datetime


class Message(Document):
    """
    MongoDB document for chat messages.

    Multi-Tenant Architecture:
    - org_id: Organization UUID for tenant isolation
    - group_id: Group UUID from Auth-API (Single Source of Truth)
    - group_name: Denormalized for performance (avoid Auth-API calls)

    Indexes:
    - Compound (org_id, group_id, created_at): Primary query pattern
    - Single org_id: Org-level analytics
    - Single sender_id: User message history
    """
    # Multi-tenant isolation
    org_id: str = Field(..., description="Organization UUID (tenant boundary)")

    # Group reference (Auth-API is Single Source of Truth)
    group_id: str = Field(..., description="Group UUID from Auth-API")
    group_name: str = Field(..., max_length=100, description="Denormalized group name for performance")

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
            # Supports: WHERE org_id = ? AND group_id = ? ORDER BY created_at DESC
            [("org_id", 1), ("group_id", 1), ("created_at", -1)],

            # Single-field indexes for specific queries
            "org_id",  # Org-level analytics, admin queries
            "sender_id",  # User message history

            # Legacy compound index - KEPT for backwards compatibility during transition
            # Will be removed after full migration to org_id model
            [("group_id", 1), ("is_deleted", 1), ("created_at", -1)],
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "org_id": "660e8400-e29b-41d4-a716-446655440000",
                "group_id": "550e8400-e29b-41d4-a716-446655440000",
                "group_name": "Engineering Team",
                "sender_id": "770e8400-e29b-41d4-a716-446655440000",
                "content": "Hello, world!",
                "is_deleted": False
            }
        }
