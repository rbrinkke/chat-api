"""
Mock Auth API Response Fixtures

Provides standardized mock responses for Auth API permission check endpoint.
Used for unit and integration testing without requiring real Auth API.
"""

from typing import Dict, Any, Optional
import pytest


# =============================================================================
# Response Templates
# =============================================================================

def permission_allowed_response(
    org_id: str,
    user_id: str,
    permission: str,
    resource: Optional[str] = None,
    ttl: int = 300
) -> Dict[str, Any]:
    """
    Generate Auth API response for allowed permission

    Args:
        org_id: Organization ID
        user_id: User ID
        permission: Permission name (e.g., "chat:read")
        resource: Optional resource identifier
        ttl: Cache TTL in seconds

    Returns:
        Mock response dictionary
    """
    return {
        "allowed": True,
        "org_id": org_id,
        "user_id": user_id,
        "permission": permission,
        "resource": resource,
        "ttl": ttl,
        "reason": None
    }


def permission_denied_response(
    org_id: str,
    user_id: str,
    permission: str,
    reason: str = "user_missing_permission",
    ttl: int = 120
) -> Dict[str, Any]:
    """
    Generate Auth API response for denied permission

    Args:
        org_id: Organization ID
        user_id: User ID
        permission: Permission name
        reason: Denial reason
        ttl: Cache TTL for denied permissions

    Returns:
        Mock response dictionary
    """
    return {
        "allowed": False,
        "org_id": org_id,
        "user_id": user_id,
        "permission": permission,
        "resource": None,
        "ttl": ttl,
        "reason": reason
    }


# =============================================================================
# Standard Permission Responses
# =============================================================================

@pytest.fixture
def mock_permission_responses():
    """
    Standard mock responses for different users and permissions

    Mimics Auth API behavior based on test user permissions
    """
    return {
        # Admin user (admin-user-456) - ALL permissions allowed
        ("org-test-1", "admin-user-456", "chat:create"): permission_allowed_response(
            "org-test-1", "admin-user-456", "chat:create", ttl=60
        ),
        ("org-test-1", "admin-user-456", "chat:read"): permission_allowed_response(
            "org-test-1", "admin-user-456", "chat:read", ttl=300
        ),
        ("org-test-1", "admin-user-456", "chat:send_message"): permission_allowed_response(
            "org-test-1", "admin-user-456", "chat:send_message", ttl=60
        ),
        ("org-test-1", "admin-user-456", "chat:delete"): permission_allowed_response(
            "org-test-1", "admin-user-456", "chat:delete", ttl=60
        ),
        ("org-test-1", "admin-user-456", "chat:manage_members"): permission_allowed_response(
            "org-test-1", "admin-user-456", "chat:manage_members", ttl=30
        ),
        ("org-test-1", "admin-user-456", "dashboard:read_metrics"): permission_allowed_response(
            "org-test-1", "admin-user-456", "dashboard:read_metrics", ttl=300
        ),

        # Standard user (test-user-123) - chat:read + chat:send_message
        ("org-test-1", "test-user-123", "chat:read"): permission_allowed_response(
            "org-test-1", "test-user-123", "chat:read", ttl=300
        ),
        ("org-test-1", "test-user-123", "chat:send_message"): permission_allowed_response(
            "org-test-1", "test-user-123", "chat:send_message", ttl=60
        ),
        ("org-test-1", "test-user-123", "chat:create"): permission_denied_response(
            "org-test-1", "test-user-123", "chat:create"
        ),
        ("org-test-1", "test-user-123", "chat:delete"): permission_denied_response(
            "org-test-1", "test-user-123", "chat:delete"
        ),
        ("org-test-1", "test-user-123", "chat:manage_members"): permission_denied_response(
            "org-test-1", "test-user-123", "chat:manage_members"
        ),

        # Read-only user (reader-user-789) - chat:read ONLY
        ("org-test-1", "reader-user-789", "chat:read"): permission_allowed_response(
            "org-test-1", "reader-user-789", "chat:read", ttl=300
        ),
        ("org-test-1", "reader-user-789", "chat:send_message"): permission_denied_response(
            "org-test-1", "reader-user-789", "chat:send_message"
        ),
        ("org-test-1", "reader-user-789", "chat:delete"): permission_denied_response(
            "org-test-1", "reader-user-789", "chat:delete"
        ),

        # Writer user in different org (writer-user-999, org-test-2)
        ("org-test-2", "writer-user-999", "chat:read"): permission_allowed_response(
            "org-test-2", "writer-user-999", "chat:read", ttl=300
        ),
        ("org-test-2", "writer-user-999", "chat:send_message"): permission_allowed_response(
            "org-test-2", "writer-user-999", "chat:send_message", ttl=60
        ),
        ("org-test-2", "writer-user-999", "chat:delete"): permission_allowed_response(
            "org-test-2", "writer-user-999", "chat:delete", ttl=60
        ),

        # Cross-org access (should all be denied)
        ("org-test-2", "test-user-123", "chat:read"): permission_denied_response(
            "org-test-2", "test-user-123", "chat:read",
            reason="user_not_in_organization"
        ),
        ("org-test-1", "writer-user-999", "chat:read"): permission_denied_response(
            "org-test-1", "writer-user-999", "chat:read",
            reason="user_not_in_organization"
        ),

        # Legacy user with default-org
        ("default-org", "legacy-user-888", "chat:read"): permission_allowed_response(
            "default-org", "legacy-user-888", "chat:read", ttl=300
        ),
    }


