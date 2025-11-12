from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings."""

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

    # JWT Authentication
    JWT_SECRET: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    # ========== RBAC Authorization Settings ==========
    # Auth API Integration
    AUTH_API_URL: str = "http://auth-api:8000"
    AUTH_API_TIMEOUT: float = 3.0  # seconds
    AUTH_API_PERMISSION_CHECK_ENDPOINT: str = "/api/v1/authorization/check"

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

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
