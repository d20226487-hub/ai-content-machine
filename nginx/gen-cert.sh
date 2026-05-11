#!/usr/bin/env bash
#
# Generate a self-signed cert pair for nginx-acm.
#
# The cert doesn't need to be trusted by browsers — Traefik connects
# to nginx-acm with `insecureSkipVerify: true`, so any valid cert works.
# A long-lived self-signed cert (10 years) is the simplest fit.
#
# Run once after cloning the repo, before the first `docker compose up`:
#   bash nginx/gen-cert.sh
#
# Re-run to rotate. The files are gitignored.

set -euo pipefail

cd "$(dirname "$0")"
mkdir -p certs

if [[ -f certs/selfsigned.crt && -f certs/selfsigned.key ]]; then
  echo "certs/selfsigned.{crt,key} already exist — refusing to overwrite."
  echo "Delete them first if you want to regenerate."
  exit 1
fi

openssl req -x509 -nodes -newkey rsa:2048 \
  -days 3650 \
  -subj "/CN=nginx-acm" \
  -addext "subjectAltName=DNS:nginx-acm,DNS:localhost,IP:127.0.0.1" \
  -keyout certs/selfsigned.key \
  -out    certs/selfsigned.crt

chmod 600 certs/selfsigned.key
chmod 644 certs/selfsigned.crt

echo
echo "Wrote:"
echo "  nginx/certs/selfsigned.crt"
echo "  nginx/certs/selfsigned.key"
echo
echo "Note: nginx-acm reads these on container start, so a regen needs a"
echo "      \`docker compose up -d --force-recreate nginx-acm\` to take effect."
