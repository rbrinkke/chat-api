-- ============================================================================
-- RBAC Test Data Setup voor Chat API
-- ============================================================================
-- Dit script maakt een complete testcase aan met:
-- - Organisatie "TestOrg"
-- - 3 gebruikers (admin, user1, user2)
-- - 2 groepen ("vrienden" met chat rechten, "observers" zonder)
-- - Permissie koppelingen
--
-- Gebruik: psql -U postgres -d activitydb -f test_rbac_setup.sql
-- ============================================================================

\echo '════════════════════════════════════════════════════════════'
\echo 'RBAC Test Data Setup - Chat API'
\echo '════════════════════════════════════════════════════════════'
\echo ''

BEGIN;

-- ============================================================================
-- 1. CLEANUP (optioneel - verwijder bestaande test data)
-- ============================================================================
\echo '1. Cleaning up existing test data...'

DELETE FROM activity.user_groups
WHERE group_id IN (
    SELECT id FROM activity.groups
    WHERE name IN ('vrienden', 'observers')
);

DELETE FROM activity.group_permissions
WHERE group_id IN (
    SELECT id FROM activity.groups
    WHERE name IN ('vrienden', 'observers')
);

DELETE FROM activity.groups
WHERE name IN ('vrienden', 'observers');

DELETE FROM activity.organization_members
WHERE organization_id IN (
    SELECT organization_id FROM activity.organizations WHERE slug = 'test-org-chat'
);

DELETE FROM activity.organizations WHERE slug = 'test-org-chat';

-- Delete users by specific UUIDs to avoid conflicts
DELETE FROM activity.users WHERE user_id IN (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
    'ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID,
    'dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID,
    'aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID
);

\echo '✓ Cleanup complete'
\echo ''

-- ============================================================================
-- 2. ORGANISATIE
-- ============================================================================
\echo '2. Creating organization...'

INSERT INTO activity.organizations (organization_id, name, slug, description)
VALUES (
    '99999999-9999-9999-9999-999999999999'::UUID,
    'Chat Test Organization',
    'test-org-chat',
    'Test organization voor Chat API RBAC testing'
);

\echo '✓ Organization created: test-org-chat (99999999-9999-9999-9999-999999999999)'
\echo ''

-- ============================================================================
-- 3. GEBRUIKERS
-- ============================================================================
\echo '3. Creating users...'

-- Admin user
INSERT INTO activity.users (user_id, username, email, password_hash, is_verified)
VALUES (
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
    'chattest_admin',
    'chattest-admin@example.com',
    '$argon2id$v=19$m=65536,t=3,p=4$dummy_hash',  -- Dummy hash
    true
);

-- User 1 (wordt lid van "vrienden" groep)
INSERT INTO activity.users (user_id, username, email, password_hash, is_verified)
VALUES (
    'ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID,
    'chattest_user1',
    'chattest-user1@example.com',
    '$argon2id$v=19$m=65536,t=3,p=4$dummy_hash',
    true
);

-- User 2 (wordt lid van "observers" groep)
INSERT INTO activity.users (user_id, username, email, password_hash, is_verified)
VALUES (
    'dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID,
    'chattest_user2',
    'chattest-user2@example.com',
    '$argon2id$v=19$m=65536,t=3,p=4$dummy_hash',
    true
);

-- User 3 (wordt lid van "moderators" groep - heeft chat:admin)
INSERT INTO activity.users (user_id, username, email, password_hash, is_verified)
VALUES (
    'aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID,
    'chattest_moderator',
    'chattest-moderator@example.com',
    '$argon2id$v=19$m=65536,t=3,p=4$dummy_hash',
    true
);

\echo '✓ Users created:'
\echo '  - chattest-admin@example.com     (eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee)'
\echo '  - chattest-user1@example.com     (ffffffff-ffff-ffff-ffff-ffffffffffff)'
\echo '  - chattest-user2@example.com     (dddddddd-dddd-dddd-dddd-dddddddddddd)'
\echo '  - chattest-moderator@example.com (aaaabbbb-cccc-dddd-eeee-ffffffff1111)'
\echo ''

