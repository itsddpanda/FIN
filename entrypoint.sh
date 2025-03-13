#!/bin/sh

LOG_FILE="/app/app.log"

# Load environment variables from .env if it exists
if [ -f "/app/.env" ]; then
  echo ".env file found, loading variables..."
  export $(grep -v '^#' /app/.env | xargs)
else
  echo "WARNING: .env file not found!"
fi

# Wait for the database to be ready
echo "Waiting for PostgreSQL to start..."
while ! nc -z db 5432; do
  sleep 20
done
echo "PostgreSQL started"

# Check the value of CHECK from .env
if [ "$CHECK" = "true" ]; then
  echo "CHECK is set to true, executing additional command..."
  # Replace with your actual command
  exec rm -rf ./alembic/versions/*.py
else
  echo "CHECK is not true or not set, skipping additional command."
fi

if [ -f "$LOG_FILE" ]; then
    rm "$LOG_FILE"
    echo "app.log removed."
else
    echo "app.log not found, skipping..."
fi

# Disable server header and start FastAPI
echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
