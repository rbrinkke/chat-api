"""
Test Data for RBAC Testing

Defines test organizations, users, permissions, and groups used across
all RBAC test suites. Maintains consistency and reduces duplication.
"""

from typing import Dict, List, Any
from dataclasses import dataclass
import pytest


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TestUser:
    """Test user definition"""
    user_id: str
    org_id: str
    username: str
    email: str
    permissions: List[str]
    is_admin: bool = False


@dataclass
class TestOrganization:
    """Test organization definition"""
    org_id: str
    name: str
    users: List[str]  # List of user_ids


@dataclass
class TestGroup:
    """Test chat group definition"""
    conversation_id: str
    name: str
    description: str
    org_id: str
    authorized_user_ids: List[str]


# =============================================================================
# Test Organizations
# =============================================================================

TEST_ORGANIZATIONS = {
    "org-test-1": TestOrganization(
        org_id="org-test-1",
        name="Test Organization 1",
        users=["admin-user-456", "test-user-123", "reader-user-789"]
    ),
    "org-test-2": TestOrganization(
        org_id="org-test-2",
        name="Test Organization 2",
        users=["writer-user-999", "user-888"]
    ),
    "default-org": TestOrganization(
        org_id="default-org",
        name="Default Organization (backward compatibility)",
        users=["legacy-user-888"]
    ),
    "org-load-test": TestOrganization(
        org_id="org-load-test",
        name="Load Testing Organization",
        users=[f"load-test-user-{i}" for i in range(100)]
    )
}


# =============================================================================
# Test Users
# =============================================================================

TEST_USERS = {
    "admin-user-456": TestUser(
        user_id="admin-user-456",
        org_id="org-test-1",
        username="admin",
        email="admin@example.com",
        is_admin=True,
        permissions=[
            "chat:create",
            "chat:read",
            "chat:send_message",
            "chat:delete",
            "chat:manage_members",
            "dashboard:read_metrics"
        ]
    ),
    "test-user-123": TestUser(
        user_id="test-user-123",
        org_id="org-test-1",
        username="testuser",
        email="test@example.com",
        permissions=[
            "chat:read",
            "chat:send_message"
        ]
    ),
    "reader-user-789": TestUser(
        user_id="reader-user-789",
        org_id="org-test-1",
        username="reader",
        email="reader@example.com",
        permissions=[
            "chat:read"
        ]
    ),
    "writer-user-999": TestUser(
        user_id="writer-user-999",
        org_id="org-test-2",
        username="writer",
        email="writer@example.com",
        permissions=[
            "chat:read",
            "chat:send_message",
            "chat:delete"
        ]
    ),
    "user-888": TestUser(
        user_id="user-888",
        org_id="org-test-2",
        username="user888",
        email="user888@example.com",
        permissions=[
            "chat:read",
            "chat:send_message"
        ]
    ),
    "legacy-user-888": TestUser(
        user_id="legacy-user-888",
        org_id="default-org",
        username="legacy",
        email="legacy@example.com",
        permissions=[
            "chat:read",
            "chat:send_message"
        ]
    ),
    # WebSocket test users
    "ws-user-123": TestUser(
        user_id="ws-user-123",
        org_id="org-test-1",
        username="wsuser",
        email="ws@example.com",
        permissions=[
            "chat:read",
            "chat:send_message"
        ]
    ),
    "ws-no-read-456": TestUser(
        user_id="ws-no-read-456",
        org_id="org-test-1",
        username="noreaduser",
        email="noread@example.com",
        permissions=[]  # No permissions!
    )
}


# =============================================================================
# Test Groups
# =============================================================================

TEST_GROUPS = {
    "group-1-org1": TestGroup(
        conversation_id ="group-1-org1",
        name="General (Org 1)",
        description="Main group for org-test-1",
        org_id="org-test-1",
        authorized_user_ids=["admin-user-456", "test-user-123", "reader-user-789"]
    ),
    "group-2-org1": TestGroup(
        conversation_id ="group-2-org1",
        name="Private Group (Org 1)",
        description="Admin-only group",
        org_id="org-test-1",
        authorized_user_ids=["admin-user-456"]  # Admin only
    ),
    "group-1-org2": TestGroup(
        conversation_id ="group-1-org2",
        name="General (Org 2)",
        description="Main group for org-test-2",
        org_id="org-test-2",
        authorized_user_ids=["writer-user-999", "user-888"]
    ),
    "group-ws-test": TestGroup(
        conversation_id ="group-ws-test",
        name="WebSocket Test Group",
        description="Group for WebSocket testing",
        org_id="org-test-1",
        authorized_user_ids=["ws-user-123", "test-user-123"]
    )
}


# =============================================================================
# Permission Definitions
# =============================================================================

CHAT_PERMISSIONS = [
    "chat:create",
    "chat:read",
    "chat:send_message",
    "chat:delete",
    "chat:manage_members"
]

DASHBOARD_PERMISSIONS = [
    "dashboard:read_metrics"
]

ALL_PERMISSIONS = CHAT_PERMISSIONS + DASHBOARD_PERMISSIONS


# =============================================================================
# Test Messages
# =============================================================================

TEST_MESSAGES = [
    {
        "message_id": "msg-1",
        "group_id": "group-1-org1",
        "sender_id": "test-user-123",
        "content": "Hello, world!",
        "is_deleted": False
    },
    {
        "message_id": "msg-2",
        "group_id": "group-1-org1",
        "sender_id": "admin-user-456",
        "content": "Welcome to the group!",
        "is_deleted": False
    },
    {
        "message_id": "msg-3",
        "group_id": "group-1-org2",
        "sender_id": "writer-user-999",
        "content": "Message in org 2",
        "is_deleted": False
    },
    {
        "message_id": "msg-deleted",
        "group_id": "group-1-org1",
        "sender_id": "test-user-123",
        "content": "This was deleted",
        "is_deleted": True
    }
]


