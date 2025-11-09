"""
Auth API Mock Server

Production-quality mock server for authentication service.
Provides JWT token generation, user registration, and authentication endpoints.

Features:
- JWT token generation compatible with chat-api validation
- In-memory user storage with seed data
- Password hashing with bcrypt
- Error simulation for testing
- Network delay simulation
- Comprehensive API documentation

Usage:
    python auth_api_mock.py
    # or
    uvicorn auth_api_mock:app --reload --port 8000
"""

import os
import sys
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from mock_utils import (
    generate_jwt_token,
    generate_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    generate_user_id,
    MockUser,
    SeededDataGenerator,
    simulate_network_delay,
    error_simulator,
    random_error_simulator,
    metrics
)

# Load environment variables
load_dotenv()


# ============================================================================
# Configuration
# ============================================================================

class Settings(BaseSettings):
    """Mock server settings."""

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # JWT Configuration (MUST match chat-api settings)
    JWT_SECRET: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24
    JWT_REFRESH_EXPIRY_DAYS: int = 30

    # Mock Behavior
    SIMULATE_DELAYS: bool = True
    MIN_DELAY_MS: int = 50
    MAX_DELAY_MS: int = 200
    ERROR_RATE: float = 0.0  # 0.0 = no random errors, 0.1 = 10% error rate

    # Seed Data
    DEFAULT_PASSWORD: str = "password123"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


# ============================================================================
# Pydantic Models
# ============================================================================

class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password (min 8 characters)")
    name: str = Field(..., min_length=1, max_length=100, description="User full name")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: Dict = Field(..., description="User information")


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str = Field(..., description="Refresh token")


class UserResponse(BaseModel):
    """User information response."""
    id: str
    email: str
    name: str
    created_at: str


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[Dict] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    timestamp: str
    metrics: Optional[Dict] = None


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Auth API Mock Server",
    description="Mock authentication service for chat-api development and testing",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# In-Memory Storage
# ============================================================================

# Thread-safe user storage
users_db: Dict[str, MockUser] = SeededDataGenerator.get_seed_users(settings.DEFAULT_PASSWORD)
users_lock = Lock()


# ============================================================================
# Middleware
# ============================================================================

@app.middleware("http")
async def add_delay_and_metrics(request, call_next):
    """Add simulated network delay and track metrics."""
    # Record request
    metrics.record_request(f"{request.method} {request.url.path}")

    # Simulate network delay
    if settings.SIMULATE_DELAYS:
        await simulate_network_delay(settings.MIN_DELAY_MS, settings.MAX_DELAY_MS)

    # Random error simulation
    try:
        random_error_simulator(settings.ERROR_RATE)
    except HTTPException:
        metrics.record_error()
        raise

    response = await call_next(request)

    # Track errors
    if response.status_code >= 400:
        metrics.record_error()

    return response


# ============================================================================
# Dependency Functions
# ============================================================================

async def get_current_user_from_token(token: str) -> MockUser:
    """
    Extract and validate user from JWT token.

    Args:
        token: JWT token string

    Returns:
        MockUser: Authenticated user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    payload = decode_token(token, settings.JWT_SECRET, settings.JWT_ALGORITHM)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing user ID")

    with users_lock:
        user = users_db.get(user_id)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns service status and metrics.
    """
    return HealthResponse(
        status="healthy",
        service="auth-api-mock",
        timestamp=datetime.utcnow().isoformat(),
        metrics=metrics.get_stats()
    )


@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register(
    user_data: RegisterRequest,
    simulate_error: Optional[int] = Query(None, description="Simulate HTTP error code for testing")
):
    """
    Register a new user.

    **Test Data:**
    ```json
    {
        "email": "newuser@example.com",
        "password": "securepass123",
        "name": "New User"
    }
    ```

    **Error Simulation:**
    - `?simulate_error=409` - Simulate user already exists
    - `?simulate_error=500` - Simulate server error

    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/register \\
      -H "Content-Type: application/json" \\
      -d '{"email":"test@example.com","password":"password123","name":"Test User"}'
    ```
    """
    # Error simulation
    error_simulator(simulate_error)

    with users_lock:
        # Check if user already exists
        existing_user = SeededDataGenerator.get_user_by_email(users_db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists"
            )

        # Create new user
        user_id = generate_user_id()
        hashed_password = hash_password(user_data.password)

        new_user = MockUser(
            id=user_id,
            email=user_data.email,
            name=user_data.name,
            hashed_password=hashed_password
        )

        users_db[user_id] = new_user

    return UserResponse(**new_user.dict())


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(
    credentials: LoginRequest,
    simulate_error: Optional[int] = Query(None, description="Simulate HTTP error code for testing")
):
    """
    Authenticate user and return JWT tokens.

    **Test Credentials:**
    - Email: `alice@example.com`, Password: `password123`
    - Email: `bob@example.com`, Password: `password123`
    - Email: `charlie@example.com`, Password: `password123`
    - Email: `diana@example.com`, Password: `password123`
    - Email: `ethan@example.com`, Password: `password123`

    **Error Simulation:**
    - `?simulate_error=401` - Simulate authentication failure
    - `?simulate_error=500` - Simulate server error

    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/login \\
      -H "Content-Type: application/json" \\
      -d '{"email":"alice@example.com","password":"password123"}'
    ```

    **Response:**
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer",
        "expires_in": 86400,
        "user": {
            "id": "test-user-123",
            "email": "alice@example.com",
            "name": "Alice Johnson",
            "created_at": "2024-01-01T00:00:00"
        }
    }
    ```
    """
    # Error simulation
    error_simulator(simulate_error)

    # Find user by email
    with users_lock:
        user = SeededDataGenerator.get_user_by_email(users_db, credentials.email)

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Generate tokens
    access_token = generate_jwt_token(
        user.id,
        settings.JWT_SECRET,
        settings.JWT_ALGORITHM,
        settings.JWT_EXPIRY_HOURS
    )

    refresh_token = generate_refresh_token(
        user.id,
        settings.JWT_SECRET,
        settings.JWT_ALGORITHM,
        settings.JWT_REFRESH_EXPIRY_DAYS
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRY_HOURS * 3600,
        user=user.dict()
    )


