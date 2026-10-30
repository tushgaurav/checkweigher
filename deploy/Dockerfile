# Multi-arch (linux/arm64 for Raspberry Pi, linux/amd64 for x86) image with the collector,
# API and the built dashboard. Build from the repository root:
#   docker build -f deploy/Dockerfile -t checkweigher:latest .
# Pin base images by digest for production deployments.

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.7.2 AS uv

FROM python:3.13-slim AS app
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    CW_CONFIG=/config/config.yaml CW_WEB_DIST=/app/web
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist /app/web
RUN useradd --system --uid 1000 --groups dialout cw && mkdir -p /data/spool && chown -R cw /data
USER cw
EXPOSE 8000
CMD ["cw-api"]
