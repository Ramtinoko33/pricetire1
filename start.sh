#!/bin/bash
if [ "$SERVICE_TYPE" = "worker" ]; then
  echo "=== Starting WORKER ==="
  cd /app/backend && exec python3 worker.py
else
  echo "=== Starting API ==="
  cd /app/backend && exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
fi
