FROM node:22-alpine AS builder
WORKDIR /srv
COPY package*.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci
COPY . .
ARG API_URL=http://backend:8000
ENV API_URL=$API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM node:22-alpine
WORKDIR /srv
ENV NODE_ENV=production
COPY --from=builder --chown=node:node /srv/.next/standalone ./
COPY --from=builder --chown=node:node /srv/.next/static ./.next/static
USER node
EXPOSE 3000
ENV HOSTNAME=0.0.0.0
CMD ["node","server.js"]
