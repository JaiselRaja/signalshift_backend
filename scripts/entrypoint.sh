#!/bin/sh
set -e

echo "Running database migrations..."
python -m alembic upgrade head
echo "Migrations complete."

echo "Seeding default data..."
python scripts/seed.py
echo "Seed complete."

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
