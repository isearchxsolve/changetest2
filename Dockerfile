# Dockerfile for the AC1 in-memory mock auth backend.
# NOTE: This is an in-memory mock for testing/prototyping only — NOT production auth.
# The container's primary purpose is to run the pytest suite in a clean, reproducible
# environment. There is no network, filesystem, or database access at runtime.

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and buffering stdout/stderr.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install test dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and tests.
COPY backend/ ./backend/
COPY tests/ ./tests/
COPY pyproject.toml ./

# Default command: run the full test suite verbosely.
# The in-memory mock requires no services, ports, volumes, or secrets.
CMD ["pytest", "tests/test_ac1_auth.py", "-v"]
