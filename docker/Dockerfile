# Catalyst Trading Bot - Production Docker Image
# ==============================================
# Multi-stage build for smaller final image and better caching

# Stage 1: Build dependencies
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt requirements-trading.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-trading.txt

# Stage 2: Runtime image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user for security
RUN useradd -m -u 1000 catalyst && \
    mkdir -p /app/data/cache /app/data/databases /app/data/logs && \
    chown -R catalyst:catalyst /app

# Copy application code
COPY --chown=catalyst:catalyst . .

# Switch to non-root user
USER catalyst

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/catalyst/.local/bin:${PATH}" \
    DB_DIR=/app/data/databases \
    CACHE_DIR=/app/data/cache \
    LOG_DIR=/app/data/logs

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import catalyst_bot; print('OK')" || exit 1

# Expose port for potential web interface (optional)
EXPOSE 8080

# Default entrypoint: Run the bot in loop mode
ENTRYPOINT ["python", "-m", "catalyst_bot.runner"]
CMD ["--loop", "--sleep-secs", "300"]
