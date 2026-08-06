FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY packages/reup_core /app/packages/reup_core
COPY apps/api /app/apps/api

RUN pip install --no-cache-dir -e /app/packages/reup_core \
    && pip install --no-cache-dir -e /app/apps/api

WORKDIR /app/apps/api
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
