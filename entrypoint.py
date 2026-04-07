import os
import sys

service_type = os.environ.get("SERVICE_TYPE", "")
port = int(os.environ.get("PORT", 8000))

if service_type == "worker":
    print("=== Starting WORKER ===", flush=True)
    sys.path.insert(0, "/app/backend")
    import worker  # noqa: F401  (runs on import)
else:
    print(f"=== Starting API on port {port} ===", flush=True)
    sys.path.insert(0, "/app/backend")
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=port)
