# ── Build Stage: Frontend ──
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --silent
COPY frontend/ ./
ENV VITE_BASE_URL=/app/
ENV VITE_ALLOW_BROWSER_VIEW=true
RUN npm run build

# ── Runtime Stage: Backend + Frontend ──
FROM python:3.11-slim
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY backend/ .

# Frontend build
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Uploads volume
RUN mkdir -p /app/uploads/avatars /app/uploads/images /app/uploads/banners /app/uploads/badges

# Alembic stamp on startup, then run
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
