# SkillLab production image — multi-stage:
#   1. build the React SPA
#   2. slim python runtime serving dist/ + API from one port
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY web/frontend/package.json web/frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY web/frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY skilllab/ ./skilllab/
COPY web/backend/ ./web/backend/
COPY --from=frontend /frontend/dist ./web/frontend/dist
RUN pip install --no-cache-dir ".[web]" \
    && useradd -r -u 10001 -m skilllab \
    && mkdir -p /lab && chown skilllab:skilllab /lab
USER skilllab
ENV SKILLLAB_DIR=/lab SKILLLAB_ENV=production
VOLUME ["/lab"]
EXPOSE 8320
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8320/api/v1/health')" || exit 1
CMD ["uvicorn", "web.backend.app:app", "--host", "0.0.0.0", "--port", "8320"]
