#!/usr/bin/env bash

uv run isort src/ tests/ && uv run ruff check --fix && uv run ruff format && uv run mypy src/