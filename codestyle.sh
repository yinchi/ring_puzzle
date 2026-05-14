#!/usr/bin/env bash

echo "Running isort..." && \
uv run isort src/ tests/ && \

echo -e "\n\nRunning ruff check..." && \
uv run ruff check --fix --exit-non-zero-on-fix && \

echo -e "\n\nRunning ruff format..."&& \
uv run ruff format --exit-non-zero-on-format && \

echo -e "\n\nRunning mypy..." && \
uv run mypy src/ && \

echo -e "\n\nRunning biome check..." && \
bunx --bun @biomejs/biome check --write --error-on-warnings web/
