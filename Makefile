.PHONY: install backend frontend test dev seed

install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

# Convenience: run both (Ctrl+C stops the script’s children)
dev:
	@echo "Starting API :8000 and Vite :5173 …"
	@cd backend && . .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000 & \
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

test:
	cd backend && . .venv/bin/activate && pytest -q
	cd frontend && npm test -- --run

seed:
	cd backend && . .venv/bin/activate && python scripts/seed_db.py
