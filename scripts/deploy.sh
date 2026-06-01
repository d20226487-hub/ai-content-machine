#!/usr/bin/env bash
#
# Clean-sync deploy for AI Content Machine.
#
# Why this exists
# ---------------
# The web image is built from the ./frontend build context with `COPY . .`,
# so Docker bakes in *whatever* is on disk — including untracked files. A plain
# `git pull` into a long-lived checkout updates tracked files but does NOT
# delete a file that was removed in git while a stale untracked copy lingers
# on the server. That stale copy then gets compiled by `next build` against the
# new code around it and fails the build, e.g.:
#
#   ./components/SavedGenerationsModal.tsx
#   Type error: Argument of type 'Dispatch<...>' is not assignable to ...
#
# (SavedGenerationsModal.tsx was deleted upstream; the orphan on the server was
# being compiled against the new paginated listSavedGenerations() signature.)
#
# This script forces the working tree to match the committed branch exactly,
# removes orphaned files from the Docker build contexts, then builds + starts.
#
# Usage
# -----
#   ./scripts/deploy.sh                 # full stack, Caddy mode (default)
#   ./scripts/deploy.sh api worker      # rebuild only some services
#   DEPLOY_BRANCH=main ./scripts/deploy.sh
#   # Traefik-fronted deploy:
#   COMPOSE_FILES="docker-compose.yml docker-compose.prod.yml docker-compose.traefik.yml" \
#     ./scripts/deploy.sh
#
set -euo pipefail

# Run from the repo root regardless of where the script is invoked.
cd "$(dirname "$0")/.."

BRANCH="${DEPLOY_BRANCH:-main}"
COMPOSE_FILES="${COMPOSE_FILES:-docker-compose.yml docker-compose.prod.yml}"

compose_args=()
for f in $COMPOSE_FILES; do
  compose_args+=(-f "$f")
done

echo "==> Syncing working tree to origin/${BRANCH}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

# Remove untracked orphans from the Docker build contexts ONLY (frontend and
# backend are what `COPY . .` ingests). No -x, so gitignored artifacts that are
# expensive or sensitive to recreate — node_modules, .next, .env — are kept.
# nginx/ (self-signed certs from gen-cert.sh) and the tracked Caddyfile are
# deliberately out of scope.
echo "==> Removing stale untracked files from build contexts"
git clean -fd -- frontend backend

echo "==> Building images and (re)starting services"
docker compose "${compose_args[@]}" up -d --build "$@"

echo "==> Current services:"
docker compose "${compose_args[@]}" ps
