#!/usr/bin/env python3
"""
OAuth 2.0 Test Token Generator

Generates RS256-signed JWT tokens for testing the chat-api OAuth2 implementation.

Usage:
    # Generate default test token
    python scripts/generate_test_token.py

    # Generate token with specific permissions
    python scripts/generate_test_token.py --permissions "groups:read,groups:create,messages:send"

    # Generate admin token
    python scripts/generate_test_token.py --role admin --permissions "groups:*,messages:*,admin:*"

    # Generate token with custom claims
    python scripts/generate_test_token.py --user-id user-123 --org-id org-456 --username testuser

NOTE: This script generates tokens for TESTING ONLY.
In production, tokens are issued by the auth-api after proper authentication.

Prerequisites:
    pip install python-jose[cryptography] cryptography
"""

import argparse
import json
from datetime import datetime, timedelta
from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


# ========== RSA Key Generation ==========


def generate_rsa_keypair():
    """
    Generate RS256 RSA key pair for testing.

    In production, keys are managed by Auth-API and rotated regularly.
    """
    print("Generating RSA key pair...")

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Get private key in PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Get public key in PEM format
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem.decode('utf-8'), public_pem.decode('utf-8')


# ========== Token Generation ==========


def generate_test_token(
    user_id: str = "test-user-123",
    org_id: str = "test-org-456",
    username: str = "testuser",
    email: str = "test@example.com",
    permissions: list[str] = None,
    roles: list[str] = None,
    expires_hours: int = 24,
    issuer: str = "http://auth-api:8000",
    audience: str = "chat-api",
    kid: str = "test-key-2024"
):
    """
    Generate RS256-signed JWT token for testing.

    Args:
        user_id: User UUID
        org_id: Organization UUID
        username: Username
        email: Email address
        permissions: List of permissions (e.g., ['groups:read', 'messages:send'])
        roles: List of roles (e.g., ['admin', 'member'])
        expires_hours: Token expiration in hours
        issuer: Token issuer (must match AUTH_API_ISSUER in chat-api config)
        audience: Token audience (must match JWT_AUDIENCE in chat-api config)
        kid: Key ID for JWKS

    Returns:
        Tuple of (token, private_key, public_key)
    """
    # Default permissions if not provided
    if permissions is None:
        permissions = [
            "groups:read",
            "groups:create",
            "messages:send",
            "messages:edit",
            "messages:delete"
        ]

    # Default roles if not provided
    if roles is None:
        roles = ["member"]

    # Generate RSA key pair
    private_key_pem, public_key_pem = generate_rsa_keypair()

    # Build JWT payload
    now = datetime.utcnow()
    payload = {
        # Standard claims
        "iss": issuer,  # Issuer
        "aud": audience,  # Audience
        "sub": user_id,  # Subject (User ID)
        "iat": int(now.timestamp()),  # Issued at
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),  # Expiration

        # Custom claims
        "org_id": org_id,
        "username": username,
        "email": email,
        "permissions": permissions,
        "roles": roles,

        # Metadata
        "token_type": "access",
        "scope": "chat-api"
    }

    # Sign token with RS256
    token = jwt.encode(
        payload,
        private_key_pem,
        algorithm="RS256",
        headers={"kid": kid}
    )

    return token, private_key_pem, public_key_pem, payload


# ========== JWKS Generation ==========


