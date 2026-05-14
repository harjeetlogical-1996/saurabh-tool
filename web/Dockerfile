# syntax=docker/dockerfile:1.7
#
# Tool web frontend (Next.js standalone) for Cloud Run.
# Mirrors the marketing-site pattern: deps → build → minimal runner.

# ─── deps ─────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --include=dev

# ─── build ────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build-time env: the API URL must be baked in because Next bakes
# NEXT_PUBLIC_* into the client bundle at build time. Cloud Run can
# inject via --build-arg or via the Cloud Build substitution.
ARG NEXT_PUBLIC_API_URL=https://tools-api.saurabhbhayana.com
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

# ─── runner ──────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Cloud Run injects PORT (default 8080). Next's standalone server reads it.
ENV PORT=8080
ENV HOSTNAME=0.0.0.0

# Non-root user
RUN groupadd --system --gid 1001 nodejs \
 && useradd  --system --uid 1001 --gid nodejs nextjs

COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 8080
CMD ["node", "server.js"]