# =============================================================================
# Error Responses
# =============================================================================

@pytest.fixture
def mock_auth_api_error_responses():
    """Mock responses for Auth API error scenarios"""
    return {
        "permission_not_found": {
            "detail": "Permission 'invalid:permission' not found",
            "status_code": 404
        },
        "internal_server_error": {
            "detail": "Internal server error",
            "status_code": 500
        },
        "service_unavailable": {
            "detail": "Service temporarily unavailable",
            "status_code": 503
        },
        "bad_request": {
            "detail": "Invalid request parameters",
            "status_code": 400
        },
        "unprocessable_entity": {
            "detail": "Validation error",
            "status_code": 422,
            "errors": [
                {
                    "field": "org_id",
                    "message": "Organization ID is required"
                }
            ]
        },
        "timeout": {
            "error": "Request timeout",
            "status_code": 504
        }
    }


# =============================================================================
# Malformed Response Scenarios
# =============================================================================

@pytest.fixture
def mock_malformed_responses():
    """Mock malformed/unexpected Auth API responses"""
    return {
        "missing_allowed_field": {
            # Missing 'allowed' field (required)
            "org_id": "org-test-1",
            "user_id": "test-user-123",
            "permission": "chat:read"
        },
        "wrong_type_allowed": {
            # 'allowed' should be boolean, not string
            "allowed": "true",  # Wrong type!
            "org_id": "org-test-1",
            "user_id": "test-user-123",
            "permission": "chat:read"
        },
        "null_values": {
            "allowed": None,  # Null instead of boolean
            "org_id": None,
            "user_id": None,
            "permission": None
        },
        "extra_unexpected_fields": {
            "allowed": True,
            "org_id": "org-test-1",
            "user_id": "test-user-123",
            "permission": "chat:read",
            "unexpected_field": "should_be_ignored",
            "another_field": 12345
        },
        "empty_response": {},
        "non_json_response": "This is not JSON",
        "html_error_page": "<html><body>500 Error</body></html>"
    }


# =============================================================================
# Circuit Breaker Test Responses
# =============================================================================

@pytest.fixture
def mock_circuit_breaker_responses():
    """Mock responses for circuit breaker testing"""
    return {
        "success_sequence": [
            permission_allowed_response("org-test-1", "cb-user-1", "chat:read")
            for _ in range(10)
        ],
        "failure_sequence": [
            {"detail": "Internal server error", "status_code": 500}
            for _ in range(10)
        ],
        "mixed_sequence": [
            permission_allowed_response("org-test-1", "cb-user-1", "chat:read"),
            permission_allowed_response("org-test-1", "cb-user-1", "chat:read"),
            {"detail": "Internal server error", "status_code": 500},
            {"detail": "Internal server error", "status_code": 500},
            permission_allowed_response("org-test-1", "cb-user-1", "chat:read"),
            {"detail": "Internal server error", "status_code": 500},
            {"detail": "Internal server error", "status_code": 500},
            {"detail": "Internal server error", "status_code": 500},
        ],
        "recovery_sequence": [
            # Failures to open circuit
            *[{"detail": "Internal server error", "status_code": 500} for _ in range(6)],
            # Successes for recovery
            *[permission_allowed_response("org-test-1", "cb-user-1", "chat:read") for _ in range(5)]
        ]
    }


# =============================================================================
# Performance Test Responses
# =============================================================================

def generate_bulk_allowed_responses(count: int, org_id: str = "org-load-test") -> list:
    """Generate many allowed responses for load testing"""
    return [
        permission_allowed_response(
            org_id=org_id,
            user_id=f"load-test-user-{i}",
            permission="chat:read",
            ttl=300
        )
        for i in range(count)
    ]


@pytest.fixture
def mock_load_test_responses():
    """Generate responses for load testing"""
    return generate_bulk_allowed_responses(1000)


# =============================================================================
# Helper Functions
# =============================================================================

def get_mock_response(
    org_id: str,
    user_id: str,
    permission: str,
    responses_dict: Dict
) -> Optional[Dict[str, Any]]:
    """
    Lookup mock response for given parameters

    Args:
        org_id: Organization ID
        user_id: User ID
        permission: Permission name
        responses_dict: Dictionary of mock responses

    Returns:
        Mock response or None if not found
    """
    key = (org_id, user_id, permission)
    return responses_dict.get(key)


def is_permission_allowed(response: Dict[str, Any]) -> bool:
    """
    Check if mock response indicates allowed permission

    Args:
        response: Mock Auth API response

    Returns:
        True if permission allowed, False otherwise
    """
    return response.get("allowed", False) is True


# =============================================================================
# Request Matchers for pytest-mock / responses library
# =============================================================================

def match_permission_check_request(expected_org: str, expected_user: str, expected_permission: str):
    """
    Create a request matcher for permission check requests

    Usage with responses library:
        responses.add(
            responses.POST,
            "http://auth-api:8000/api/v1/authorization/check",
            json=permission_allowed_response(...),
            match=[match_permission_check_request("org-1", "user-1", "chat:read")]
        )
    """
    def matcher(request_obj):
        import json
        try:
            body = json.loads(request_obj.body)
            return (
                body.get("org_id") == expected_org and
                body.get("user_id") == expected_user and
                body.get("permission") == expected_permission
            )
        except Exception:
            return False

    return matcher
