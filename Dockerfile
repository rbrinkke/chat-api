# Multi-stage Dockerfile for Chat API with optimized logging
#
# Features:
# - All logs to STDOUT/STDERR for Docker log collection
# - Structured JSON logging in production
# - Minimal image size with multi-stage build
# - Non-root user for security
# - Health check support

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Make sure scripts are executable
RUN chmod +x /app/*.sh 2>/dev/null || true

# Switch to non-root user
USER appuser

# Add local Python packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Environment defaults (override with docker-compose or k8s)
ENV ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    LOG_JSON_FORMAT=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

# Production command with proper logging
# --access-log is disabled because we use custom AccessLogMiddleware
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--no-access-log", \
     "--log-config", "logging.yaml"]

# Alternative: Gunicorn for production (with multiple workers)
# CMD ["gunicorn", "app.main:app", \
#      "--workers", "4", \
#      "--worker-class", "uvicorn.workers.UvicornWorker", \
#      "--bind", "0.0.0.0:8001", \
#      "--access-logfile", "-", \
#      "--error-logfile", "-", \
#      "--log-level", "info"]
