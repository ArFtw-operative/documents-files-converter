# Verso Folio web: static Vite build served by Caddy (SPA fallback).
FROM node:24-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
COPY packages packages
COPY apps/web/package.json apps/web/package.json
RUN npm ci --no-audit --no-fund
COPY apps/web apps/web
RUN npm --workspace @folio/web run build

FROM caddy:2.10-alpine
# Port 8080 needs no privileges; drop the binary's file capability so it runs with cap_drop: ALL.
RUN apk add --no-cache libcap && setcap -r /usr/bin/caddy && apk del libcap
ENV XDG_DATA_HOME=/tmp/caddy-data XDG_CONFIG_HOME=/tmp/caddy-config
COPY infra/docker/web.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/apps/web/dist /srv
USER 1000:1000
EXPOSE 8080
