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
