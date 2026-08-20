FROM node:26-alpine@sha256:aadf416b2cdce311a8811ba3f0608a61b77dbf997500e2eafe781b51f6a0b019 AS builder
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

FROM node:26-alpine@sha256:aadf416b2cdce311a8811ba3f0608a61b77dbf997500e2eafe781b51f6a0b019 AS runner
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
