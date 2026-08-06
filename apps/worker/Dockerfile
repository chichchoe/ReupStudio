FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg build-essential curl fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY packages/reup_core /app/packages/reup_core
COPY apps/worker /app/apps/worker

RUN pip install --no-cache-dir -e /app/packages/reup_core \
    && pip install --no-cache-dir -e "/app/apps/worker[ai]"

WORKDIR /app/apps/worker
CMD ["celery", "-A", "src.celery_app", "worker", "-Q", "download,media,gpu,upload", "-l", "info", "--concurrency=2"]
