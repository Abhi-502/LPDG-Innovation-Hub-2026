FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATA_DIR=/app/data \
    ARTIFACTS_DIR=/app/artifacts

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy source code and scripts
COPY app/ ./app/
COPY main.py validate_submission.py ./
COPY docs/ ./docs/
COPY tests/ ./tests/

# Create artifacts directory
RUN mkdir -p /app/artifacts /app/data

EXPOSE 8000

# Default to running the API server
CMD ["python", "main.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
