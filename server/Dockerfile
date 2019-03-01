# Dockerfile for Agent Control Server
#
# Build from the repository root:
#   docker build -t agent-control-server -f server/Dockerfile .
#
# Run:
#   docker run -p 8000:8000 agent-control-server

FROM node:20-alpine AS ui-builder

WORKDIR /ui

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV NEXT_TELEMETRY_DISABLED=1
ENV AGENT_CONTROL_STATIC_EXPORT=true
ENV NEXT_PUBLIC_STATIC_EXPORT=true

RUN corepack enable && corepack prepare pnpm@9 --activate

COPY ui/package.json ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY ui/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Configure uv environment variables
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace definition
COPY pyproject.toml uv.lock* ./

# Copy alembic configuration and migrations from server directory
COPY server/alembic.ini ./
COPY server/alembic/ alembic/

# Copy shared dependencies (Workspaces)
COPY models/ models/
COPY engine/ engine/
COPY telemetry/ telemetry/
COPY evaluators/ evaluators/

# Copy server application
COPY server/ server/

# Copy the exported UI bundle that FastAPI serves for hosted deployments
COPY --from=ui-builder /ui/out ./server/ui-dist

# Install server + bundled runtime packages (engine/evaluators/models/telemetry)
# We ignore the lockfile if it's missing or out of sync to ensure build succeeds during dev
RUN uv sync \
    --package agent-control-server \
    --package agent-control-engine \
    --package agent-control-evaluators \
    --package agent-control-models \
    --package agent-control-telemetry \
    --no-dev \
  || uv sync \
    --package agent-control-server \
    --package agent-control-engine \
    --package agent-control-evaluators \
    --package agent-control-models \
    --package agent-control-telemetry \
    --no-dev \
    --frozen

# Add the virtual environment to PATH
