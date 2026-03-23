.PHONY: up down reset migrate demo-a demo-b demo-c demo-plugin logs health test lint

up:
	docker compose up -d

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up -d

migrate:
	docker compose exec backend alembic upgrade head

demo-a:
	cd examples/pattern-a-offline-only && ./run.sh

demo-b:
	cd examples/pattern-b-online-only && ./run.sh

demo-c:
	cd examples/pattern-c-chained && ./run.sh

demo-plugin:
	pip install -e examples/pattern-d-custom-evaluator/my_custom_eval
	cd examples/pattern-d-custom-evaluator && ./run.sh

logs:
	docker compose logs -f

health:
	curl -s http://localhost:8000/health | python3 -m json.tool

test:
	cd backend && pytest tests/ -v --asyncio-mode=auto

lint:
	cd backend && ruff check src/ tests/
	cd frontend && npx tsc --noEmit
