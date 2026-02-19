.PHONY: test lint hassfest hacs

test: lint hassfest hacs

lint:
	docker compose run --rm ruff

hassfest:
	docker compose run --rm hassfest

hacs:
	docker compose run --rm hacs
