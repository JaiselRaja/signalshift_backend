# Signal Shift — Production deployment guide

Target architecture for a single-VM deploy:

```
                           ┌────────── VM (Ubuntu 22.04 / 24.04) ──────────┐
                           │                                               │
Internet ── 443/80 ──▶ Caddy │ ──▶ Docker ─┬─ api      :8000  (FastAPI)    │
                           │               ├─ frontend :3001  (Next.js)    │
                           │               └─ admin    :3000  (Next.js)    │
                           │                                               │
                           │         Postgres 16 (apt) on 127.0.0.1:5432   │
                           │         Redis 7    (apt) on 127.0.0.1:6379   │
                           └───────────────────────────────────────────────┘
```

Docker runs the three apps. Postgres and Redis run directly on the host via `apt`. Containers reach them via `host.docker.internal` (mapped to the docker bridge gateway). Caddy terminates TLS and reverse-proxies to each service. All container ports are bound to `127.0.0.1` so they're not reachable from the public internet.

---

## 1. Server prep

Assume Ubuntu 22.04 or 24.04 LTS, root or a sudo user.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg ufw git
sudo timedatectl set-timezone Asia/Kolkata   # or your TZ
```

### Install Docker Engine + Compose plugin

```bash
# Add Docker's official GPG key and repo
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Let your user run docker without sudo (re-login after this)
sudo usermod -aG docker $USER
```

Verify: `docker compose version` should print a version.

---

## 2. Postgres (apt)

```bash
sudo apt install -y postgresql-16
sudo systemctl enable --now postgresql
```

Create role and database:

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE signal WITH LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
CREATE DATABASE signalshift OWNER signal;
SQL
```

### Let Docker containers connect

The default docker bridge is `172.17.0.0/16` with gateway `172.17.0.1`. Tell Postgres to listen on loopback **and** the bridge.

Edit `/etc/postgresql/16/main/postgresql.conf`:

```conf
listen_addresses = 'localhost,172.17.0.1'
# Optional hardening (defaults are usually fine)
password_encryption = scram-sha-256
```

Edit `/etc/postgresql/16/main/pg_hba.conf` — append:

```conf
# Docker bridge access for application containers
host    signalshift    signal    172.17.0.0/16    scram-sha-256
```

Reload:

```bash
sudo systemctl reload postgresql
```

Quick smoke test from the host:

```bash
psql -h 172.17.0.1 -U signal -d signalshift -c 'SELECT 1;'
```

---

## 3. Redis (apt)

```bash
sudo apt install -y redis-server
sudo systemctl enable --now redis-server
```

Edit `/etc/redis/redis.conf`:

```conf
bind 127.0.0.1 172.17.0.1 -::1
protected-mode yes
# If you want a password (recommended):
requirepass CHANGE_ME_REDIS_PASSWORD
```

```bash
sudo systemctl restart redis-server
redis-cli -h 172.17.0.1 ping   # PONG
# with password:  redis-cli -h 172.17.0.1 -a PASSWORD ping
```

If you set a Redis password, update `REDIS_URL` to `redis://:PASSWORD@host.docker.internal:6379/0`.

---

## 4. Firewall (ufw)

Public surface should only be 22, 80, 443. Postgres and Redis must never be reachable from the internet.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Because Postgres/Redis listen only on `localhost` and `172.17.0.1` (docker bridge), ufw doesn't need explicit deny rules for them — but double-check with `sudo ss -tlnp | grep -E '5432|6379'` that there's no `0.0.0.0:5432` or `0.0.0.0:6379`.

---

## 5. Clone the three repos

Pick a stable path. Recommend `/opt/signal-shift/`:

```bash
sudo mkdir -p /opt/signal-shift
sudo chown -R $USER: /opt/signal-shift
cd /opt/signal-shift

# NOTE: the compose file expects the frontend/admin checkouts to be named
# exactly 'frontend' and 'admin' (see the build.context paths). The backend
# repo can keep its full name because compose is run from inside it.
git clone https://github.com/JaiselRaja/signalshift_backend.git
git clone https://github.com/JaiselRaja/signalshift_frontend.git frontend
git clone https://github.com/JaiselRaja/signalshift_admin.git admin
```

