# RBAC Test Plan - Chat API
## Comprehensive Testing Strategy for Enterprise Authorization

**Version:** 1.0
**Date:** 2025-11-12
**Status:** Ready for Implementation
**Owner:** Engineering Team

---

## Executive Summary

This document outlines a comprehensive testing strategy for the Chat API's Role-Based Access Control (RBAC) system. The RBAC implementation is a **critical security boundary** that protects against unauthorized access. Test failures here could result in security breaches, making this our highest priority testing initiative.

**Testing Philosophy:** Security First → Functionality → Performance → Observability

**Success Criteria:**
- ✅ Zero critical security vulnerabilities
- ✅ >90% code coverage for authorization code
- ✅ <100ms p95 latency for cached permission checks
- ✅ <500ms p99 latency for uncached permission checks
- ✅ All security tests pass with 100% success rate

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Risk Assessment](#risk-assessment)
3. [Test Strategy](#test-strategy)
4. [Phase 1: Security Foundation](#phase-1-security-foundation)
5. [Phase 2: Core Functionality](#phase-2-core-functionality)
6. [Phase 3: Resilience & Performance](#phase-3-resilience--performance)
7. [Test Infrastructure](#test-infrastructure)
8. [Test Execution](#test-execution)
9. [CI/CD Integration](#cicd-integration)
10. [Monitoring & Metrics](#monitoring--metrics)

---

## Architecture Overview

### RBAC Components

```
┌─────────────────────────────────────────────────────────────┐
│                        CHAT API                              │
│                                                              │
│  ┌────────────┐         ┌──────────────────┐               │
│  │   Route    │────────▶│  Authorization   │               │
│  │  Handler   │         │   Dependency     │               │
│  └────────────┘         └─────────┬────────┘               │
│                                    │                         │
│                         ┌──────────▼──────────┐             │
│                         │  Authorization      │             │
│                         │     Service         │             │
│                         │  (Orchestrator)     │             │
│                         └──┬────────────┬─────┘             │
│                            │            │                    │
│                   ┌────────▼──┐    ┌───▼──────────┐        │
│                   │  Redis    │    │ Auth API     │        │
│                   │  Cache    │    │   Client     │        │
│                   │  (Fast)   │    │ (HTTP calls) │        │
│                   └───────────┘    └───┬──────────┘        │
│                                        │                    │
│                                ┌───────▼────────┐          │
│                                │ Circuit Breaker│          │
│                                │ (Resilience)   │          │
│                                └────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                                    │
                            ┌───────▼────────┐
                            │   AUTH API     │
                            │ (Source of     │
                            │   Truth)       │
                            └────────────────┘
```

### Key Security Properties

1. **Fail-Closed by Default**: If Auth API unavailable → deny access
2. **JWT Validation**: Tokens must be valid, unexpired, properly signed
3. **Organization Isolation**: Users can only access their org's resources
4. **Permission Granularity**: Fine-grained permissions (read, write, delete, admin)
5. **Cache Security**: TTLs prevent stale permissions, invalidation on revocation

---

## Risk Assessment

### Critical Risks (🔴 High Impact)

| Risk | Impact | Likelihood | Mitigation | Test Priority |
|------|--------|------------|------------|---------------|
| **Token bypass** | Unauthorized access to all resources | Low | JWT signature validation | 🔴 Critical |
| **Permission escalation** | Users gain admin privileges | Low | Strict permission checks | 🔴 Critical |
| **Cache poisoning** | Malicious permissions cached | Low | Input validation, cache key design | 🔴 Critical |
| **Stale cache after revocation** | Revoked user retains access | Medium | TTL enforcement, invalidation API | 🔴 Critical |
| **Circuit breaker fail-open** | Auth API down → allow all | Low | Fail-closed configuration | 🔴 Critical |

### High Risks (🟡 Moderate Impact)

| Risk | Impact | Likelihood | Mitigation | Test Priority |
|------|--------|------------|------------|---------------|
| **WebSocket long-lived auth** | Revoked user stays connected | Medium | Periodic re-auth, shorter TTL | 🟡 High |
| **Race conditions** | Concurrent checks, inconsistent state | Low | Proper locking, atomic operations | 🟡 High |
| **Auth API timeout** | Slow responses block users | Medium | Circuit breaker, timeouts | 🟡 High |
| **Cache memory exhaustion** | Redis OOM, service degradation | Low | TTL, max keys, monitoring | 🟡 High |

### Medium Risks (🟢 Low Impact)

| Risk | Impact | Likelihood | Mitigation | Test Priority |
|------|--------|------------|------------|---------------|
| **Poor cache hit rate** | High latency, Auth API load | Medium | TTL tuning, pre-warming | 🟢 Medium |
| **Missing observability** | Slow incident response | Medium | Comprehensive logging/metrics | 🟢 Medium |
| **Backward compatibility** | Old tokens break after upgrade | Low | Default org_id fallback | 🟢 Medium |

---

## Test Strategy

### Testing Pyramid

```
                    ┌────────────┐
                    │   E2E      │  ← 10% (Full system, slow)
                    │  (Manual)  │
                ┌───┴────────────┴───┐
                │   Integration      │  ← 30% (Auth API + Redis)
                │   (Automated)      │
            ┌───┴────────────────────┴───┐
            │        Unit Tests          │  ← 60% (Fast, isolated)
            │        (Automated)         │
        ┌───┴────────────────────────────┴───┐
```

### Test Types

1. **Unit Tests** (60%)
   - Individual component testing (cache, circuit breaker, JWT validation)
   - Mocked dependencies (no real Auth API or Redis)
   - Fast execution (<30 seconds total)
   - High coverage target (>90%)

2. **Integration Tests** (30%)
   - Real Auth API interaction via HTTP
   - Real Redis caching behavior
   - Docker Compose test environment
   - Medium execution time (~2 minutes)

3. **Security Tests** (Critical)
   - Penetration testing scenarios
   - Token manipulation attempts
   - Permission bypass attempts
   - Must achieve 100% pass rate

4. **Performance Tests** (10%)
   - Load testing (1000 concurrent users)
   - Latency benchmarks
   - Cache effectiveness measurement
   - Run on staging environment

5. **E2E Tests** (Manual)
   - Complete user workflows
   - Cross-service integration
   - Production-like environment
   - Smoke tests before releases

---

## Phase 1: Security Foundation (Week 1)

**Priority:** 🔴 **CRITICAL**
**Goal:** Verify zero security vulnerabilities in authorization system

### 1.1 JWT Token Validation Tests

**File:** `tests/rbac/security/test_token_validation.py`

#### Test Cases

| Test ID | Scenario | Expected Result | Risk Mitigated |
|---------|----------|-----------------|----------------|
| SEC-001 | Valid token with all claims | 200 OK, access granted | - |
| SEC-002 | Expired token (exp < now) | 401 Unauthorized | Token replay |
| SEC-003 | Token with invalid signature | 401 Unauthorized | Token tampering |
| SEC-004 | Token without `sub` claim | 401 Unauthorized | Missing user ID |
| SEC-005 | Token without `org_id` claim | Warning logged, defaults to "default-org" | Backward compatibility |
| SEC-006 | Token with future `exp` date | Accepted (within reason) | Clock skew |
| SEC-007 | Token with past `iat` date | Accepted if not expired | - |
| SEC-008 | Malformed JWT (not 3 parts) | 401 Unauthorized | Malformed input |
| SEC-009 | Token with SQL injection in claims | Safely handled, no DB impact | Injection attacks |
| SEC-010 | Token with XSS payload in claims | Safely handled, escaped output | XSS attacks |

#### Implementation Example

```python
import pytest
from datetime import datetime, timedelta
from jose import jwt
from app.config import settings

@pytest.mark.security
@pytest.mark.asyncio
async def test_expired_token_rejected(client, jwt_secret):
    """SEC-002: Expired tokens must be rejected"""
    # Create expired token
    payload = {
        "sub": "test-user-123",
        "org_id": "org-456",
        "exp": datetime.utcnow() - timedelta(hours=1)  # Expired 1h ago
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    # Attempt to access protected endpoint
    response = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Verify rejection
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()

@pytest.mark.security
@pytest.mark.asyncio
async def test_tampered_signature_rejected(client, jwt_secret):
    """SEC-003: Tokens with invalid signatures must be rejected"""
    # Create valid token
    payload = {
        "sub": "test-user-123",
        "org_id": "org-456",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    # Tamper with signature (change last char)
    tampered_token = token[:-1] + ("X" if token[-1] != "X" else "Y")

    # Attempt access
    response = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {tampered_token}"}
    )

    # Verify rejection
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()
```

---

### 1.2 Permission Bypass Prevention Tests

**File:** `tests/rbac/security/test_permission_bypass.py`

#### Test Cases

| Test ID | Scenario | Expected Result | Risk Mitigated |
|---------|----------|-----------------|----------------|
| SEC-011 | Access endpoint without token | 401 Unauthorized | Authentication bypass |
| SEC-012 | Access endpoint with insufficient permission | 403 Forbidden | Authorization bypass |
| SEC-013 | Access other org's resources | 403 Forbidden | Org isolation bypass |
| SEC-014 | Direct database access bypass API | N/A (architectural) | Data access bypass |
| SEC-015 | WebSocket without token | Connection rejected | WebSocket auth bypass |
| SEC-016 | WebSocket with invalid token | Connection rejected | WebSocket token bypass |
| SEC-017 | Parameter injection in permission check | Safely handled | Injection bypass |
| SEC-018 | Path traversal in resource access | 404 or 403, no data leak | Path traversal |

#### Implementation Example

```python
@pytest.mark.security
@pytest.mark.asyncio
async def test_no_token_rejected(client):
    """SEC-011: Requests without tokens must be rejected"""
    response = await client.get("/api/chat/groups")
    assert response.status_code == 401
    assert "credentials" in response.json()["detail"].lower()

@pytest.mark.security
@pytest.mark.asyncio
async def test_insufficient_permission_rejected(client, read_only_token):
    """SEC-012: Users without permission cannot access endpoint"""
    # User has chat:read but tries to delete (requires chat:delete)
    response = await client.delete(
        "/api/chat/messages/some-message-id",
        headers={"Authorization": f"Bearer {read_only_token}"}
    )

    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()

@pytest.mark.security
@pytest.mark.asyncio
async def test_cross_org_access_denied(client, org1_token, org2_group_id):
    """SEC-013: Users cannot access other organizations' resources"""
    # org1_token tries to access org2's group
    response = await client.get(
        f"/api/chat/groups/{org2_group_id}",
        headers={"Authorization": f"Bearer {org1_token}"}
    )

    assert response.status_code == 403
    # Should NOT reveal that group exists (info disclosure)
    assert "not found" in response.json()["detail"].lower()
```

---

### 1.3 Circuit Breaker Fail-Closed Tests

**File:** `tests/rbac/security/test_circuit_breaker_security.py`

#### Test Cases

| Test ID | Scenario | Expected Result | Risk Mitigated |
|---------|----------|-----------------|----------------|
| SEC-019 | Circuit breaker OPEN, fail-closed enabled | 503 Service Unavailable | Fail-open vulnerability |
| SEC-020 | Auth API down, no cached permission | 503 Service Unavailable | Unauthorized access |
| SEC-021 | Auth API down, cached permission exists | Access granted from cache | Availability |
| SEC-022 | Circuit breaker config: fail-open=true | Access allowed (degraded) | N/A (config choice) |
| SEC-023 | Rapid auth API failures trigger circuit | Circuit opens after threshold | Cascade failures |

#### Implementation Example

```python
@pytest.mark.security
@pytest.mark.asyncio
async def test_circuit_open_denies_access(client, valid_token, mock_auth_api_down):
    """SEC-019: When circuit breaker opens, access must be denied (fail-closed)"""
    # Simulate Auth API failures to open circuit
    for _ in range(6):  # Exceed threshold of 5
        await client.get(
            "/api/chat/groups",
            headers={"Authorization": f"Bearer {valid_token}"}
        )

    # Circuit should now be OPEN
    response = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {valid_token}"}
    )

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()

    # Verify health endpoint shows degraded state
    health_response = await client.get("/health")
    assert health_response.json()["checks"]["auth_api"] == "degraded"
```

---

### 1.4 Cache Security Tests

**File:** `tests/rbac/security/test_cache_security.py`

#### Test Cases

| Test ID | Scenario | Expected Result | Risk Mitigated |
|---------|----------|-----------------|----------------|
| SEC-024 | Stale cached permission after revocation | Access denied after TTL expires | Stale cache attack |
| SEC-025 | Cache invalidation API called | Permission re-checked immediately | Permission persistence |
| SEC-026 | Malicious cache key injection | Safely handled, no collision | Cache poisoning |
| SEC-027 | Cache TTL for denied permissions | Cached for 2 minutes | Auth API hammering |
| SEC-028 | Cache TTL for admin permissions | 30 seconds (short) | Privilege escalation window |
| SEC-029 | Cache TTL for read permissions | 5 minutes (longer) | Performance/security balance |

#### Implementation Example

```python
@pytest.mark.security
@pytest.mark.asyncio
async def test_cache_invalidation_revokes_access(
    client, valid_token, auth_service, redis_client
):
    """SEC-025: Cache invalidation must immediately revoke access"""
    # First request: permission granted and cached
    response1 = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response1.status_code == 200

    # Verify permission is cached
    cache_key = "auth:permission:org-123:user-456:chat:read"
    cached = await redis_client.get(cache_key)
    assert cached == "true"

    # Invalidate cache (simulating permission revocation)
    await auth_service.invalidate_user_permissions(
        org_id="org-123",
        user_id="user-456"
    )

    # Verify cache cleared
    cached_after = await redis_client.get(cache_key)
    assert cached_after is None

    # Second request: permission re-checked (should fail if revoked)
    response2 = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    # Result depends on Auth API response (testing the flow, not the decision)
```

---

## Phase 2: Core Functionality (Week 2)

**Priority:** 🟡 **HIGH**
**Goal:** Verify RBAC functionality works correctly under normal conditions

### 2.1 Cache Behavior Tests

**File:** `tests/rbac/integration/test_cache_flow.py`

#### Test Cases

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| FUNC-001 | First permission check (cold cache) | Auth API called, result cached |
| FUNC-002 | Second permission check (warm cache) | Cache hit, no Auth API call |
| FUNC-003 | Cache miss after TTL expiry | Auth API called again |
| FUNC-004 | Redis unavailable | Fallback to Auth API (no cache) |
| FUNC-005 | Cache hit rate measurement | >80% hit rate under normal load |
| FUNC-006 | Different permissions cached independently | Separate cache entries |
| FUNC-007 | Cache key format validation | org_id:user_id:permission |

#### Implementation Example

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_hit_avoids_auth_api(
    client, valid_token, auth_api_mock, redis_client
):
    """FUNC-002: Cached permissions should not call Auth API"""
    # First request: cache miss, Auth API called
    auth_api_mock.reset_mock()
    response1 = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response1.status_code == 200
    assert auth_api_mock.call_count == 1

    # Second request: cache hit, no Auth API call
    auth_api_mock.reset_mock()
    response2 = await client.get(
        "/api/chat/groups",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response2.status_code == 200
    assert auth_api_mock.call_count == 0  # Cache hit!
```

---

### 2.2 Auth API Integration Tests

**File:** `tests/rbac/integration/test_auth_api_integration.py`

#### Test Cases

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| FUNC-008 | Auth API returns 200 + allowed | Access granted, 200 OK |
| FUNC-009 | Auth API returns 200 + denied | Access denied, 403 Forbidden |
| FUNC-010 | Auth API returns 404 (permission unknown) | Log warning, deny access |
| FUNC-011 | Auth API returns 500 (error) | Circuit breaker increments, 503 |
| FUNC-012 | Auth API timeout (>3 seconds) | Request fails, circuit breaker |
| FUNC-013 | Auth API returns malformed JSON | Error logged, deny access |
| FUNC-014 | Auth API returns unexpected schema | Error logged, deny access |

---

### 2.3 Circuit Breaker State Machine Tests

**File:** `tests/rbac/unit/test_circuit_breaker.py`

#### Test Cases

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| FUNC-015 | Initial state is CLOSED | Requests pass through |
| FUNC-016 | 4 consecutive failures | State remains CLOSED |
| FUNC-017 | 5 consecutive failures | State transitions to OPEN |
| FUNC-018 | OPEN state, wait timeout | State transitions to HALF_OPEN |
| FUNC-019 | HALF_OPEN, success | State transitions to CLOSED |
| FUNC-020 | HALF_OPEN, failure | State returns to OPEN |
| FUNC-021 | State transitions logged | Observability events emitted |

---

### 2.4 WebSocket Authorization Tests

**File:** `tests/rbac/integration/test_websocket_auth.py`

#### Test Cases

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| FUNC-022 | WebSocket connect with valid token | Connection accepted |
| FUNC-023 | WebSocket connect without token | Connection rejected |
| FUNC-024 | WebSocket connect with expired token | Connection rejected |
| FUNC-025 | WebSocket connect with insufficient permission | Connection rejected |
| FUNC-026 | Long-lived WebSocket (>5 minutes) | Connection remains open (cached) |
| FUNC-027 | WebSocket token query parameter parsing | Token extracted correctly |

#### Implementation Example

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_requires_valid_token(client, valid_token):
    """FUNC-022: WebSocket connections require valid JWT token"""
    async with client.websocket_connect(
        f"/api/chat/ws/group-123?token={valid_token}"
    ) as websocket:
        # Wait for connection message
        data = await websocket.receive_json()
        assert data["type"] == "connected"
        assert data["user_id"] == "test-user-123"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_rejects_invalid_token(client):
    """FUNC-023: WebSocket connections without token are rejected"""
    with pytest.raises(Exception) as exc_info:
        async with client.websocket_connect("/api/chat/ws/group-123"):
            pass

    assert "401" in str(exc_info.value) or "Unauthorized" in str(exc_info.value)
```

---

### 2.5 Multiple Permission Logic Tests

**File:** `tests/rbac/unit/test_permission_logic.py`

#### Test Cases

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| FUNC-028 | require_permission("chat:read") with permission | Access granted |
| FUNC-029 | require_permission("chat:read") without permission | 403 Forbidden |
| FUNC-030 | require_any_permission(["A", "B"]) with A | Access granted |
| FUNC-031 | require_any_permission(["A", "B"]) with B | Access granted |
| FUNC-032 | require_any_permission(["A", "B"]) with neither | 403 Forbidden |
| FUNC-033 | require_all_permissions(["A", "B"]) with both | Access granted |
| FUNC-034 | require_all_permissions(["A", "B"]) with only A | 403 Forbidden |

---

## Phase 3: Resilience & Performance (Week 3)

**Priority:** 🟢 **MEDIUM**
**Goal:** Verify system performs well and degrades gracefully under stress

### 3.1 Load Testing

**Tool:** Locust or k6
**File:** `tests/rbac/performance/locustfile.py`

#### Test Scenarios

| Test ID | Scenario | Target | Success Criteria |
|---------|----------|--------|------------------|
| PERF-001 | 100 concurrent users, cached permissions | <50ms p95 | <100ms p99 |
| PERF-002 | 100 concurrent users, uncached (cold start) | <300ms p95 | <500ms p99 |
| PERF-003 | 1000 concurrent users, mixed cache hits | <100ms p95 | <200ms p99 |
| PERF-004 | Cache hit rate under load | >80% | >90% ideal |
| PERF-005 | Auth API load (requests/sec) | <100 RPS | Caching effective |
| PERF-006 | Redis memory usage | <100 MB | Stable, no leak |

#### Implementation Example

```python
from locust import HttpUser, task, between

class RBACLoadTest(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # Generate valid JWT token
        self.token = generate_test_token()
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(10)  # 10x weight (most common operation)
    def read_groups(self):
        """Test read permission (cached, fast)"""
        self.client.get("/api/chat/groups", headers=self.headers)

    @task(3)
    def read_messages(self):
        """Test read permission on different endpoint"""
        self.client.get(
            "/api/chat/groups/test-group/messages",
            headers=self.headers
        )

    @task(1)
    def send_message(self):
        """Test write permission (shorter TTL)"""
        self.client.post(
            "/api/chat/groups/test-group/messages",
            json={"content": "Test message"},
            headers=self.headers
        )
```

---

### 3.2 Graceful Degradation Tests

**File:** `tests/rbac/resilience/test_graceful_degradation.py`

#### Test Cases

| Test ID | Scenario | Expected Result |
|---------|----------|-----------------|
| RES-001 | Redis down, Auth API up | Direct Auth API calls (slower) |
| RES-002 | Auth API down, Redis has cache | Cached requests succeed |
| RES-003 | Both Redis and Auth API down | 503 Service Unavailable |
| RES-004 | Auth API slow (2 second response) | Requests succeed but slow |
| RES-005 | Auth API timeout (>3 seconds) | Request fails, circuit opens |
| RES-006 | Network partition (intermittent) | Circuit breaker stabilizes |

---

### 3.3 Observability Tests

**File:** `tests/rbac/observability/test_metrics_and_logs.py`

#### Test Cases

| Test ID | Scenario | Expected Metric/Log |
|---------|----------|---------------------|
| OBS-001 | Permission check latency | Metric: `rbac_permission_check_duration_ms` |
| OBS-002 | Cache hit rate | Metric: `rbac_cache_hit_rate` |
| OBS-003 | Circuit breaker state | Metric: `rbac_circuit_breaker_state` |
| OBS-004 | Auth API failures | Metric: `rbac_auth_api_errors_total` |
| OBS-005 | Permission denied | Log: `permission_denied` with correlation_id |
| OBS-006 | Invalid token | Log: `invalid_token` with reason |
| OBS-007 | Cache invalidation | Log: `cache_invalidated` with user_id |

---

## Test Infrastructure

### Directory Structure

```
tests/
├── conftest.py                    # Shared pytest fixtures
├── rbac/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── jwt_tokens.py          # Token generation utilities
│   │   ├── mock_responses.py      # Auth API response mocks
│   │   └── test_data.py           # Test users, orgs, permissions
│   ├── unit/
│   │   ├── test_authorization_service.py
│   │   ├── test_auth_client.py
│   │   ├── test_circuit_breaker.py
│   │   ├── test_dependencies.py
│   │   └── test_permission_logic.py
│   ├── integration/
│   │   ├── test_auth_api_integration.py
│   │   ├── test_cache_flow.py
│   │   ├── test_permission_check_flow.py
│   │   └── test_websocket_auth.py
│   ├── security/
│   │   ├── test_token_validation.py
│   │   ├── test_permission_bypass.py
│   │   ├── test_circuit_breaker_security.py
│   │   └── test_cache_security.py
│   ├── performance/
│   │   ├── locustfile.py
│   │   └── test_benchmarks.py
│   ├── resilience/
│   │   └── test_graceful_degradation.py
│   └── observability/
│       └── test_metrics_and_logs.py
```

### Shared Fixtures

**File:** `tests/rbac/fixtures/jwt_tokens.py`

```python
from datetime import datetime, timedelta
from jose import jwt
import pytest

@pytest.fixture
def jwt_secret():
    """JWT secret for testing (matches config)"""
    return "dev-secret-key-change-in-production"

@pytest.fixture
def valid_token(jwt_secret):
    """Generate valid JWT token with standard claims"""
    payload = {
        "sub": "test-user-123",
        "org_id": "org-test-1",
        "username": "testuser",
        "email": "test@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

@pytest.fixture
def admin_token(jwt_secret):
    """Token for user with admin permissions"""
    payload = {
        "sub": "admin-user-456",
        "org_id": "org-test-1",
        "username": "admin",
        "email": "admin@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

@pytest.fixture
def read_only_token(jwt_secret):
    """Token for user with read-only permissions"""
    payload = {
        "sub": "reader-user-789",
        "org_id": "org-test-1",
        "username": "reader",
        "email": "reader@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

@pytest.fixture
def expired_token(jwt_secret):
    """Token that has already expired"""
    payload = {
        "sub": "test-user-123",
        "org_id": "org-test-1",
        "exp": datetime.utcnow() - timedelta(hours=1)  # Expired
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

@pytest.fixture
def no_org_token(jwt_secret):
    """Token without org_id (backward compatibility test)"""
    payload = {
        "sub": "legacy-user-999",
        "username": "legacy",
        "email": "legacy@example.com",
        "exp": datetime.utcnow() + timedelta(hours=1)
        # Note: no org_id
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

def generate_token(user_id: str, org_id: str, expires_in_hours: int = 1) -> str:
    """Utility function to generate custom tokens in tests"""
    secret = "dev-secret-key-change-in-production"
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "exp": datetime.utcnow() + timedelta(hours=expires_in_hours)
    }
    return jwt.encode(payload, secret, algorithm="HS256")
```

---

## Test Execution

### Running Tests Locally

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
make test-rbac

# Run specific test phases
make test-rbac-security      # Security tests only (critical)
make test-rbac-unit          # Unit tests only (fast)
make test-rbac-integration   # Integration tests (requires Docker)
make test-rbac-performance   # Performance tests (requires staging)

# Run with coverage
make test-rbac-coverage

# Run specific test file
pytest tests/rbac/security/test_token_validation.py -v

# Run specific test
pytest tests/rbac/security/test_token_validation.py::test_expired_token_rejected -v

# Run with markers
pytest -m security      # Security tests only
pytest -m "not slow"    # Exclude slow tests
```

### Makefile Targets

```makefile
# RBAC Test Suite
.PHONY: test-rbac test-rbac-security test-rbac-unit test-rbac-integration

test-rbac:
	pytest tests/rbac/ -v --tb=short

test-rbac-security:
	pytest tests/rbac/security/ -v -m security --tb=short
	@echo "✅ All security tests passed!"

test-rbac-unit:
	pytest tests/rbac/unit/ -v --tb=short

test-rbac-integration:
	docker-compose -f docker-compose.test.yml up -d
	pytest tests/rbac/integration/ -v --tb=short
	docker-compose -f docker-compose.test.yml down

test-rbac-performance:
	locust -f tests/rbac/performance/locustfile.py --headless -u 100 -r 10 -t 60s

test-rbac-coverage:
	pytest tests/rbac/ --cov=app/core/authorization --cov=app/middleware/auth --cov=app/dependencies --cov-report=html --cov-report=term
```

---

## CI/CD Integration

### GitHub Actions Workflow

**File:** `.github/workflows/rbac-tests.yml`

```yaml
name: RBAC Test Suite

on:
  push:
    branches: [main, develop]
    paths:
      - 'app/core/authorization.py'
      - 'app/middleware/auth.py'
      - 'app/dependencies.py'
      - 'tests/rbac/**'
  pull_request:
    branches: [main]

jobs:
  security-tests:
    name: 🔴 Security Tests (Critical)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run security tests
        run: |
          pytest tests/rbac/security/ -v -m security --tb=short

      - name: Security test results
        if: failure()
        run: |
          echo "❌ CRITICAL: Security tests failed!"
          exit 1

  unit-tests:
    name: 🟡 Unit Tests
    runs-on: ubuntu-latest
    needs: security-tests
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run unit tests with coverage
        run: |
          pytest tests/rbac/unit/ -v --cov=app/core/authorization --cov=app/middleware/auth --cov-report=term --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: rbac-unit

  integration-tests:
    name: 🟢 Integration Tests
    runs-on: ubuntu-latest
    needs: unit-tests
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
      mongodb:
        image: mongo:7.0
        ports:
          - 27017:27017

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Start auth-api mock
        run: |
          # Start mock auth-api service for testing
          docker-compose -f docker-compose.test.yml up -d auth-api-mock

      - name: Run integration tests
        run: |
          pytest tests/rbac/integration/ -v --tb=short
        env:
          REDIS_URL: redis://localhost:6379
          MONGODB_URL: mongodb://localhost:27017
          AUTH_API_URL: http://localhost:8080

      - name: Cleanup
        if: always()
        run: |
          docker-compose -f docker-compose.test.yml down
```

### Test Quality Gates

**PR Requirements:**
- ✅ All security tests pass (100% required)
- ✅ Unit test coverage >90% for authorization code
- ✅ Integration tests pass
- ✅ No new security vulnerabilities (Snyk scan)
- ✅ Code review approved by 1+ maintainer

**Deployment Gates:**
- ✅ All tests pass in staging
- ✅ Performance benchmarks meet SLAs
- ✅ Security audit completed
- ✅ Smoke tests pass in production

---

## Monitoring & Metrics

### Key Metrics to Track

#### Authorization Performance
```
rbac_permission_check_duration_seconds{result="allowed|denied|error"}
  - Histogram: latency distribution
  - Target: p95 <100ms (cached), p95 <500ms (uncached)

rbac_cache_hit_rate
  - Gauge: percentage of cache hits
  - Target: >80%

rbac_cache_operations_total{operation="hit|miss|set|delete"}
  - Counter: cache operations
```

#### Auth API Health
```
rbac_auth_api_requests_total{status="success|error|timeout"}
  - Counter: total Auth API requests

rbac_auth_api_duration_seconds
  - Histogram: Auth API response time
  - Target: p95 <300ms

rbac_circuit_breaker_state{state="closed|open|half_open"}
  - Gauge: current circuit breaker state
  - Alert: state=open for >5 minutes
```

#### Security Events
```
rbac_permission_denied_total{permission="chat:read|chat:write|..."}
  - Counter: denied permission checks
  - Alert: spike detection

rbac_invalid_token_total{reason="expired|signature|malformed"}
  - Counter: invalid token attempts
  - Alert: >100/minute = potential attack
```

### Grafana Dashboard

**Panels:**
1. Permission Check Latency (p50, p95, p99)
2. Cache Hit Rate (gauge + trend)
3. Auth API Health (success rate, latency)
4. Circuit Breaker State (timeline)
5. Permission Denials (top permissions, top users)
6. Security Events (invalid tokens, bypasses)

### Alerts

```yaml
# Alert: Circuit Breaker Open
alert: RBACCircuitBreakerOpen
expr: rbac_circuit_breaker_state{state="open"} == 1
for: 5m
labels:
  severity: critical
annotations:
  summary: "RBAC circuit breaker is open - Auth API unavailable"
  description: "Users may be unable to access protected resources"

# Alert: High Permission Denial Rate
alert: RBACHighDenialRate
expr: rate(rbac_permission_denied_total[5m]) > 10
for: 5m
labels:
  severity: warning
annotations:
  summary: "High rate of permission denials"
  description: "Possible misconfiguration or attack attempt"

# Alert: Invalid Token Spike
alert: RBACInvalidTokenSpike
expr: rate(rbac_invalid_token_total[1m]) > 50
for: 2m
labels:
  severity: critical
annotations:
  summary: "Spike in invalid token attempts"
  description: "Possible credential stuffing or brute force attack"
```

---

## Appendix A: Test Data

### Test Organizations

```python
TEST_ORGS = {
    "org-test-1": {
        "name": "Test Organization 1",
        "users": ["admin-user-456", "test-user-123", "reader-user-789"]
    },
    "org-test-2": {
        "name": "Test Organization 2",
        "users": ["writer-user-999"]
    },
    "default-org": {
        "name": "Default Organization (backward compat)",
        "users": ["legacy-user-888"]
    }
}
```

### Test Users and Permissions

```python
TEST_USERS = {
    "admin-user-456": {
        "org_id": "org-test-1",
        "email": "admin@example.com",
        "permissions": [
            "chat:create",
            "chat:read",
            "chat:send_message",
            "chat:delete",
            "chat:manage_members",
            "dashboard:read_metrics"
        ]
    },
    "test-user-123": {
        "org_id": "org-test-1",
        "email": "test@example.com",
        "permissions": [
            "chat:read",
            "chat:send_message"
        ]
    },
    "reader-user-789": {
        "org_id": "org-test-1",
        "email": "reader@example.com",
        "permissions": [
            "chat:read"
        ]
    },
    "writer-user-999": {
        "org_id": "org-test-2",
        "email": "writer@example.com",
        "permissions": [
            "chat:read",
            "chat:send_message",
            "chat:delete"
        ]
    }
}
```

---

## Appendix B: Mock Auth API Responses

```python
# Success: Permission allowed
{
    "allowed": True,
    "org_id": "org-test-1",
    "user_id": "test-user-123",
    "permission": "chat:read",
    "resource": null,
    "ttl": 300
}

# Success: Permission denied
{
    "allowed": False,
    "org_id": "org-test-1",
    "user_id": "test-user-123",
    "permission": "chat:admin",
    "reason": "user_missing_permission",
    "ttl": 120
}

# Error: Permission not found
{
    "detail": "Permission 'invalid:permission' not found",
    "status_code": 404
}

# Error: Internal server error
{
    "detail": "Internal server error",
    "status_code": 500
}
```

---

## Appendix C: Performance Targets

| Metric | Target | Threshold | Action if Exceeded |
|--------|--------|-----------|-------------------|
| Permission check (cached) | <50ms p95 | <100ms p95 | Investigate cache issues |
| Permission check (uncached) | <300ms p95 | <500ms p95 | Optimize Auth API calls |
| Cache hit rate | >80% | >70% | Review TTL configuration |
| Auth API load | <100 RPS | <200 RPS | Increase cache TTL |
| Circuit breaker opens | 0 per day | 3 per day | Investigate Auth API stability |
| Permission denials | <5% of requests | <10% | Review permission configuration |

---

## Summary

This comprehensive test plan ensures the Chat API's RBAC system is:
- ✅ **Secure**: Zero critical vulnerabilities, fail-closed by default
- ✅ **Functional**: All authorization flows work correctly
- ✅ **Resilient**: Graceful degradation under failures
- ✅ **Performant**: <100ms p95 latency for cached permissions
- ✅ **Observable**: Rich metrics and logging for troubleshooting

**Next Steps:**
1. Review and approve test plan with team
2. Implement Phase 1 (Security Foundation) - Week 1
3. Implement Phase 2 (Core Functionality) - Week 2
4. Implement Phase 3 (Resilience & Performance) - Week 3
5. Integrate into CI/CD pipeline
6. Schedule quarterly security audits

**Estimated Effort:** 3 weeks (1 engineer full-time) + ongoing maintenance

---

*Document Version: 1.0*
*Last Updated: 2025-11-12*
*Author: Engineering Team*
*Reviewers: Security Team, DevOps Team*
