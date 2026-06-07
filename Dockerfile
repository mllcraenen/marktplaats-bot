FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Create non-root user (use --force-badname and skip if GID/UID already taken)
RUN groupadd --gid 1001 appgroup 2>/dev/null || groupadd appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser 2>/dev/null || \
    useradd --gid appgroup --shell /bin/bash --create-home appuser

# Copy source and project metadata
COPY pyproject.toml ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install Python deps (editable install requires src/ to exist)
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers as root before switching user
RUN playwright install chromium --with-deps

# Data directory (SQLite)
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data

USER appuser

EXPOSE 3002

CMD ["uvicorn", "marktplaats_bot.main:app", "--host", "0.0.0.0", "--port", "3002"]
