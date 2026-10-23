# Stage 1: build the static bundle.
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Vite inlines import.meta.env at build time, so the gateway origin has to be
# passed in as a build argument - setting it at runtime has no effect.
ARG VITE_API_URL=http://localhost:4000/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: serve the bundle. nginx keeps one worker and no build toolchain in
# the image, which is what a static SPA actually needs.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
