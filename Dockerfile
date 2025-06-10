# Dockerfile for Pump Bot Worker
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ca-certificates \
    libffi-dev \
    libssl-dev \
    pkg-config \
    libsodium-dev \
    python3-dev \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 pumpbot && \
    mkdir -p /app/logs /app/wallets /app/config && \
    chown -R pumpbot:pumpbot /app

# Copy pyproject.toml and README.md first for better caching
COPY pyproject.toml README.md ./

# Install uv for faster dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install Python dependencies using uv with pyproject.toml
RUN /root/.local/bin/uv pip install --system .

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY .env.example .env

# Set permissions
RUN chmod -R 755 /app/src /app/scripts && \
    chown -R pumpbot:pumpbot /app

# Switch to non-root user
USER pumpbot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8081/health', timeout=5)" || exit 1

# Expose metrics port
EXPOSE 8081

# Environment variables that can be overridden
ENV LOG_LEVEL=INFO
ENV METRICS_ENABLED=true
ENV METRICS_PORT=8081

# Start command
CMD ["python", "-m", "src.worker_app"]
