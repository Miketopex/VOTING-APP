# ---------- CloudVote · worker (Node.js) ----------
FROM node:22-alpine

ENV NODE_ENV=production
WORKDIR /app

# Install dependencies first so this layer is cached between builds.
# (If package-lock.json exists it is used for reproducible installs.)
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi \
 && npm cache clean --force

COPY src ./src

# node:alpine ships an unprivileged "node" user
USER node

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/health || exit 1

# exec form: node receives SIGTERM directly and shuts down gracefully
CMD ["node", "src/index.js"]