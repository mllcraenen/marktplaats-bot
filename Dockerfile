FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Install Python deps first (layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers as root before switching user
RUN playwright install chromium --with-deps

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Data directory (SQLite)
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data

USER appuser

EXPOSE 3002

CMD ["uvicorn", "marktplaats_bot.main:app", "--host", "0.0.0.0", "--port", "3002"]
