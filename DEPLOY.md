# Deployment

Production deployment guide for **Content Beast** (ACM). Self-hosted on a single
Linux VPS with Docker Compose and Caddy as the reverse proxy and TLS
terminator. Targets an internal team of ~10-50 users.

## What you're deploying

```
                       :443
   Internet ──▶  Caddy  ───▶  web   (Next.js standalone, port 3000)
                  │      ──▶  api   (FastAPI + uvicorn, port 8000)
                  │
                  ├── /api/*  →  api (prefix stripped)
                  └── /*      →  web

  api ──▶ db (Postgres 16, internal-only)
  api ──▶ redis (rate-limit counters, Celery broker)

  worker (Celery + beat, internal-only)
   └─ runs single + bulk publish jobs, hourly backups
```

Caddy handles TLS, security headers, and request routing. Nothing except
ports 80/443 is published to the host. Same-origin frontend → backend, so
no CORS is needed in production.

## Prerequisites

**Host machine**:

- Linux (Ubuntu 22.04+, Debian 12+, or anything with a recent Docker Engine).
- Docker 24+ with Compose v2.20+ (the compose file uses `!reset []`).
- At least 4 GB RAM, 2 vCPUs, 20 GB free disk. The memory limits in
  `docker-compose.prod.yml` total ~5 GB; in practice idle usage is well
  under 1 GB.
- Ports **80** and **443** open inbound. Nothing else needs to be exposed.
- Outbound HTTPS open so the container can reach LLM providers, target
  CMSes, and Let's Encrypt.

**DNS**:

- A DNS A record pointing the public hostname (e.g. `acm.example.com`) at
  the VPS. Caddy will auto-fetch a Let's Encrypt cert on first boot.
- For internal-only deployments without public DNS, set
  `ACM_HOSTNAME=localhost` and use the built-in local CA, or add
  `tls internal` to the Caddyfile if you have a private CA.

**Secrets you'll need to generate before editing `.env`**:

```bash
# Fernet key (encrypts provider API keys + CMS credentials at rest)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# JWT signing secret
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Strong Postgres password (any 32+ char random string)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Strong bootstrap admin password (use a password manager)
```

## First deployment

```bash
# 1. Clone
git clone <repo-url> ai-content-machine
cd ai-content-machine

# 2. Configure
cp .env.example .env
chmod 600 .env
$EDITOR .env       # fill in the checklist below

# 3. Build images + run migrations + start services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. Watch the first boot — wait until you see api+worker "healthy" / "Started"
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f migrate api worker caddy

# 5. After the first successful login, blank the bootstrap password
$EDITOR .env       # set BOOTSTRAP_ADMIN_PASSWORD=
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker
```

That's it. The one-shot `migrate` service runs `alembic upgrade head &&
python -m app.seed` on every `up`, so schema changes apply automatically and
the bootstrap admin is created exactly once (idempotent on re-run).

### `.env` checklist for production

Open `.env.example` to see all variables with comments. The ones you
**must** set before the first `up`:

| Variable                       | Required | Notes                                                                             |
| ------------------------------ | -------- | --------------------------------------------------------------------------------- |
| `FERNET_KEY`                   | yes      | from the generator above. Or use `FERNET_KEYS=<new>,<old>` during rotation.       |
| `JWT_SECRET`                   | yes      | from the generator above                                                          |
| `POSTGRES_PASSWORD`            | yes      | strong random — port 5432 is internal only but still don't ship the dev default   |
| `BOOTSTRAP_ADMIN_EMAIL`        | yes      | the first user that exists                                                        |
| `BOOTSTRAP_ADMIN_PASSWORD`     | yes      | blank this after first login                                                      |
| `ACM_HOSTNAME`                 | yes      | public DNS name or `localhost`                                                    |
| `ACM_LETSENCRYPT_EMAIL`        | yes      | needed for Let's Encrypt; ignored when `ACM_HOSTNAME=localhost`                   |
| `ACM_PUBLIC_API_URL`           | no       | leave default `/api` so the frontend bundle calls Caddy same-origin               |
| `LOG_FORMAT`                   | no       | prod compose forces `json`; leave the line blank or set `json` explicitly         |
| `LOG_LEVEL`                    | no       | default `INFO` is fine                                                            |
| `SENTRY_DSN`                   | optional | leave blank to disable. Compatible with self-hosted GlitchTip                     |
| `SENTRY_ENVIRONMENT`           | optional | only matters if DSN is set                                                        |
| `SENTRY_TRACES_SAMPLE_RATE`    | optional | `0.0` = errors only (default)                                                     |

### Verifying the deploy

```bash
# 1. Containers all running:
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Expected (migrate is "Exited (0)"; everything else "running" + healthy):
#   acm-caddy-1     ... Up
#   acm-api-1       ... Up (healthy)
#   acm-worker-1    ... Up (healthy)
#   acm-web-1       ... Up
#   acm-db-1        ... Up (healthy)
#   acm-redis-1     ... Up
#   acm-migrate-1   ... Exited (0)
#   acm-warmup-1    ... Exited (0)

