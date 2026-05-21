# AI Content Machine

Internal multi-user web tool for AI-driven content generation, organisation
and publishing. Replaces a Google-Sheets-based workflow.

- **Single mode** — pick a prompt template, fill in variables, generate one
  result at a time, save it, optionally publish to WordPress / a custom CMS.
- **Bulk mode** — spreadsheet-like tables where each row is a generation
  task; run hundreds of generations in parallel under provider rate limits.
- **Publishing** — WordPress (incl. Polylang / WPML) or arbitrary Custom CMS
  via a body-template; single posts and bulk runs with pause / resume /
  cancel / rerun-failed.
- **Roles** — `admin` / `manager` / `content_generator`. Role-aware navigation,
  ACL on bulk tables, in-app documentation gated per role.

## Stack

| Layer        | Choice                                                     |
| ------------ | ---------------------------------------------------------- |
| Backend      | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic        |
| DB           | PostgreSQL 16                                              |
| Queue        | Celery + Redis 7                                           |
| Auth         | bcrypt + PyJWT, Fernet (`MultiFernet`) for encrypted secrets |
| Frontend     | Next.js 15 (App Router) + TypeScript + Tailwind 3.4        |
| Deploy       | Docker Compose, Caddy reverse proxy + auto TLS             |

## Repository layout

```
backend/
  app/
    api/         FastAPI routers
    core/        config, security, crypto, ssrf
    db/          base, async session, models
    providers/   AI Studio / Vertex AI / OpenRouter / GitHub Models
    cms/         WordPress + Custom CMS clients
    services/    prompts, ai_assist, bulk_generation, rate_limit, retry,
                 publish_single, publish_bulk, media_cache, login_throttle, ...
    tasks/       celery_app, bulk_generation, publish_single, publish_bulk
    schemas/     Pydantic v2 request/response models
  alembic/versions/   0001..0028
  tests/              pytest suite (SSRF, JWT, publish state machine, ...)
  Dockerfile          dev (single-stage, --reload)
  Dockerfile.prod     prod (multi-stage, non-root, tini, no reload)

frontend/
  app/
    (app)/       protected route group: dashboard, prompts, create, library,
                 publish, users, errors, settings, docs
    login/
    layout.tsx   ThemeProvider + LanguageProvider + AuthProvider
  components/
  content/docs/  bilingual markdown documentation (ru/, en/)
  lib/
  Dockerfile          dev
  Dockerfile.prod     prod (output: standalone, node user)

docker-compose.yml          dev base (db, redis, api, worker; web optional)
docker-compose.prod.yml     prod overlay (Caddy, migrate one-shot, no host
                            ports for db/redis, restart policies, log
                            rotation, memory limits)
Caddyfile                   reverse proxy + automatic TLS
.env.example                authoritative variable reference
```

## Local development (recommended path)

The frontend runs natively on the host (Windows/macOS/Linux); the backend
services run in Docker. We tried full-Docker on Windows and the file-watch
performance under bind mounts was too slow.

### 1. Prerequisites

- Docker Desktop or equivalent
- Node 20+
- Python 3.12 only needed if you want to run `pytest` / scripts on the host

### 2. First-time setup

```bash
git clone <repo> ai-content-machine
cd ai-content-machine

cp .env.example .env
# Edit .env. At minimum set:
#   FERNET_KEY=<value from python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
#   JWT_SECRET=<value from python -c "import secrets; print(secrets.token_urlsafe(48))">
#   BOOTSTRAP_ADMIN_PASSWORD=<a strong dev password>
```

### 3. Backend

In one terminal at the repo root:

```bash
docker compose up
```

This starts `db`, `redis`, `api` (port 8000), `worker`. The first run will
build images.

After services are healthy, in another terminal apply migrations and seed
the bootstrap admin:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed
```

### 4. Frontend

In a third terminal:

```bash
cd frontend
npm install   # first time only
npm run dev
```

Open <http://localhost:3010>. Log in with `BOOTSTRAP_ADMIN_EMAIL` and the
password you set in `.env`.

### Useful dev commands

```bash
# Restart api after code change (volumes mount source live; --reload picks
# up Python edits without restart, but config/env changes need recreate):
docker compose up -d --force-recreate api

# Tail worker logs:
docker compose logs -f worker

# Run backend tests (inside the api container, where deps are installed):
docker compose exec api python -m pytest tests/

# Frontend type-check:
cd frontend && npx tsc --noEmit

# Frontend production-strict build (catches issues `next dev` lets through):
cd frontend && npm run build
```

## Production deployment

Self-host on a single VPS with Docker Compose + Caddy. Caddy fetches a
Let's Encrypt cert if `ACM_HOSTNAME` is a real DNS name; uses its built-in
local CA for `localhost`.

### Runbook

```bash
git clone <repo> ai-content-machine
cd ai-content-machine

cp .env.example .env
chmod 600 .env
# Edit .env — set everything from the Production checklist below.

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# After the first successful boot, blank BOOTSTRAP_ADMIN_PASSWORD in .env:
#   BOOTSTRAP_ADMIN_PASSWORD=
# Then restart so the api/worker no longer hold the value in their env:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The prod overlay runs a one-shot `migrate` service that does
`alembic upgrade head && python -m app.seed` and exits; `api` and `worker`
both wait on `migrate: condition: service_completed_successfully`, so
schema changes apply automatically on every deploy.

### Production .env checklist

