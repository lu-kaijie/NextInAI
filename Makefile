.PHONY: install-dev lint test run init-storage

install-dev:
	pip install -e ".[dev]"

lint:
	ruff check src tests

test:
	pytest

run:
	nextinai --help

init-storage:
	nextinai system init-storage
