FROM python:3.12-slim

WORKDIR /app

# System deps for Telethon / cryptg
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Sessions dir (mounted as volume)
RUN mkdir -p /app/sessions

# Create non-root user with proper permissions
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Install requirements first (as root)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app and set ownership
COPY app/ app/
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
