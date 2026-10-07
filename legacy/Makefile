.PHONY: test build up down logs
test:
	python -m pytest -q
build:
	docker compose build
up:
	docker compose up -d
down:
	docker compose down
logs:
	docker compose logs -f api worker-image

