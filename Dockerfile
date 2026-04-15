FROM python:3.11-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache gcc musl-dev libmagic

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/

# Set proper permissions (use root for Alpine)
RUN chmod -R 755 ./frontend/ && \
    ls -la ./frontend/  # Verify files

# Expose port (match EB expectations)
EXPOSE 8080

# Run as root (Alpine compatibility) - change to non-root user after testing
# USER 1000:1000  # Uncomment after confirming it works as root first

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