def generate_jwks(public_key_pem: str, kid: str = "test-key-2024"):
    """
    Generate JWKS (JSON Web Key Set) from public key.

    This is what Auth-API would serve at /.well-known/jwks.json
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    import base64

    # Load public key
    public_key = serialization.load_pem_public_key(
        public_key_pem.encode('utf-8'),
        backend=default_backend()
    )

    # Extract RSA public key components
    numbers = public_key.public_numbers()

    # Convert to base64url encoding (JWK format)
    def int_to_base64url(num):
        # Convert int to bytes, then base64url encode
        num_bytes = num.to_bytes((num.bit_length() + 7) // 8, byteorder='big')
        return base64.urlsafe_b64encode(num_bytes).rstrip(b'=').decode('utf-8')

    # Build JWKS
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": int_to_base64url(numbers.n),  # Modulus
                "e": int_to_base64url(numbers.e)   # Exponent
            }
        ]
    }

    return jwks


# ========== CLI ==========


def main():
    parser = argparse.ArgumentParser(
        description="Generate RS256-signed JWT tokens for testing chat-api OAuth2"
    )

    parser.add_argument(
        "--user-id",
        default="test-user-123",
        help="User UUID (default: test-user-123)"
    )

    parser.add_argument(
        "--org-id",
        default="test-org-456",
        help="Organization UUID (default: test-org-456)"
    )

    parser.add_argument(
        "--username",
        default="testuser",
        help="Username (default: testuser)"
    )

    parser.add_argument(
        "--email",
        default="test@example.com",
        help="Email address (default: test@example.com)"
    )

    parser.add_argument(
        "--permissions",
        help="Comma-separated permissions (default: groups:read,groups:create,messages:send)"
    )

    parser.add_argument(
        "--role",
        choices=["member", "admin", "owner"],
        default="member",
        help="User role (default: member)"
    )

    parser.add_argument(
        "--expires-hours",
        type=int,
        default=24,
        help="Token expiration in hours (default: 24)"
    )

    parser.add_argument(
        "--kid",
        default="test-key-2024",
        help="Key ID for JWKS (default: test-key-2024)"
    )

    parser.add_argument(
        "--save-keys",
        action="store_true",
        help="Save private/public keys to files"
    )

    parser.add_argument(
        "--save-jwks",
        action="store_true",
        help="Save JWKS to file (for mock Auth-API)"
    )

    args = parser.parse_args()

    # Parse permissions
    permissions = None
    if args.permissions:
        permissions = [p.strip() for p in args.permissions.split(",")]
    elif args.role == "admin":
        permissions = [
            "groups:*",
            "messages:*",
            "admin:read",
            "admin:manage"
        ]

    # Determine roles
    roles = [args.role]

    # Generate token
    print("\n" + "="*70)
    print("OAuth 2.0 Test Token Generator")
    print("="*70)

    token, private_key, public_key, payload = generate_test_token(
        user_id=args.user_id,
        org_id=args.org_id,
        username=args.username,
        email=args.email,
        permissions=permissions,
        roles=roles,
        expires_hours=args.expires_hours,
        kid=args.kid
    )

    # Print token
    print("\n📝 JWT TOKEN:")
    print("-" * 70)
    print(token)
    print("-" * 70)

    # Print payload
    print("\n📋 TOKEN PAYLOAD:")
    print("-" * 70)
    print(json.dumps(payload, indent=2))
    print("-" * 70)

    # Print usage instructions
    print("\n🚀 USAGE:")
    print("-" * 70)
    print(f"curl -H 'Authorization: Bearer {token[:50]}...' \\")
    print("  http://localhost:8001/api/chat/groups")
    print("-" * 70)

    # Save keys if requested
    if args.save_keys:
        with open("test_private_key.pem", "w") as f:
            f.write(private_key)
        with open("test_public_key.pem", "w") as f:
            f.write(public_key)
        print("\n💾 Keys saved:")
        print("  - test_private_key.pem")
        print("  - test_public_key.pem")

    # Save JWKS if requested
    if args.save_jwks:
        jwks = generate_jwks(public_key, args.kid)
        with open("test_jwks.json", "w") as f:
            json.dump(jwks, f, indent=2)
        print("\n💾 JWKS saved:")
        print("  - test_jwks.json")
        print("\nTo use with chat-api, serve this file at:")
        print("  http://auth-api:8000/.well-known/jwks.json")

    print("\n✅ Done!\n")


if __name__ == "__main__":
    main()