# 2. Health endpoint through Caddy:
curl -k https://$ACM_HOSTNAME/api/health
# → {"status":"ok"}

# 3. Security headers from Caddy:
curl -kI https://$ACM_HOSTNAME/ | grep -iE 'strict-transport|x-frame|x-content'

# 4. Browse https://$ACM_HOSTNAME and sign in with BOOTSTRAP_ADMIN_EMAIL.
```

If you see `502 Bad Gateway` on the first request right after `up`,
that's the api still warming up. The `warmup` one-shot pings `/health` a
few times to absorb cold-start latency, but DB-heavy first request can
still trip. Refresh.

## Deploy modes

There are two front-of-house configurations. Pick the one that fits your
infrastructure — the rest of the stack (api, worker, db, redis, migrate,
web, backups) is identical in both.

| Mode      | Reverse proxy + TLS | When to use                                                                                       |
| --------- | ------------------- | ------------------------------------------------------------------------------------------------- |
| **Caddy** | Caddy on host 80/443, Let's Encrypt | Solo VPS deploy. ACM is the only thing on the host that needs the public ports.                  |
| **Traefik** | Host Traefik on 80/443, ACM behind it | Shared host running multiple tools through a single Traefik. ACM only exposes an internal nginx. |

### Mode A — Caddy (default)

The runbook above. Compose command is:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Mode B — Traefik-fronted

This mode disables Caddy and adds an `nginx-acm` container that sits on
both the ACM internal docker network and the external `traefik_proxy`
network. Traefik (running outside this stack on the same host) reaches it
by service name at `https://nginx-acm:443` with `insecureSkipVerify`.

**One-time setup**:

```bash
# 1. Create the external network Traefik already uses (skip if it exists):
docker network create traefik_proxy

# 2. Generate the self-signed cert pair for nginx-acm:
bash nginx/gen-cert.sh

# 3. Add the router + service block to your Traefik dynamic config —
#    see nginx/traefik-router.example.yml for the exact shape. Set the
#    Host(`...`) rule to whatever DNS name points at this host.
```

**Deploy**:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.traefik.yml \
  up -d --build
```

`docker compose ps` will show `caddy` in `Exited (0)` — that's intentional.
The Traefik overlay no-ops Caddy's entrypoint because Compose overlays
can't fully remove a service.

**What's different vs Mode A**:

- Caddy is inert; ports 80/443 are owned by Traefik on the host.
- TLS is terminated twice: once at Traefik (public cert) and again at
  nginx-acm (long-lived self-signed). Traefik trusts the self-signed cert
  via `serversTransport: insecure-backend`.
- IP allow-listing happens in Traefik's `allow-vpn-only` middleware, not in
  ACM. The login throttle inside ACM still works on real client IPs because
  both proxies pass `X-Forwarded-For` through.
- `ACM_HOSTNAME` and `ACM_LETSENCRYPT_EMAIL` in `.env` are unused in this
  mode (no cert is issued by ACM itself). The frontend bundle still uses
  `ACM_PUBLIC_API_URL=/api` for same-origin routing — leave that as is.

### Localhost testing

Both modes have a way to test locally without touching production:

- **Dev path (recommended for day-to-day work)** — use the base compose
  alone with the frontend running natively, exactly as the development
  README describes. No reverse proxy, no TLS. Browse `http://localhost:3010`.
  This works regardless of which prod mode you'll eventually deploy with.

  ```bash
  docker compose up                # backend in docker
  cd frontend && npm run dev       # frontend on :3010 natively
  ```

- **Caddy mode dry-run on localhost** — leave `ACM_HOSTNAME=localhost`
  in `.env`. Caddy uses its built-in local CA. Browse
  `https://localhost` (your browser will warn about the cert — expected).

- **Traefik mode dry-run on localhost** — without Traefik installed, you
  can still exercise the nginx-acm container directly. Uncomment the
  `ports: ["127.0.0.1:8443:443"]` line in `docker-compose.traefik.yml`
  (it's pre-written, commented out, near the bottom of the `nginx-acm`
  service), then `up -d`. Browse `https://localhost:8443`. Re-comment the
  line before deploying to production so Traefik is the only path in.

