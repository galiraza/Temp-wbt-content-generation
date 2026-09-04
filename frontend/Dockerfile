# Mirrors backend/Dockerfile's shape: install, build, then a slim runner.
#
# Unlike the old frontend, NO secret is a build arg here. That app read
# NEXT_PUBLIC_API_KEY, which Next inlines into the browser bundle at build
# time — so the key shipped to every visitor and changing it meant a rebuild.
# This one reads HUB_API_URL / HUB_API_KEY server-side at runtime, so they are
# plain environment variables: the key never reaches the browser, and rotating
# it is a restart rather than a rebuild.

FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The build must not reach the API: pages that fetch are force-dynamic, so
# nothing is prerendered against a backend that is not up yet.
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as a non-root user. The standalone output is self-contained, so nothing
# needs to be written at runtime.
RUN groupadd --system --gid 1001 nodejs \
 && useradd --system --uid 1001 --gid nodejs nextjs

COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
