# Chat API Test Data Setup

Complete RBAC test data voor het testen van Chat API permissions via Auth API.

## Quick Start

```bash
# Load test data into database
docker exec -i activity-postgres-db psql -U postgres -d activitydb < test_rbac_setup.sql
```

## Test Organization

**Organization Details**:
- **ID**: `99999999-9999-9999-9999-999999999999`
- **Name**: `Chat Test Organization`
- **Slug**: `test-org-chat`
- **Description**: Test organization voor Chat API RBAC testing

## Test Users

### 1. Admin User
- **UUID**: `eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee`
- **Username**: `chattest_admin`
- **Email**: `chattest-admin@example.com`
- **Groups**: vrienden
- **Permissions**: `chat:read`, `chat:write`

### 2. Regular User 1
- **UUID**: `ffffffff-ffff-ffff-ffff-ffffffffffff`
- **Username**: `chattest_user1`
- **Email**: `chattest-user1@example.com`
- **Groups**: vrienden
- **Permissions**: `chat:read`, `chat:write`

### 3. Observer User (No Permissions)
- **UUID**: `dddddddd-dddd-dddd-dddd-dddddddddddd`
- **Username**: `chattest_user2`
- **Email**: `chattest-user2@example.com`
- **Groups**: observers
- **Permissions**: NONE (observers group has no permissions)

### 4. Moderator
- **UUID**: `aaaabbbb-cccc-dddd-eeee-ffffffff1111`
- **Username**: `chattest_moderator`
- **Email**: `chattest-moderator@example.com`
- **Groups**: moderators
- **Permissions**: `chat:admin`

## Test Groups

### 1. vrienden (Friends)
- **UUID**: `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`
- **Name**: `vrienden`
- **Description**: Vrienden groep met chat:read en chat:write rechten
- **Permissions**: `chat:read`, `chat:write`
- **Members**: admin, user1

### 2. observers (No Permissions)
- **UUID**: `bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb`
- **Name**: `observers`
- **Description**: Observers groep ZONDER permissions (test voor denial)
- **Permissions**: NONE
- **Members**: user2

### 3. moderators (Admin Rights)
- **UUID**: `cccccccc-cccc-cccc-cccc-cccccccccccc`
- **Name**: `moderators`
- **Description**: Moderators groep met chat:admin rechten (kan berichten van anderen verwijderen)
- **Permissions**: `chat:admin`
- **Members**: moderator

## Permissions

All chat permissions are already in the database:

```sql
-- chat:read (existing)
SELECT id FROM activity.permissions
WHERE resource = 'chat' AND action = 'read';
-- Result: 79d465c7-35c5-4398-b789-5d340b14fc63

-- chat:write (existing)
SELECT id FROM activity.permissions
WHERE resource = 'chat' AND action = 'write';
-- Result: 2d05eb16-3c8e-4f9c-bb45-fd0c7e5a5c14

-- chat:admin (created in test setup)
SELECT id FROM activity.permissions
WHERE resource = 'chat' AND action = 'admin';
-- Result: d607efa1-f06b-456b-8de4-630f4f8c7ce8
```

## Expected Test Results

When you run `test_rbac_setup.sql`, you should see:

```
════════════════════════════════════════════════════════════
RBAC Test Data Setup - Chat API
════════════════════════════════════════════════════════════

✓ Cleanup complete
✓ Organization created: test-org-chat
✓ Users created (4 users)
✓ All users added to organization
✓ Groups created (3 groups)
✓ Permissions linked
✓ Users added to groups

════════════════════════════════════════════════════════════
Verification Tests
════════════════════════════════════════════════════════════

Test 1: Admin heeft chat:read?                    ✓ PASS
Test 2: Admin heeft chat:write?                   ✓ PASS
Test 3: User1 heeft chat:read?                    ✓ PASS
Test 4: User2 heeft chat:read?                    ✓ PASS (correct: geen rechten)
Test 5: Moderator heeft chat:admin?               ✓ PASS
Test 6: User1 heeft GEEN chat:admin?              ✓ PASS (correct: geen admin rechten)

════════════════════════════════════════════════════════════
Setup Complete!
════════════════════════════════════════════════════════════
```

## Testing via Auth API

### Test 1: Admin User (chat:read permission)

```bash
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "permission": "chat:read"
  }'
```

**Expected Response**:
```json
{
  "allowed": true,
  "groups": ["vrienden"],
  "reason": null
}
```

### Test 2: Admin User (chat:write permission)

```bash
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "permission": "chat:write"
  }'
```

**Expected Response**:
```json
{
  "allowed": true,
  "groups": ["vrienden"],
  "reason": null
}
```

### Test 3: User2 (observer - NO permissions)

```bash
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "permission": "chat:read"
  }'
```

**Expected Response**:
```json
{
  "allowed": false,
  "groups": null,
  "reason": "User does not have permission 'chat:read'"
}
```

### Test 4: Moderator (chat:admin permission)

```bash
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "aaaabbbb-cccc-dddd-eeee-ffffffff1111",
    "permission": "chat:admin"
  }'
```

**Expected Response**:
```json
{
  "allowed": true,
  "groups": ["moderators"],
  "reason": null
}
```

### Test 5: User1 tries chat:admin (should FAIL)

```bash
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "permission": "chat:admin"
  }'
```

**Expected Response**:
```json
{
  "allowed": false,
  "groups": null,
  "reason": "User does not have permission 'chat:admin'"
}
```

## Test Matrix

