# Makefile for the AC1 in-memory mock auth backend.
# NOTE: This is an in-memory mock for testing/prototyping only — NOT production auth.

.PHONY: test test-docker build clean help

help:
	@echo "Targets:"
	@echo "  test         Run the pytest suite locally"
	@echo "  test-docker  Run the pytest suite inside Docker"
	@echo "  build        Build the test Docker image"
	@echo "  clean        Remove caches and build artifacts"

test:
	pytest tests/test_ac1_auth.py -v

build:
	docker build -t auth-mock-ac1:test .

test-docker: build
	docker run --rm auth-mock-ac1:test

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__ */*/__pycache__
