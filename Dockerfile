# Build stage
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    export PATH="/root/.local/bin:$PATH" && \
    uv --version

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Create venv and install dependencies
ENV PATH="/root/.local/bin:$PATH"
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install .

# Runtime stage
FROM python:3.11-slim

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Set working directory
WORKDIR /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Create volume for data persistence
VOLUME /app/data

# Expose ports
EXPOSE 8080

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
