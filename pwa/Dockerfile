# syntax=docker/dockerfile:1
#
# Niouzou PWA image: build the Vite bundle, then serve the static files with
# Nginx.
#
# IMPORTANT: Vite inlines `import.meta.env.VITE_API_URL` at *build* time, so the
# API URL must be passed as a build arg, not a runtime env var. The browser (not
# this container) calls the API, so it must be a URL the browser can reach.

# --- Build stage --------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Install deps from the lockfile first (cached unless package*.json change).
COPY package.json package-lock.json ./
RUN npm ci

# Bake the API base URL into the bundle. Default matches the self-host compose
# (API published on :8000). Override with --build-arg VITE_API_URL=... .
ARG VITE_API_URL=http://localhost:8000/api/v1
ENV VITE_API_URL=${VITE_API_URL}

COPY . .
RUN npm run build

# --- Runtime stage: Nginx serving the static build ----------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000
# nginx:alpine's default entrypoint runs nginx; keep its foreground command.
CMD ["nginx", "-g", "daemon off;"]