| User | Group | chat:read | chat:write | chat:admin |
|------|-------|-----------|------------|------------|
| Admin | vrienden | ✅ YES | ✅ YES | ❌ NO |
| User1 | vrienden | ✅ YES | ✅ YES | ❌ NO |
| User2 | observers | ❌ NO | ❌ NO | ❌ NO |
| Moderator | moderators | ❌ NO* | ❌ NO* | ✅ YES |

*Note: Moderator only has explicit chat:admin. If you want moderators to also have read/write, add those permissions to the moderators group.

## Cleanup

The test setup script automatically cleans up existing test data before creating new data:

```sql
-- Cleans up:
-- 1. Users (cascades to user_groups, organization_members)
-- 2. Groups (cascades to group_permissions)
-- 3. Organization (if exists)
```

To manually clean up:

```bash
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
DELETE FROM activity.users WHERE user_id IN (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
    'ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID,
    'dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID,
    'aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID
);
DELETE FROM activity.organizations
WHERE organization_id = '99999999-9999-9999-9999-999999999999'::UUID;
"
```

## Database Queries

### View All Test Users
```sql
SELECT
    u.user_id,
    u.username,
    u.email,
    u.is_verified
FROM activity.users u
WHERE u.email LIKE 'chattest-%@example.com'
ORDER BY u.email;
```

### View All Test Groups with Members
```sql
SELECT
    g.name as group_name,
    g.description,
    u.username,
    u.email
FROM activity.groups g
JOIN activity.user_groups ug ON g.id = ug.group_id
JOIN activity.users u ON ug.user_id = u.user_id
WHERE g.organization_id = '99999999-9999-9999-9999-999999999999'::UUID
ORDER BY g.name, u.username;
```

### View Group Permissions
```sql
SELECT
    g.name as group_name,
    p.resource,
    p.action,
    p.description
FROM activity.groups g
JOIN activity.group_permissions gp ON g.id = gp.group_id
JOIN activity.permissions p ON gp.permission_id = p.id
WHERE g.organization_id = '99999999-9999-9999-9999-999999999999'::UUID
ORDER BY g.name, p.resource, p.action;
```

### Test Stored Procedure Directly
```sql
-- Test admin user has chat:read
SELECT activity.sp_user_has_permission(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,  -- user_id
    '99999999-9999-9999-9999-999999999999'::UUID,  -- org_id
    'chat',                                         -- resource
    'read'                                          -- action
);
-- Expected: t (true)

-- Test user2 has chat:read (observers group has NO permissions)
SELECT activity.sp_user_has_permission(
    'dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID,  -- user_id
    '99999999-9999-9999-9999-999999999999'::UUID,  -- org_id
    'chat',                                         -- resource
    'read'                                          -- action
);
-- Expected: f (false)

-- Test moderator has chat:admin
SELECT activity.sp_user_has_permission(
    'aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID,  -- user_id
    '99999999-9999-9999-9999-999999999999'::UUID,  -- org_id
    'chat',                                         -- resource
    'admin'                                         -- action
);
-- Expected: t (true)
```

## Troubleshooting

### Problem: Tests fail with "ROLLBACK"

**Cause**: Database constraint violation or error in SQL script

**Solution**:
```bash
# Check PostgreSQL logs for detailed error
docker logs activity-postgres-db | tail -50

# Common issues:
# 1. Users already exist (run cleanup first)
# 2. Organization already exists
# 3. Foreign key constraint violations
```

### Problem: "User does not have permission" but setup shows PASS

**Cause**: Permissions check via HTTP API might have different result than stored procedure

**Debug**:
```bash
# 1. Check stored procedure directly
docker exec -i activity-postgres-db psql -U postgres -d activitydb -c "
SELECT activity.sp_user_has_permission(
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
    '99999999-9999-9999-9999-999999999999'::UUID,
    'chat', 'read'
);
"

# 2. Check Auth API endpoint
curl -X POST http://localhost:8000/api/v1/authorization/check \
  -H "X-Service-Token: your-service-token" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "99999999-9999-9999-9999-999999999999",
    "user_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "permission": "chat:read"
  }'

# 3. Check Auth API logs
docker logs auth-api | grep permission_check
```

### Problem: "Invalid service token"

**Cause**: X-Service-Token header doesn't match SERVICE_AUTH_TOKEN in Auth API

**Solution**:
```bash
# Check Auth API service token
cat /mnt/d/activity/auth-api/.env | grep SERVICE_AUTH_TOKEN

# Use correct token in curl commands
export SERVICE_TOKEN="<value-from-env>"
```

## Permission Hierarchy

Understanding the permission levels:

```
chat:admin (highest)
    └── Full control
        ├── Delete ANY message (including others)
        ├── Moderate users
        └── All chat:write capabilities
            └── All chat:read capabilities

chat:write (medium)
    └── Create and manage own messages
        ├── Create messages
        ├── Edit own messages
        ├── Delete own messages
        └── All chat:read capabilities

chat:read (lowest)
    └── Read-only access
        └── View messages in authorized groups
```

**Note**: Current test setup does NOT implement permission inheritance. Each permission must be explicitly granted to groups.

## Next Steps

After loading test data:

1. **Verify Auth API** responds correctly to permission checks
2. **Test Chat API integration** (when implemented) with these test users
3. **Test edge cases**:
   - Cross-org access attempts
   - Invalid user/org IDs
   - Malformed permission strings
4. **Performance testing** with permission checks
5. **Add more test users/groups** as needed for specific scenarios

## Related Documentation

- **Authorization Flow**: `AUTHORIZATION.md`
- **Test SQL Script**: `test_rbac_setup.sql`
- **Chat API Docs**: `CLAUDE.md`
- **Auth API Docs**: `../auth-api/CLAUDE.md`
