FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install --no-cache-dir uv

COPY . .

# Install Python dependencies using uv sync
RUN uv sync --frozen --no-dev --extra disk

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

# Give read and write access to the store_creds volume
RUN mkdir -p /app/store_creds \
    && chown -R app:app /app/store_creds \
    && chmod 755 /app/store_creds

# Normalize line endings (in case of a Windows checkout) and make executable
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Container starts as root so the entrypoint can chown the Fly volume,
# then drops privileges to the app user before running the server.

# Expose port (use default of 8000 if PORT not set)
EXPOSE 8000
# Expose additional port if PORT environment variable is set to a different value
ARG PORT
EXPOSE ${PORT:-8000}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD sh -c 'curl -f http://localhost:${PORT:-8000}/health || exit 1'

# Exec-form entrypoint so `docker run IMAGE --tool-tier core` appends args (see Docker docs).
# entrypoint.sh chowns /data (root-mounted by Fly) then execs the server as the app user.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--tools", "gmail", "drive", "calendar", "--tool-tier", "complete"]