# Frontend Dockerfile
# Supports two targets:
#   --target dev   — install deps only, run `pnpm dev` at container start
#   --target prod  — full build baked in, run `pnpm start` at container start (default if no --target is specified)

ARG PNPM_STORE_PATH=/root/.local/share/pnpm/store

# ── Base: shared setup ────────────────────────────────────────────────────────
FROM node:22-alpine AS base
ARG PNPM_STORE_PATH
RUN corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
WORKDIR /app

# ── Deps: install only (cache-friendly) ───────────────────────────────────────
FROM base AS deps
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./frontend/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    cd /app/frontend && pnpm install --frozen-lockfile

# ── Dev: install only, CMD is overridden by docker-compose ───────────────────
FROM base AS dev
COPY --from=deps /app/frontend/node_modules ./frontend/node_modules
COPY frontend ./frontend
EXPOSE 3000

# ── Builder: install + compile Next.js ───────────────────────────────────────
FROM base AS builder
COPY --from=deps /app/frontend/node_modules ./frontend/node_modules
COPY frontend ./frontend
# Skip env validation — runtime vars are injected by nginx/container
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    cd /app/frontend && SKIP_ENV_VALIDATION=1 pnpm build && pnpm prune --prod

# ── Prod: minimal runtime with pre-built output ───────────────────────────────
FROM node:22-alpine AS prod
RUN corepack enable && corepack install -g pnpm@10.26.2
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/frontend ./frontend
EXPOSE 3000
CMD ["sh", "-c", "cd /app/frontend && pnpm start"]