Directory layout:

```
/opt/signal-shift/
├── signalshift_backend/
├── frontend/
└── admin/
```

---

## 6. Backend `.env` for production

```bash
cd /opt/signal-shift/signalshift_backend
cp .env.example .env
nano .env
```

Minimum production values (match the Postgres/Redis credentials you just set):

```env
DATABASE_URL=postgresql+asyncpg://signal:STRONG_PG_PASSWORD@host.docker.internal:5432/signalshift
REDIS_URL=redis://host.docker.internal:6379/0
# or: redis://:STRONG_REDIS_PASSWORD@host.docker.internal:6379/0

JWT_SECRET_KEY=REPLACE_WITH_64_BYTES_OF_RANDOMNESS    # openssl rand -hex 64
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

APP_ENV=production
DEBUG=false
API_PREFIX=/api/v1
CORS_ORIGINS=["https://app.signalshift.in","https://admin.signalshift.in"]

# MSG91 (OTP only)
MSG91_AUTH_KEY=...
MSG91_EMAIL_DOMAIN=msg.signalshift.in
MSG91_FROM_EMAIL=no-reply@msg.signalshift.in
MSG91_FROM_NAME=Signal Shift
MSG91_OTP_TEMPLATE_ID=signalshift_login_otp

# SendGrid (all other transactional email)
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=no-reply@signalshift.in
SENDGRID_FROM_NAME=Signal Shift
ADMIN_NOTIFICATION_EMAIL=ops@signalshift.in   # optional; leave blank to skip admin alerts
FRONTEND_BASE_URL=https://signalshift.in
BRAND_SUPPORT_EMAIL=support@signalshift.in

# UPI
UPI_VPA=yourvpa@bank
UPI_PAYEE_NAME=Signal Shift
```

> **SendGrid sender auth.** Verify your sending domain (signalshift.in) in the
> SendGrid dashboard before going live, otherwise every outbound message will
> land in spam or bounce. OTP email continues to flow through MSG91; SendGrid
> only handles booking, payment, team, and tournament notifications.

Generate a strong JWT secret:

```bash
openssl rand -hex 64
```

---

## 7. Build-time env for the Next.js images

Next.js inlines `NEXT_PUBLIC_*` at build time, so the compose file passes them as build args. Set these at the path where you run `docker compose`:

```bash
cd /opt/signal-shift/signalshift_backend
cat > .env.compose <<'EOF'
FRONTEND_API_URL=https://api.signalshift.in/api/v1
ADMIN_API_URL=https://api.signalshift.in/api/v1
TENANT_SLUG=default
GOOGLE_CLIENT_ID=...
RAZORPAY_KEY_ID=
EOF
```

