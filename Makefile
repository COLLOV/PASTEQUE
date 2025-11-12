SHELL := /bin/bash

.PHONY: backend-setup backend-dev frontend-setup frontend-dev

backend-setup:
	cd backend && uv sync

backend-dev:
	cd backend && uv run uvicorn insight_backend.main:app --reload

frontend-setup:
	cd frontend && npm i

frontend-dev:
	cd frontend && npm run build -- --mode development && npm run preview
