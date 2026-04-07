#!/bin/bash
if [ "$SERVICE_TYPE" = "worker" ]; then
  echo "=== Starting WORKER ==="
  exec python3 backend/worker.py
else
  echo "=== Starting API ==="
  exec uvicorn backend.server:app --host 0.0.0.0 --port ${PORT:-8000}
fi
