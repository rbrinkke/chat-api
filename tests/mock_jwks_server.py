"""
Mock JWKS Server for OAuth2 Testing

Lightweight server that serves a JWKS endpoint for testing JWT validation.
Generates RSA keys on startup and provides both token generation and JWKS endpoint.

Usage:
    python tests/mock_jwks_server.py

Endpoints:
    GET /.well-known/jwks.json - JWKS endpoint
    POST /generate-token - Generate test JWT token
    GET /health - Health check

Example:
    # Start mock server
    python tests/mock_jwks_server.py

    # Generate token
    curl -X POST http://localhost:9000/generate-token \
      -H "Content-Type: application/json" \
      -d '{"user_id": "test-123", "permissions": ["groups:read"]}'

    # Get JWKS
    curl http://localhost:9000/.well-known/jwks.json
"""

import json
import base64
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import uvicorn


# ========== Configuration ==========

KID = "mock-key-2024"
ISSUER = "http://localhost:9000"
AUDIENCE = "chat-api"


# ========== RSA Key Generation ==========

def generate_rsa_keypair():
    """Generate RSA key pair for JWT signing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    # Extract public key numbers for JWKS
    public_numbers = public_key.public_numbers()

    return private_pem, public_pem, public_numbers


def int_to_base64url(value: int) -> str:
    """Convert integer to base64url-encoded string (for JWKS)."""
    value_bytes = value.to_bytes((value.bit_length() + 7) // 8, byteorder='big')
    return base64.urlsafe_b64encode(value_bytes).rstrip(b'=').decode('utf-8')


# ========== Global State ==========

# Generate keys on module load
PRIVATE_KEY, PUBLIC_KEY, PUBLIC_NUMBERS = generate_rsa_keypair()

# Build JWKS
JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "kid": KID,
            "alg": "RS256",
            "n": int_to_base64url(PUBLIC_NUMBERS.n),
            "e": int_to_base64url(PUBLIC_NUMBERS.e)
        }
    ]
}


# ========== FastAPI App ==========

app = FastAPI(
    title="Mock JWKS Server",
    description="OAuth2 JWKS endpoint for testing",
    version="1.0.0"
)


# ========== Models ==========

class TokenRequest(BaseModel):
    """Request body for token generation."""
    user_id: str = "test-user-123"
    org_id: str = "test-org-456"
    permissions: List[str] = ["groups:read", "messages:send"]
    roles: List[str] = ["member"]
    expires_hours: int = 24


class TokenResponse(BaseModel):
    """Response with generated token."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    payload: dict


# ========== Endpoints ==========

@app.get("/.well-known/jwks.json")
async def get_jwks():
    """JWKS endpoint - serves public keys for JWT validation."""
    return JWKS


@app.post("/generate-token", response_model=TokenResponse)
async def generate_token(request: TokenRequest):
    """Generate RS256-signed JWT token for testing."""
    now = datetime.utcnow()
    expires = now + timedelta(hours=request.expires_hours)

    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": request.user_id,
        "org_id": request.org_id,
        "permissions": request.permissions,
        "roles": request.roles,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp())
    }

    token = jwt.encode(
        payload,
        PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": KID}
    )

    return TokenResponse(
        access_token=token,
        expires_in=request.expires_hours * 3600,
        payload=payload
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mock-jwks-server",
        "kid": KID,
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "keys_available": len(JWKS["keys"])
    }


@app.get("/")
async def root():
    """Root endpoint with usage instructions."""
    return {
        "service": "Mock JWKS Server",
        "version": "1.0.0",
        "endpoints": {
            "jwks": "GET /.well-known/jwks.json",
            "generate_token": "POST /generate-token",
            "health": "GET /health"
        },
        "example_token_request": {
            "user_id": "test-user-123",
            "org_id": "test-org-456",
            "permissions": ["groups:read", "messages:send"],
            "roles": ["member"],
            "expires_hours": 24
        }
    }


# ========== Startup Info ==========

@app.on_event("startup")
async def startup_event():
    """Print startup information."""
    print("\n" + "="*60)
    print("🔐 Mock JWKS Server Started")
    print("="*60)
    print(f"\n📍 JWKS Endpoint: http://localhost:9000/.well-known/jwks.json")
    print(f"🎫 Token Generator: POST http://localhost:9000/generate-token")
    print(f"❤️  Health Check: http://localhost:9000/health")
    print(f"\n🔑 Key ID: {KID}")
    print(f"🏢 Issuer: {ISSUER}")
    print(f"🎯 Audience: {AUDIENCE}")
    print("\n" + "="*60)
    print("\n💡 Usage:")
    print("   1. Start Chat API with AUTH_API_JWKS_URL=http://localhost:9000/.well-known/jwks.json")
    print("   2. Generate test token:")
    print('      curl -X POST http://localhost:9000/generate-token \\')
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"user_id": "test-123", "permissions": ["groups:read"]}\'')
    print("   3. Use token with Chat API:")
    print('      curl http://localhost:8001/api/chat/groups \\')
    print('        -H "Authorization: Bearer YOUR_TOKEN"')
    print("\n" + "="*60 + "\n")


# ========== Main ==========

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9000,
        log_level="info"
    )