-- ============================================================================
-- 4. ORGANIZATION MEMBERS
-- ============================================================================
\echo '4. Adding users to organization...'

INSERT INTO activity.organization_members (organization_id, user_id, role)
VALUES
    ('99999999-9999-9999-9999-999999999999'::UUID, 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID, 'admin'),
    ('99999999-9999-9999-9999-999999999999'::UUID, 'ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID, 'member'),
    ('99999999-9999-9999-9999-999999999999'::UUID, 'dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID, 'member'),
    ('99999999-9999-9999-9999-999999999999'::UUID, 'aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID, 'member');

\echo '✓ All users added to organization'
\echo ''

-- ============================================================================
-- 5. GROEPEN
-- ============================================================================
\echo '5. Creating groups...'

-- Groep "vrienden" met chat rechten
INSERT INTO activity.groups (id, organization_id, name, description, created_by)
VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID,
    '99999999-9999-9999-9999-999999999999'::UUID,
    'vrienden',
    'Vrienden groep met chat:read en chat:write rechten',
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID
);

-- Groep "observers" ZONDER chat rechten
INSERT INTO activity.groups (id, organization_id, name, description, created_by)
VALUES (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::UUID,
    '99999999-9999-9999-9999-999999999999'::UUID,
    'observers',
    'Observers groep ZONDER chat rechten (voor negatieve tests)',
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID
);

-- Groep "moderators" met chat:admin rechten
INSERT INTO activity.groups (id, organization_id, name, description, created_by)
VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccccc'::UUID,
    '99999999-9999-9999-9999-999999999999'::UUID,
    'moderators',
    'Moderators groep met chat:admin rechten (kan berichten van anderen verwijderen)',
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID
);

\echo '✓ Groups created:'
\echo '  - vrienden   (aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa) - chat:read, chat:write'
\echo '  - observers  (bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb) - no permissions'
\echo '  - moderators (cccccccc-cccc-cccc-cccc-cccccccccccc) - chat:admin'
\echo ''

-- ============================================================================
-- 6. PERMISSIE KOPPELINGEN
-- ============================================================================
\echo '6. Linking permissions to groups...'

-- Koppel chat:read aan groep "vrienden"
INSERT INTO activity.group_permissions (group_id, permission_id, granted_by)
VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID,
    '79d465c7-35c5-4398-b789-5d340b14fc63'::UUID,  -- chat:read
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID
);

-- Koppel chat:write aan groep "vrienden"
INSERT INTO activity.group_permissions (group_id, permission_id, granted_by)
VALUES (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID,
    'c20bdf24-14be-435f-b14a-091501a4e066'::UUID,  -- chat:write
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID
);

-- Groep "observers" krijgt GEEN permissies (voor negatieve tests)

-- Koppel chat:admin aan groep "moderators"
INSERT INTO activity.group_permissions (group_id, permission_id, granted_by)
VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccccc'::UUID,
    'd607efa1-f06b-456b-8de4-630f4f8c7ce8'::UUID,  -- chat:admin
    'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID
);

\echo '✓ Permissions linked:'
\echo '  - vrienden   → chat:read, chat:write'
\echo '  - observers  → (geen permissies)'
\echo '  - moderators → chat:admin'
\echo ''

-- ============================================================================
-- 7. USER-GROEP KOPPELINGEN
-- ============================================================================
\echo '7. Adding users to groups...'

