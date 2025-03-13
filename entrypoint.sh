#!/bin/sh

# Wait for the database to be ready (optional but recommended)
echo "Waiting for PostgreSQL to start..."
while ! nc -z db 5432; do
  sleep 100
done
echo "PostgreSQL started"
# Check if the .env file exists and is loaded
if [ -f "/app/.env" ]; then
  echo ".env file found"
  # cat /app/.env
else
  echo "WARNING: .env file not found!"
fi
# Disable server header and reload
echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
