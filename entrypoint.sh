#!/bin/sh

# Wait for the database to be ready (optional but recommended)
echo "Waiting for PostgreSQL to start..."
while ! nc -z db 5432; do
  sleep 1
done

echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