-- Admin en User1 in groep "vrienden" (MET chat rechten)
INSERT INTO activity.user_groups (user_id, group_id, added_by)
VALUES
    ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID, 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID),
    ('ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID, 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID);

-- User2 in groep "observers" (ZONDER chat rechten)
INSERT INTO activity.user_groups (user_id, group_id, added_by)
VALUES
    ('dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID, 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::UUID, 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID);

-- Moderator in groep "moderators" (MET chat:admin)
INSERT INTO activity.user_groups (user_id, group_id, added_by)
VALUES
    ('aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID, 'cccccccc-cccc-cccc-cccc-cccccccccccc'::UUID, 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID);

\echo '✓ Users added to groups:'
\echo '  - chattest-admin@example.com     → vrienden   (chat:read, chat:write)'
\echo '  - chattest-user1@example.com     → vrienden   (chat:read, chat:write)'
\echo '  - chattest-user2@example.com     → observers  (NO permissions)'
\echo '  - chattest-moderator@example.com → moderators (chat:admin)'
\echo ''

COMMIT;

-- ============================================================================
-- 8. VERIFICATIE TESTS
-- ============================================================================
\echo '════════════════════════════════════════════════════════════'
\echo 'Verification Tests'
\echo '════════════════════════════════════════════════════════════'
\echo ''

\echo 'Test 1: Admin heeft chat:read?'
SELECT
    CASE WHEN activity.sp_user_has_permission(
        'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
        '99999999-9999-9999-9999-999999999999'::UUID,
        'chat', 'read'
    ) THEN '✓ PASS' ELSE '✗ FAIL' END AS result;

\echo ''
\echo 'Test 2: Admin heeft chat:write?'
SELECT
    CASE WHEN activity.sp_user_has_permission(
        'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::UUID,
        '99999999-9999-9999-9999-999999999999'::UUID,
        'chat', 'write'
    ) THEN '✓ PASS' ELSE '✗ FAIL' END AS result;

\echo ''
\echo 'Test 3: User1 heeft chat:read?'
SELECT
    CASE WHEN activity.sp_user_has_permission(
        'ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID,
        '99999999-9999-9999-9999-999999999999'::UUID,
        'chat', 'read'
    ) THEN '✓ PASS' ELSE '✗ FAIL' END AS result;

\echo ''
\echo 'Test 4: User2 heeft chat:read? (verwacht: FALSE)'
SELECT
    CASE WHEN NOT activity.sp_user_has_permission(
        'dddddddd-dddd-dddd-dddd-dddddddddddd'::UUID,
        '99999999-9999-9999-9999-999999999999'::UUID,
        'chat', 'read'
    ) THEN '✓ PASS (correct: geen rechten)' ELSE '✗ FAIL (fout: heeft rechten!)' END AS result;

\echo ''
\echo 'Test 5: Moderator heeft chat:admin?'
SELECT
    CASE WHEN activity.sp_user_has_permission(
        'aaaabbbb-cccc-dddd-eeee-ffffffff1111'::UUID,
        '99999999-9999-9999-9999-999999999999'::UUID,
        'chat', 'admin'
    ) THEN '✓ PASS' ELSE '✗ FAIL' END AS result;

\echo ''
\echo 'Test 6: User1 heeft GEEN chat:admin? (verwacht: FALSE)'
SELECT
    CASE WHEN NOT activity.sp_user_has_permission(
        'ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID,
        '99999999-9999-9999-9999-999999999999'::UUID,
        'chat', 'admin'
    ) THEN '✓ PASS (correct: geen admin rechten)' ELSE '✗ FAIL (fout: heeft admin!)' END AS result;

\echo ''
\echo '════════════════════════════════════════════════════════════'
\echo 'Setup Complete!'
\echo '════════════════════════════════════════════════════════════'
\echo ''
\echo 'Test Data Summary:'
\echo '  Organization: test-org-chat (99999999-9999-9999-9999-999999999999)'
\echo '  Users:'
\echo '    - Admin  (eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee) → vrienden'
\echo '    - User1  (ffffffff-ffff-ffff-ffff-ffffffffffff) → vrienden'
\echo '    - User2  (dddddddd-dddd-dddd-dddd-dddddddddddd) → observers'
\echo '  Groups:'
\echo '    - vrienden  (aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa) → chat:read, chat:write'
\echo '    - observers (bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb) → no permissions'
\echo ''
\echo 'Next steps:'
\echo '  1. Test via Auth API: curl -X POST http://localhost:8000/api/v1/authorization/check'
\echo '  2. Use in Chat API tests'
\echo '  3. Cleanup: Run this script again (has DELETE at start)'
\echo '════════════════════════════════════════════════════════════'
