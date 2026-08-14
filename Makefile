.PHONY: help setup up down api worker web migrate revision test fmt clean

help:
	@echo "make setup     - cài dependency (venv + node_modules)"
	@echo "make setup-ai  - cài faster-whisper (nặng, cần cho bước nhận dạng)"
	@echo "make up        - bật postgres + redis"
	@echo "make api       - chạy FastAPI dev"
	@echo "make worker    - chạy Celery worker"
	@echo "make web       - chạy Next.js dev"
	@echo "make migrate   - alembic upgrade head"
	@echo "make test      - chạy pytest"

setup:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e packages/reup_core
	.venv/bin/pip install -e "apps/api[dev]"
	.venv/bin/pip install -e "apps/worker[dev]"
	cd apps/web && npm install
	@echo ""
	@echo "Bước nhận dạng giọng nói cần thêm: make setup-ai"

# Tách riêng vì nặng (ctranslate2 + weight model). Không có bước này thì
# transcribe_video sẽ báo TranscribeError ngay khi chạy.
setup-ai:
	.venv/bin/pip install -e "apps/worker[ai]"

up:
	docker compose up -d postgres redis

down:
	docker compose down

api:
	cd apps/api && ../../.venv/bin/uvicorn src.main:app --reload --port 8000

worker:
	cd apps/worker && ../../.venv/bin/celery -A src.celery_app worker -Q download,media,gpu,upload -l info --concurrency=2

beat:
	cd apps/worker && ../../.venv/bin/celery -A src.celery_app beat -l info

web:
	cd apps/web && npm run dev

migrate:
	cd apps/api && ../../.venv/bin/alembic upgrade head

revision:
	cd apps/api && ../../.venv/bin/alembic revision --autogenerate -m "$(m)"

test:
	cd apps/worker && ../../.venv/bin/pytest
	cd apps/api && ../../.venv/bin/pytest

fmt:
	.venv/bin/ruff format packages apps/api apps/worker
	.venv/bin/ruff check --fix packages apps/api apps/worker

types:
	cd apps/web && npx openapi-typescript http://localhost:8000/openapi.json -o lib/types.gen.ts

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf media/work/* media/out/* 2>/dev/null || true