@app.post("/api/auth/refresh", response_model=TokenResponse, tags=["Authentication"])
async def refresh_token(
    request: RefreshTokenRequest,
    simulate_error: Optional[int] = Query(None, description="Simulate HTTP error code for testing")
):
    """
    Refresh access token using refresh token.

    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/auth/refresh \\
      -H "Content-Type: application/json" \\
      -d '{"refresh_token":"YOUR_REFRESH_TOKEN"}'
    ```
    """
    # Error simulation
    error_simulator(simulate_error)

    # Decode refresh token
    payload = decode_token(request.refresh_token, settings.JWT_SECRET, settings.JWT_ALGORITHM)

    # Verify token type
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token."
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID"
        )

    # Get user
    with users_lock:
        user = users_db.get(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Generate new tokens
    new_access_token = generate_jwt_token(
        user.id,
        settings.JWT_SECRET,
        settings.JWT_ALGORITHM,
        settings.JWT_EXPIRY_HOURS
    )

    new_refresh_token = generate_refresh_token(
        user.id,
        settings.JWT_SECRET,
        settings.JWT_ALGORITHM,
        settings.JWT_REFRESH_EXPIRY_DAYS
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRY_HOURS * 3600,
        user=user.dict()
    )


@app.get("/api/auth/me", response_model=UserResponse, tags=["Authentication"])
async def get_current_user(
    authorization: str = Query(..., description="Bearer token", alias="token"),
    simulate_error: Optional[int] = Query(None, description="Simulate HTTP error code for testing")
):
    """
    Get current authenticated user information.

    **Authentication:**
    - Pass JWT token as query parameter: `?token=YOUR_ACCESS_TOKEN`
    - Or use Authorization header: `Authorization: Bearer YOUR_ACCESS_TOKEN`

    **Example:**
    ```bash
    # Using query parameter
    curl http://localhost:8000/api/auth/me?token=YOUR_ACCESS_TOKEN

    # Using header
    curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \\
      http://localhost:8000/api/auth/me
    ```
    """
    # Error simulation
    error_simulator(simulate_error)

    # Extract token
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

    # Get user from token
    user = await get_current_user_from_token(token)

    return UserResponse(**user.dict())


@app.get("/api/auth/users", response_model=List[UserResponse], tags=["Development"])
async def list_users():
    """
    List all registered users (development only).

    This endpoint is for development/testing purposes only.
    Returns all users in the mock database.

    **Example:**
    ```bash
    curl http://localhost:8000/api/auth/users
    ```
    """
    with users_lock:
        user_list = [UserResponse(**user.dict()) for user in users_db.values()]

    return user_list


@app.delete("/api/auth/users/reset", response_model=MessageResponse, tags=["Development"])
async def reset_users():
    """
    Reset user database to seed data (development only).

    This endpoint is for development/testing purposes only.
    Resets the in-memory user database to the original seed data.

    **Example:**
    ```bash
    curl -X DELETE http://localhost:8000/api/auth/users/reset
    ```
    """
    global users_db

    with users_lock:
        users_db = SeededDataGenerator.get_seed_users(settings.DEFAULT_PASSWORD)

    return MessageResponse(
        message="User database reset to seed data",
        details={"user_count": len(users_db)}
    )


@app.get("/api/auth/metrics", response_model=Dict, tags=["Development"])
async def get_metrics():
    """
    Get mock server metrics (development only).

    Returns request counts, error rates, and endpoint statistics.

    **Example:**
    ```bash
    curl http://localhost:8000/api/auth/metrics
    ```
    """
    return metrics.get_stats()


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 80)
    print("🚀 Auth API Mock Server Starting...")
    print("=" * 80)
    print(f"📍 Server: http://{settings.HOST}:{settings.PORT}")
    print(f"📚 Docs: http://{settings.HOST}:{settings.PORT}/docs")
    print(f"🔐 JWT Secret: {settings.JWT_SECRET}")
    print(f"👥 Seed Users: {len(users_db)}")
    print(f"⏱️  Simulate Delays: {settings.SIMULATE_DELAYS}")
    print("=" * 80)
    print("\n🧪 Test Credentials:")
    for user in list(users_db.values())[:3]:
        print(f"   Email: {user.email}, Password: {settings.DEFAULT_PASSWORD}")
    print("\n" + "=" * 80)

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info"
    )
