# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --require-hashes \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy application files
COPY backend/app/ ./backend/app/
COPY backend/alembic/ ./backend/alembic/
COPY backend/alembic.ini ./backend/alembic.ini
COPY agent/ ./agent/

# Create writable runtime directories before dropping privileges.
# Named volumes inherit these directory permissions when first attached.
RUN mkdir -p /app/data/uploads /app/.cache/huggingface \
    && addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser \
    && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=3).read()"]

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
