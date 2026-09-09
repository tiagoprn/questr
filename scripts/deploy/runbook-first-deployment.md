# Runbook: First Deployment (questr production stack)

Change 008, Phase 1. This runbook is authored in Phase 1 and EXECUTED only
when production deployment happens (after Phase 3). The only Phase 1 execution
is local stack validation (T8 in the change brief).

Target: a fresh Debian/Ubuntu VM, app deployed from the Forgejo registry to
`/opt/questr`. Image: `oa.saga-torino.ts.net:3000/tiago/questr:<version>`
(semver from `pyproject.toml`, D4). All commands as root unless noted.

IMPORTANT: all `docker compose` commands use `-p questr` so the project name
(and container names like `questr-db-1`) is stable regardless of the working
directory. The backup cron in section 10 depends on this.

## 1. VM baseline

### 1.1 Docker Engine from the official apt repository

Not `docker.io`. Follow https://docs.docker.com/engine/install/ubuntu/ and add
the official apt repository, then:

```sh
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker compose version   # must be v2.x
```

### 1.2 daemon.json log caps

```sh
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl restart docker
```

Note: log caps apply to NEW containers only; do this before first `up`.

### 1.3 Hold the engine out of unattended upgrades

```sh
apt-mark hold docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Lift with `apt-mark unhold <pkg>` when deliberately updating. Trade-off: CVE
patches for pinned images arrive only when the stack is redeployed to a newer
tag, so backup/restore discipline (section 5) is load-bearing.

### 1.4 Boot persistence

Docker's restart policies are the only restart actor in this phase (A5,
Docker-only; no watchdog, no systemd units). Verify the daemon is enabled:

```sh
systemctl is-enabled docker   # must print enabled
```

`restart: unless-stopped` on every service in `deploy/compose.yaml` handles
container restarts and boot recovery.

## 2. Registry access (Forgejo)

Reference: `tmp/container-registry.md` B1/B2.

```sh
# B1: insecure registry entry (Tailscale-internal HTTP registry)
# Append to /etc/docker/daemon.json:
#   "insecure-registries": ["oa.saga-torino.ts.net:3000"]
systemctl restart docker
docker info | grep -A1 Insecure   # must list oa.saga-torino.ts.net:3000

# B2: login (token from `pass oa/forgejo-api-token-to-image-registry`)
echo $(pass oa/forgejo-api-token-to-image-registry) | docker login oa.saga-torino.ts.net:3000 --username tiago --password-stdin
```

## 3. Ship the stack

```sh
mkdir -p /opt/questr
# Copy from the repo (rsync or git archive): deploy/, scripts/deploy/
rsync -a deploy/ /opt/questr/deploy/
```

## 4. Secrets

```sh
cd /opt/questr/deploy/secrets
openssl rand -base64 32 > pg_password
openssl rand -base64 32 > redis_password
cp app.env.example app.env
```

Edit `app.env`: paste the generated passwords (same values), set
`APP_URL=<real https:// URL>`. Then:

```sh
chmod 600 pg_password redis_password app.env
chown root:root pg_password redis_password app.env
```

Trade-off, stated: plaintext files on host disk, root-owned 0600, is the
accepted secrets mechanism for this phase.

## 5. Port check

```sh
ss -ltnp | grep -E ':80|:443'   # must be EMPTY before first up
```

## 6. Database migration one-off

Before the first `up -d` (db must be healthy first; the compose file gates
app on db health, so start db, wait for healthy, migrate, then bring the rest):

```sh
cd /opt/questr/deploy
docker compose -p questr up -d db
docker compose -p questr ps      # wait for db healthy
docker compose -p questr run --rm app alembic upgrade head
```

## 7. First bring-up

```sh
docker compose -p questr up -d
watch docker compose -p questr ps   # app, db, redis healthy; caddy running
```

## 8. Reboot drill (replaces the watchdog drill: A5 is Docker-only)

```sh
reboot
# After boot, with no manual action:
docker compose -p questr -f /opt/questr/deploy/compose.yaml ps   # all healthy
```

## 9. Verification (proposal section 5, items 2, 6, 7)

```sh
# Header check: real client IP and https scheme visible to the app
curl -s https://<domain>/health   # 200

# Port check: only 80/443 published
ss -ltnp | grep docker   # expect :80 and :443 only
# From an external host, confirm db/redis are NOT reachable:
#   nc -zv <vm-ip> 5432   -> refused (db has no ports)
#   nc -zv <vm-ip> 6379   -> refused (redis has no ports)
```

## 10. Backups (Work Group 1F)

Root cron, nightly dump plus monthly restore test:

```cron
30 2 * * * docker exec questr-db-1 pg_dump -U questr -d questr_db -Fc > /var/backups/questr/db-$(date +\%F).dump
0 3 1 * * docker exec -i questr-db-1 pg_restore -U questr -d restore_test --clean --if-exists < /var/backups/questr/db-latest.dump || logger -t restore-test FAILED
```

Copy dumps off-box (rclone / S3-compatible). A container volume is not a
backup strategy; backups only count when restore is tested. See
`runbook-restore-test.md` for the manual drill.
