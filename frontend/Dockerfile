FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS builder
WORKDIR /app
ARG VITE_API_URL=http://localhost:8000
ARG VITE_MCP_URL=http://localhost:8001/mcp
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_MCP_URL=${VITE_MCP_URL}
COPY package.json ./
COPY vendor ./vendor
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0
RUN addgroup --system --gid 1001 app && adduser --system --uid 1001 --ingroup app app
COPY --from=builder --chown=app:app /app/dist ./dist
COPY --chown=app:app scripts/static-server.mjs ./server.mjs
USER app
EXPOSE 3000
CMD ["node", "server.mjs"]
