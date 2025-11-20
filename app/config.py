from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings."""

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow"  # Allow extra fields from .env
    )

    # Application
    APP_NAME: str = "Chat API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production

    # API
    API_PREFIX: str = "/api/chat"
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "chat_db"

    # Redis (optional - for caching)
    REDIS_URL: str = ""  # Example: "redis://localhost:6379/0"

    # ========== OAuth 2.0 Configuration (HS256 - Shared Secret) ==========
    # JWT Validation - HS256 symmetric signing with Auth API
    JWT_SECRET_KEY: str = "dev_secret_key_change_in_production_min_32_chars_required"  # MUST match Auth API
    JWT_ALGORITHM: str = "HS256"  # Symmetric signing (shared secret)

    # Authorization Server (Auth-API) Settings
    AUTH_API_URL: str = "http://auth-api:8000"
    AUTH_API_ISSUER: str = "http://auth-api:8000"  # Expected 'iss' claim
    AUTH_API_TIMEOUT: float = 3.0  # Timeout for Auth-API HTTP requests (seconds)
    SERVICE_AUTH_TOKEN: str = "your-service-token-change-in-production"  # Service-to-service authentication

    # Service-to-Service OAuth 2.0 (Client Credentials Flow)
    # Used by ChatService to fetch group data from Auth-API
    SERVICE_CLIENT_ID: str = "chat-api-service"
    SERVICE_CLIENT_SECRET: str = "your-service-secret-change-in-production"
    SERVICE_TOKEN_URL: str = "http://auth-api:8000/oauth/token"
    SERVICE_SCOPE: str = "groups:read"  # Required scope for group data access

    # Legacy Settings (Deprecated - Will be removed after full OAuth migration)
    AUTH_API_PERMISSION_CHECK_ENDPOINT: str = "/api/v1/authorization/check"  # DEPRECATED

    # Authorization Cache Settings
    AUTH_CACHE_ENABLED: bool = True
    AUTH_CACHE_TTL_READ: int = 300      # 5 minutes for read operations
    AUTH_CACHE_TTL_WRITE: int = 60      # 1 minute for write operations
    AUTH_CACHE_TTL_ADMIN: int = 30      # 30 seconds for admin operations
    AUTH_CACHE_TTL_DENIED: int = 120    # 2 minutes for denied permissions (negative caching)

    # Circuit Breaker Settings
    CIRCUIT_BREAKER_THRESHOLD: int = 5           # Number of failures before circuit opens
    CIRCUIT_BREAKER_TIMEOUT: int = 30            # Seconds circuit stays open
    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = 3 # Max calls in HALF_OPEN state

    # Fallback Behavior (CRITICAL SECURITY SETTING)
    AUTH_FAIL_OPEN: bool = False  # False = Fail-Closed (secure), True = Fail-Open (dangerous)

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_JSON_FORMAT: bool = False  # Set to True in production for structured logging
    LOG_SQL_QUERIES: bool = False  # Enable SQLAlchemy query logging (verbose!)

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # API Documentation (Swagger UI / OpenAPI)
    ENABLE_DOCS: bool = True
    PROJECT_NAME: str = "Activity Platform - Real-time Chat API"
    API_VERSION: str = "1.0.0"


settings = Settings()