## Subsequent deploys

Use the clean-sync deploy script — **do not** just `git pull`:

```bash
./scripts/deploy.sh
```

It forces the working tree to match `origin/main` (`git reset --hard`),
removes orphaned untracked files from the `frontend/` and `backend/` build
contexts (`git clean -fd`), then runs the same `up -d --build`. Migrations run
automatically before `api` and `worker` accept connections; the frontend is
rebuilt with the current `ACM_PUBLIC_API_URL` build arg; Caddy keeps its
volume so certs persist.

> **Why not a plain `git pull`?** The web image is built from `./frontend`
> with `COPY . .`, so Docker bakes in whatever is on disk. `git pull` updates
> tracked files but never deletes a file that was *removed upstream* if a
> stale untracked copy is sitting on the server. That orphan then gets
> compiled by `next build` against the new code around it and fails the build
> (see Troubleshooting → "Build fails on a component that was deleted
> upstream"). `git reset --hard` + `git clean -fd` makes that impossible.
> `clean` uses no `-x`, so gitignored `node_modules` / `.next` / `.env` are
> preserved.

If you only changed one service, pass it through to save build time:

```bash
./scripts/deploy.sh api worker
```

Traefik-fronted deploys add the overlay via an env var:

```bash
COMPOSE_FILES="docker-compose.yml docker-compose.prod.yml docker-compose.traefik.yml" \
  ./scripts/deploy.sh
```

The equivalent by hand, if you'd rather not use the script:

```bash
git fetch origin main && git reset --hard origin/main
git clean -fd -- frontend backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Backups

Two layers run in parallel — pick whichever fits your ops:

### Built-in (recommended)

Configure once from the admin UI on `/settings`:

- Toggle **Scheduled backups** on.
- Pick the hour-of-day (UTC) it should run.
- Set retention (number of local backups to keep).
- Optionally fill the S3 fields (endpoint, bucket, prefix, access key,
  secret key, retention on the remote side). Works with AWS S3,
  Backblaze B2, Cloudflare R2, MinIO, etc.

The worker runs `pg_dump | gzip` into the `db_backups` Docker volume on
schedule, rotates locally, and uploads to S3 if configured. Status, errors,
and a "Run now" button are on the same page. See [`BACKUP details`] in the
in-app docs.

### Manual (for migrations, server moves, snapshots before risky upgrades)

```bash
# Dump
docker compose exec -T db pg_dump -U $POSTGRES_USER -F c -d $POSTGRES_DB \
  > acm-$(date -u +%Y%m%d-%H%M).pgcustom

# Restore (into an empty database; recreate if needed)
docker compose exec -T db pg_restore -U $POSTGRES_USER -d $POSTGRES_DB \
  --clean --if-exists < acm-YYYYMMDD-HHMM.pgcustom
```

> **What's not backed up by `pg_dump`**: the `caddy_data` volume (TLS
> certs — Caddy will re-issue), Docker images (rebuild from git), the
> `.env` file (back this up separately and store it somewhere safe).

## FERNET key rotation

Provider API keys and CMS credentials are encrypted at rest with Fernet.
To rotate without downtime:

```bash
# 1. Generate a new key.
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. In .env, switch FERNET_KEY=<old> to FERNET_KEYS=<new>,<old> and restart.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker

# 3. Both old + new ciphertext are readable; new writes use <new>.

# 4. (Optional) Re-encrypt every stored secret under <new>:
#    crypto.rotate(token) is provided in app/core/crypto.py — write a short
#    script that walks providers + domains.

# 5. Drop <old>:
$EDITOR .env       # set FERNET_KEYS=<new> (or back to FERNET_KEY=<new>)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker
```

Skip step 4 if you don't care that some rows are still in `<old>` — they'll
get re-encrypted under `<new>` the next time they're saved through the UI.

## Operations cheat sheet

```bash
# Tail logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker caddy

# Force-restart one service (e.g. after editing .env)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate api

# Run backend tests
docker compose exec api python -m pytest tests/

# Open a Postgres shell
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB

# Reset an admin password (one-shot via seed)
$EDITOR .env       # BOOTSTRAP_ADMIN_RESET_PASSWORD=true, BOOTSTRAP_ADMIN_PASSWORD=<new>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate migrate
$EDITOR .env       # unset both lines again
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker

# Show migration head
docker compose exec api alembic current

# Apply migrations manually (normally automatic via the migrate service)
docker compose exec api alembic upgrade head
```

## Troubleshooting

**Caddy can't get a Let's Encrypt cert** — the DNS A record isn't pointing at
the VPS yet, or port 80 is blocked. Caddy retries; check `docker compose
logs caddy`. For internal-only domains, switch to the local CA or
`tls internal`.

**`migrate` exits with non-zero status** — the api/worker won't start.
Read `docker compose logs migrate`. The most common cause is a wrong
`DATABASE_URL` env (the prod compose hard-codes it to point at the `db`
container — don't override it in `.env`).

**`502 Bad Gateway` from Caddy** — api is still warming up or has crashed.
`docker compose ps` should show api as healthy. If not, check
`docker compose logs api` for an exception on boot. Common: missing
`FERNET_KEY` / `JWT_SECRET` in `.env`.

**Login throttled (`429 Retry-After`)** — too many failed attempts from
the same IP or against the same email. Default cap is 30 fails/5 min per IP
and 10 fails/15 min per email. Wait it out or restart the `redis` container
to clear all counters.

**Worker says "Connection refused" to Redis** — `redis` not up yet. The
`api`/`worker` services declare `depends_on: redis`, so this usually only
happens during a partial restart. `docker compose up -d redis`.

**Multi-site bulk publish fails with `Domain "X" not found`** — the name in
the table cell must match `domains.name` exactly (case-sensitive, no
trailing whitespace). Migration 0017 enforces `UNIQUE(name)` and auto-
renamed any duplicates that existed before the upgrade — review
`/publish/domains` after the first deploy.

**A test in `test_publish_state_machine.py` fails** — should not happen on
a clean checkout; if it does, your image is probably stale. Rebuild:
`docker compose -f docker-compose.yml -f docker-compose.prod.yml build api`.

**Build fails on a component that was deleted upstream** — e.g.
`next build` errors in `./components/SavedGenerationsModal.tsx` (or any file
you can confirm is gone from the repo with `git cat-file -e
HEAD:frontend/components/<name>` → "NOT IN HEAD"). The cause is a stale
**untracked** copy of a deleted file lingering in the server's checkout: a
plain `git pull` won't remove it, and `COPY . .` then bakes it into the web
image where it's compiled against the newer code and fails type-checking.
Fix by deploying clean — `./scripts/deploy.sh` (or the manual `git reset
--hard origin/main && git clean -fd -- frontend backend` shown under
"Subsequent deploys") — then rebuild with `--build`. To clear a Docker layer
cache that may also hold the orphan, add `--no-cache`:
`docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache web`.
Known files removed in recent revisions that may still be orphaned on an
old checkout: `SavedGenerationsModal.tsx`, `TestPromptModal.tsx`,
`domains/DomainFolderSidebar.tsx`, `CategoryTree.tsx`, `ManageTagsModal.tsx`.

## Rolling back

The system has no built-in down-migrations beyond what Alembic generates
(some 0015+ migrations explicitly raise on `downgrade`). To roll back:

1. Restore a Postgres dump taken **before** the deploy you're rolling back from.
2. Check out the previous git commit and redeploy.

For this reason, take a manual `pg_dump` (or trigger a backup from the
admin UI) right before any deploy that includes a migration. The README's
"What changed" notes call out migrations explicitly per session.

## Where the secrets live

| Secret                              | Stored                                              | Encrypted with     |
| ----------------------------------- | --------------------------------------------------- | ------------------ |
| User passwords                      | `users.password_hash`                               | bcrypt (one-way)   |
| LLM provider API keys               | `providers.api_key_encrypted`                       | Fernet             |
| LLM provider structured creds       | `providers.extra_config_encrypted` (Vertex SA JSON, project_id, location) | Fernet |
| WordPress / Custom CMS credentials  | `domains.credentials_encrypted`                     | Fernet             |
| S3 backup access keys               | `app_settings.backup_config`                        | Fernet             |
| JWT signing secret                  | `JWT_SECRET` env var                                | n/a (server-side)  |
| Fernet key(s)                       | `FERNET_KEY` / `FERNET_KEYS` env var                | n/a (server-side)  |
| Bootstrap admin password            | `BOOTSTRAP_ADMIN_PASSWORD` env var (one-shot)       | bcrypt on first use|
| Caddy TLS keys                      | `caddy_data` Docker volume                          | filesystem only    |

The `.env` file is the only place plaintext secrets sit on disk in
production. Lock it down (`chmod 600`) and back it up out-of-band (a
password manager or your secrets vault, not the same disk).
