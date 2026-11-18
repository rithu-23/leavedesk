# LeaveDesk web image (Capstone 4): build the Angular app with Node, serve it with nginx.
# Two stages, so the final image contains only nginx and the built files (no Node, no
# node_modules, no source code).

# ---- Stage 1: build ----
FROM node:24-alpine AS build
WORKDIR /app

# Install packages first: this layer is reused until package.json or package-lock.json change.
COPY package.json package-lock.json ./
RUN npm ci

# Then copy the source and build for production (output in dist/leavedesk-web/browser).
COPY . .
RUN npm run build

# ---- Stage 2: serve ----
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/leavedesk-web/browser /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
