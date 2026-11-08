FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm test && npm run db:seed && npm run build && npm run typecheck

FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
ARG DEPLOY_COMMIT=local
ENV DEPLOY_COMMIT=$DEPLOY_COMMIT
RUN groupadd --gid 10001 site && useradd --uid 10001 --gid site --no-create-home site
COPY --from=build --chown=site:site /app/dist ./dist
COPY --from=build --chown=site:site /app/data/content.sqlite ./data/content.sqlite
COPY --chown=site:site runtime ./runtime
COPY --chown=site:site src/routing.ts ./src/routing.ts
COPY --chown=site:site scripts/smoke.ts ./scripts/smoke.ts
USER site
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "runtime/server.ts"]
