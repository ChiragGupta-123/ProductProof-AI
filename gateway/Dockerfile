FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
# production disables the gateway's loopback-origin allowance, so
# ALLOWED_ORIGINS must list every real browser origin.
ENV NODE_ENV=production
EXPOSE 4000
CMD ["npm", "start"]
