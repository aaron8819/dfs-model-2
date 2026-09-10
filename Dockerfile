FROM node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS frontend
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=bind,from=wheelhouse,target=/wheels pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.lock
COPY server/ ./server/

FROM base AS migration
COPY alembic.ini ./
COPY migrations/ ./migrations/
ENTRYPOINT ["python", "-m", "alembic"]
CMD ["upgrade", "head"]

FROM base AS runtime
ENV APP_ENV=production
RUN pip uninstall --yes black coverage pytest pytest-cov ruff
RUN useradd --uid 10001 --create-home app && touch /app/.runtime.lock && chown app:app /app/.runtime.lock
COPY --from=frontend /build/dist ./web/dist
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log", "--timeout-graceful-shutdown", "40"]
