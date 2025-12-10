# Storm Cloud Server - Production Dockerfile
FROM python:3.12-slim
# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL client and development headers
    libpq-dev \
    postgresql-client \
    # Compilation dependencies
    gcc \
    # Healthcheck dependency
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt \
    && pip install --no-cache-dir --root-user-action=ignore gunicorn psycopg2-binary

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p /app/uploads /app/staticfiles /app/logs \
    && chmod -R 755 /app/uploads /app/staticfiles /app/logs

# Copy and set executable permission for entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set production settings module
ENV DJANGO_SETTINGS_MODULE=_core.settings.production

# Expose port
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command (can be overridden)
CMD ["gunicorn", "_core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