| Variable                         | Why                                                                    |
| -------------------------------- | ---------------------------------------------------------------------- |
| `FERNET_KEY` or `FERNET_KEYS`    | encrypts provider API keys + CMS credentials at rest                   |
| `JWT_SECRET`                     | signs auth tokens                                                      |
| `BOOTSTRAP_ADMIN_EMAIL/PASSWORD` | first-boot admin; blank the password after the first successful login  |
| `ACM_HOSTNAME`                   | public DNS name; Caddy uses it for the cert and for routing            |
| `ACM_LETSENCRYPT_EMAIL`          | account email for cert issuance                                        |
| `ACM_PUBLIC_API_URL`             | leave default `/api` so frontend calls go through Caddy same-origin    |
| `POSTGRES_PASSWORD`              | use a strong value; the prod compose does not publish 5432 to the host |

### Differences between dev and prod compose

- No `db` / `redis` host port mapping (internal-only)
- No source-bind mounts (images are immutable artefacts)
- `restart: unless-stopped` on every service
- Log rotation: 10 MB × 5 files per service
- Memory limits set per service
- API healthcheck on `/health`
- Caddy on host ports 80/443; everything else internal
- `BOOTSTRAP_ADMIN_PASSWORD` blanked on `api` and `worker` (only `migrate`
  briefly sees it)
- `next.js` built with `output: 'standalone'` and run as the non-root
  `node` user

## FERNET key rotation

Provider API keys, CMS app passwords and similar secrets in the database
are encrypted with Fernet via `MultiFernet`. To rotate without downtime:

```bash
# 1. Generate a new key.
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Switch from FERNET_KEY=<old> to:
#       FERNET_KEYS=<new>,<old>
#    in .env, then restart api + worker.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker

# 3. New writes are encrypted under <new>. Old ciphertext still decrypts
#    via <old>. Application keeps working as a hybrid.

# 4. Re-encrypt every secret column under <new> using the rotation helper.
#    crypto.rotate(token) is provided in app/core/crypto.py — wrap it in a
#    short script that walks the relevant tables.

# 5. Drop <old> from FERNET_KEYS:
#       FERNET_KEYS=<new>
#    Restart api + worker again.
```

Single-key mode (`FERNET_KEY=<one>`) keeps working for installs that don't
need rotation; the loader treats it as a one-key list.

## Where the secrets live

| Secret                              | Stored                                              | Encrypted with     |
| ----------------------------------- | --------------------------------------------------- | ------------------ |
| User passwords                      | `users.password_hash`                               | bcrypt (one-way)   |
| LLM provider API keys               | `providers.api_key_encrypted`                       | Fernet             |
| LLM provider structured creds       | `providers.extra_config_encrypted` (Vertex SA JSON, project_id, location) | Fernet |
| WordPress / Custom CMS credentials  | `domains.credentials_encrypted`                     | Fernet             |
| JWT signing secret                  | `JWT_SECRET` env var                                | n/a (server-side)  |
| Fernet key(s)                       | `FERNET_KEY` / `FERNET_KEYS` env var                | n/a (server-side)  |
| Bootstrap admin password            | `BOOTSTRAP_ADMIN_PASSWORD` env var (one-shot)       | bcrypt on first use|
| Caddy TLS keys                      | `caddy_data` Docker volume                          | filesystem only    |

The `.env` file is the only place plaintext secrets sit on disk in
production. Lock it down (`chmod 600`) and keep it out of version control.

## Operations

| Task                  | How                                                                     |
| --------------------- | ----------------------------------------------------------------------- |
| Tail logs             | `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker caddy` |
| Restart api           | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate api` |
| Apply pending migs    | Just redeploy — the `migrate` service runs them                          |
| Database backup       | `docker compose exec db pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql` (cron this) |
| Database restore      | `cat backup.sql \| docker compose exec -T db psql -U $POSTGRES_USER $POSTGRES_DB`         |
| Rotate Fernet key     | See "FERNET key rotation" above                                          |
| Run backend tests     | `docker compose exec api python -m pytest tests/`                        |
| Reset admin password  | Set `BOOTSTRAP_ADMIN_RESET_PASSWORD=true` + `BOOTSTRAP_ADMIN_PASSWORD=<new>`, restart, then unset |

### Health endpoints

- `GET /health` — API liveness (used by api healthcheck)
- Frontend has no separate liveness endpoint; Caddy routes both `/` (web)
  and `/api/*` (backend, prefix stripped) on the same host.

## Security notes

- **SSRF guards** — every user-supplied URL (`Domain.base_url`, `media_url`)
  is validated against a denylist of private/loopback/link-local/metadata
  ranges, and re-validated at every redirect hop via `SafeAsyncTransport`.
- **Login throttling** — Redis-backed counters: 30 failures per IP / 5 min,
  10 failures per email / 15 min, with `Retry-After` on 429. Successful
  login resets the email counter only.
- **HTML preview sandbox** — generated HTML renders inside a sandboxed
  `<iframe>`; the "Open in window" path uses Blob URLs with an opaque
  origin so model-emitted `<script>` tags can't reach `localStorage`.
- **Role gating in the API** — bulk-table ACL is per-resource (`read` /
  `write` / `delete` levels); admin-only routes (`/settings`,
  `/publish/defaults`) are hard-gated on the router.
- **Last-admin protection** — demoting/deleting the last active admin is
  rejected; concurrency-safe via a Postgres advisory lock.

## Documentation

End-user docs (Russian, with English coming) live at `/docs` inside the
running app. Articles are role-gated: a `content_generator` does not see
publish/users/errors/settings articles. The dashboard has a prominent
section linking to the docs.

To edit content: write markdown in `frontend/content/docs/ru/<slug>.md`.
The slug list and role gating live in `frontend/lib/docs.ts`.

## License

Internal. Not currently published under an open-source licence.
