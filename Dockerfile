# ==============================================================================
# Dockerfile — Computer Networks Simple Chat TCP Server (R1, R2, B2)
# Server-only container for local Docker Desktop simulation & Cloud VPS deploy
# ==============================================================================
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr so logs appear immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only shared protocol definitions and server modules (zero pip dependencies needed)
COPY common/ ./common/
COPY server/ ./server/

# Expose raw TCP socket port for client connections
EXPOSE 5000/tcp

# Bind to 0.0.0.0:5000 so clients can connect via Docker port-forwarding or Cloud VPS Public IP
CMD ["python", "-m", "server.server", "--host", "0.0.0.0", "--port", "5000"]
