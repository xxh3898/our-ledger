# syntax=docker/dockerfile:1.12

FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build

WORKDIR /workspace

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM ghcr.io/nginx/nginx-unprivileged:1.30.4-alpine@sha256:93722936b82ec8a1178d48448e619226680d2de3706a1640800e186cd5fa7fd3 AS runtime

USER root
RUN rm -rf /usr/share/nginx/html/*

COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=101:101 /workspace/dist /usr/share/nginx/html

USER 101:101
EXPOSE 8080
STOPSIGNAL SIGQUIT

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
