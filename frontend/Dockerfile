# syntax=docker/dockerfile:1.7
FROM node:20-slim

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1 \
    npm_config_loglevel=http \
    npm_config_fund=false \
    npm_config_audit=false

COPY package.json ./

# BuildKit cache mount keeps the npm cache between builds — re-installs are seconds, not minutes.
RUN --mount=type=cache,target=/root/.npm \
    npm install --progress=true --fetch-retries=5 --fetch-retry-mintimeout=20000

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
