FROM python:3.11-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /NU-AI-PERSONAL_ASSISTANT

RUN apk add --no-cache gcc musl-dev libmagic

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all directories
COPY backend/ /NU-AI-PERSONAL_ASSISTANT/backend/
COPY frontend/ /NU-AI-PERSONAL_ASSISTANT/frontend/
COPY scripts/ /NU-AI-PERSONAL_ASSISTANT/scripts/

# Set permissions - THIS IS IMPORTANT
RUN chmod -R 755 /NU-AI-PERSONAL_ASSISTANT/frontend/ && \
    chown -R 1000:1000 /NU-AI-PERSONAL_ASSISTANT/frontend/ && \
    ls -la /NU-AI-PERSONAL_ASSISTANT/frontend/  # Verify files

ENV PYTHONPATH=/NU-AI-PERSONAL_ASSISTANT

EXPOSE 8000

# Run as root temporarily for debugging (change to non-root later)
USER root

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]