(`docker compose` auto-loads `.env` from its working directory; the backend's own `.env` is passed to the api container via `env_file`, but build args come from the file named `.env` in the compose working dir — I'll use `--env-file` to point at `.env.compose` so it doesn't collide.)

---

## 8. First build & launch

```bash
cd /opt/signal-shift/signalshift_backend

# Build (first time takes 5-10 min)
docker compose --env-file .env.compose -f docker-compose.prod.yml build

# Start
docker compose --env-file .env.compose -f docker-compose.prod.yml up -d

# Watch logs
docker compose -f docker-compose.prod.yml logs -f
```

The api container automatically runs `alembic upgrade head` on boot, so DB schema is provisioned on first start.

Seed the default tenant (required for OTP verify to issue tokens — see `memory/project_default_tenant.md`):

```bash
psql -h 172.17.0.1 -U signal -d signalshift -c \
  "INSERT INTO tenants (slug, name, is_active) VALUES ('default', 'Signal Shift', true) ON CONFLICT DO NOTHING;"
```

Seed the super admin:

```bash
psql -h 172.17.0.1 -U signal -d signalshift <<'SQL'
INSERT INTO users (tenant_id, email, role, full_name, is_active)
SELECT id, 'signalshiftturf@gmail.com', 'super_admin', 'Signal Shift Admin', true
FROM tenants WHERE slug = 'default'
ON CONFLICT (tenant_id, email) DO UPDATE SET role = 'super_admin', is_active = true;
SQL
```

Smoke test:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:3001   # frontend
curl -fsS http://127.0.0.1:3000   # admin (will 307 to /login or /dashboard)
```

---

## 9. Reverse proxy (Caddy — auto TLS)

Caddy is the easiest way to get HTTPS with zero TLS config.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Edit `/etc/caddy/Caddyfile` (replace the domains with yours — they must already point to this VM's public IP):

```
api.signalshift.in {
    reverse_proxy 127.0.0.1:8000
    encode gzip
}

app.signalshift.in {
    reverse_proxy 127.0.0.1:3001
    encode gzip
}

admin.signalshift.in {
    reverse_proxy 127.0.0.1:3000
    encode gzip
}
```

```bash
sudo systemctl reload caddy
```

Caddy automatically provisions Let's Encrypt certificates on first request to each domain. No manual certbot.

---

## 10. Operations cheatsheet

```bash
# Tail logs for one service
docker compose -f docker-compose.prod.yml logs -f api

# Restart a single service (picks up updated image or env)
docker compose -f docker-compose.prod.yml up -d --build api

# Pull latest code for one repo + rebuild
cd /opt/signal-shift/signalshift_backend && git pull
docker compose --env-file .env.compose -f docker-compose.prod.yml up -d --build api

# Same for frontend / admin
cd /opt/signal-shift/signalshift_frontend && git pull
cd /opt/signal-shift/signalshift_backend
docker compose --env-file .env.compose -f docker-compose.prod.yml up -d --build frontend

# Run an ad-hoc migration manually (shouldn't be needed — entrypoint does it)
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Stop everything
docker compose -f docker-compose.prod.yml down

# Postgres backup (run from the host, nightly via cron)
pg_dump -h 172.17.0.1 -U signal -Fc signalshift > /var/backups/signalshift-$(date +%F).dump
```

### Nightly backup cron

```bash
sudo tee /etc/cron.daily/signalshift-db-backup > /dev/null <<'EOF'
#!/bin/sh
set -e
mkdir -p /var/backups/signalshift
PGPASSWORD='STRONG_PG_PASSWORD' pg_dump -h 172.17.0.1 -U signal -Fc signalshift \
  > /var/backups/signalshift/signalshift-$(date +\%F).dump
find /var/backups/signalshift -type f -mtime +14 -delete
EOF
sudo chmod +x /etc/cron.daily/signalshift-db-backup
```

---

## Troubleshooting

- **`Connection refused` on 127.0.0.1:5432 from inside a container** — Postgres not listening on the bridge. Check `listen_addresses` in `postgresql.conf`, run `sudo ss -tlnp | grep 5432`, should show `172.17.0.1:5432`.
- **`password authentication failed`** — pg_hba.conf is missing the `172.17.0.0/16` rule, or password in `.env` is wrong.
- **Containers can't reach `host.docker.internal`** — you're on an older Docker that doesn't map it automatically. The compose file already declares `extra_hosts: - "host.docker.internal:host-gateway"` to handle this.
- **Frontend has wrong API URL baked in** — `NEXT_PUBLIC_*` is frozen at build time. Update `.env.compose`, then `docker compose build --no-cache frontend` and restart.
- **Admin login succeeds but dashboard can't load data** — tenant missing. Re-run the seed query from step 8.
- **502 from Caddy** — container crashed or hasn't started yet. `docker compose -f docker-compose.prod.yml ps` and tail the service's logs.
