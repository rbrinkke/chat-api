# Archived OAuth Documentation

The following files have been **ARCHIVED** because they contain **OUTDATED** information about RS256 + JWKS:

- `ARCHIVE_OAUTH2_MIGRATION.md`
- `ARCHIVE_OAUTH2_TESTING_SUMMARY.md`

## Why Archived?

These documents discuss RS256 (asymmetric signing) and JWKS (JSON Web Key Set) endpoints.

**Auth API uses HS256** (symmetric signing with shared secret), NOT RS256.

This means:
- ❌ No JWKS endpoint exists in Auth API
- ❌ No public/private key pairs
- ❌ No key rotation mechanism needed
- ✅ Simple shared secret between Auth API and resource servers

## Use Instead

For correct, up-to-date OAuth 2.0 integration with HS256:

| File | Description |
|------|-------------|
| `README_OAUTH.md` | Overview and quick reference |
| `OAUTH_QUICK_START.md` | 5-minute setup guide |
| `OAUTH_INTEGRATION_GUIDE.md` | Complete implementation guide |
| `OAUTH_IMPLEMENTATION_STATUS.md` | Current implementation status |
| `app/core/oauth_validator.py` | Production-ready token validator |

## Can These Files Be Deleted?

**Yes**, these archived files can be safely deleted. They were kept for reference only.

If you need RS256 + JWKS in the future, Auth API would need to be modified to:
1. Generate RSA key pairs
2. Expose /.well-known/jwks.json endpoint
3. Switch JWT_ALGORITHM from HS256 to RS256

But for internal microservices, **HS256 is simpler and perfectly secure**.

---

**Date Archived:** 2025-11-12
**Reason:** Misleading - Auth API uses HS256, not RS256