# =============================================================================
# Pytest Fixtures
# =============================================================================

@pytest.fixture
def test_organizations():
    """All test organizations"""
    return TEST_ORGANIZATIONS


@pytest.fixture
def test_users():
    """All test users"""
    return TEST_USERS


@pytest.fixture
def test_groups():
    """All test groups"""
    return TEST_GROUPS


@pytest.fixture
def test_messages():
    """All test messages"""
    return TEST_MESSAGES


@pytest.fixture
def org1_users():
    """Users from org-test-1"""
    return {
        user_id: user
        for user_id, user in TEST_USERS.items()
        if user.org_id == "org-test-1"
    }


@pytest.fixture
def org2_users():
    """Users from org-test-2"""
    return {
        user_id: user
        for user_id, user in TEST_USERS.items()
        if user.org_id == "org-test-2"
    }


@pytest.fixture
def admin_users():
    """All admin users"""
    return {
        user_id: user
        for user_id, user in TEST_USERS.items()
        if user.is_admin
    }


@pytest.fixture
def non_admin_users():
    """All non-admin users"""
    return {
        user_id: user
        for user_id, user in TEST_USERS.items()
        if not user.is_admin
    }


# =============================================================================
# Helper Functions
# =============================================================================

def get_user(user_id: str) -> TestUser:
    """Get test user by ID"""
    return TEST_USERS.get(user_id)


def get_org(org_id: str) -> TestOrganization:
    """Get test organization by ID"""
    return TEST_ORGANIZATIONS.get(org_id)


def get_group(conversation_id: str) -> TestGroup:
    """Get test group by ID"""
    return TEST_GROUPS.get(group_id)


def user_has_permission(user_id: str, permission: str) -> bool:
    """Check if test user has specific permission"""
    user = get_user(user_id)
    return user and permission in user.permissions


def user_in_org(user_id: str, org_id: str) -> bool:
    """Check if test user belongs to organization"""
    user = get_user(user_id)
    return user and user.org_id == org_id


def user_in_group(user_id: str, conversation_id: str) -> bool:
    """Check if test user is authorized for group"""
    group = get_group(group_id)
    return group and user_id in group.authorized_user_ids


def get_user_permissions(user_id: str) -> List[str]:
    """Get all permissions for test user"""
    user = get_user(user_id)
    return user.permissions if user else []


def get_org_users(org_id: str) -> Dict[str, TestUser]:
    """Get all users in organization"""
    return {
        user_id: user
        for user_id, user in TEST_USERS.items()
        if user.org_id == org_id
    }


def get_group_users(conversation_id: str) -> List[TestUser]:
    """Get all users authorized for group"""
    group = get_group(group_id)
    if not group:
        return []

    return [
        get_user(user_id)
        for user_id in group.authorized_user_ids
        if get_user(user_id) is not None
    ]


# =============================================================================
# Test Scenario Builders
# =============================================================================

def build_cross_org_test_scenarios():
    """
    Build test scenarios for cross-org access testing

    Returns list of tuples: (user_id, org_id, group_id, should_have_access)
    """
    scenarios = []

    # Org 1 users trying to access org 2 resources
    for user_id in TEST_ORGANIZATIONS["org-test-1"].users:
        scenarios.append((user_id, "org-test-2", "group-1-org2", False))

    # Org 2 users trying to access org 1 resources
    for user_id in TEST_ORGANIZATIONS["org-test-2"].users:
        scenarios.append((user_id, "org-test-1", "group-1-org1", False))

    # Same org access (should work)
    scenarios.append(("test-user-123", "org-test-1", "group-1-org1", True))
    scenarios.append(("writer-user-999", "org-test-2", "group-1-org2", True))

    return scenarios


def build_permission_matrix():
    """
    Build complete permission matrix for all users

    Returns dict: {(user_id, permission): expected_result}
    """
    matrix = {}

    for user_id, user in TEST_USERS.items():
        for permission in ALL_PERMISSIONS:
            has_permission = permission in user.permissions
            matrix[(user_id, permission)] = has_permission

    return matrix


@pytest.fixture
def cross_org_scenarios():
    """Cross-organization access test scenarios"""
    return build_cross_org_test_scenarios()


@pytest.fixture
def permission_matrix():
    """Complete permission matrix for all test users"""
    return build_permission_matrix()


# =============================================================================
# Database Seed Data (for integration tests)
# =============================================================================

async def seed_test_data_to_db(db_client):
    """
    Seed test data to MongoDB for integration tests

    Args:
        db_client: MongoDB client instance
    """
    from app.models.group import Group
    from app.models.message import Message

    # Insert test groups
    for group_id, group_data in TEST_GROUPS.items():
        group = Group(
            name=group_data.name,
            description=group_data.description,
            authorized_user_ids=group_data.authorized_user_ids
        )
        await group.insert()

    # Insert test messages
    for msg_data in TEST_MESSAGES:
        message = Message(
            conversation_id =msg_data["group_id"],
            sender_id=msg_data["sender_id"],
            content=msg_data["content"],
            is_deleted=msg_data["is_deleted"]
        )
        await message.insert()


async def cleanup_test_data_from_db(db_client):
    """
    Clean up test data from MongoDB after integration tests

    Args:
        db_client: MongoDB client instance
    """
    from app.models.group import Group
    from app.models.message import Message

    # Delete all test data
    await Group.delete_all()
    await Message.delete_all()
