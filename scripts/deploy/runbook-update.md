# Runbook: Update (questr production stack)

Change 008, Phase 1. Authored in Phase 1, executed at real deployment time
(after Phase 3). Updates the running stack to a new pinned image version.

Prerequisites: first deployment done (`runbook-first-deployment.md`), logged
in to the registry on the build machine.

## 1. Build and push the new version (dev machine)

```sh
# Bump version = "X.Y.Z" in pyproject.toml, then:
scripts/deploy/build-and-push.sh
```

The script reads the version from `pyproject.toml`, builds
`deploy/Dockerfile`, and pushes
`oa.saga-torino.ts.net:3000/tiago/questr:<version>` plus `:latest`.

## 2. Deploy the new tag (VM)

```sh
cd /opt/questr/deploy
export QUESTR_VERSION=X.Y.Z
docker compose -p questr up -d
docker compose -p questr ps   # app, db, redis healthy; caddy running
curl -s https://<domain>/health   # 200
```

## 3. Schema migrations (if any)

```sh
cd /opt/questr/deploy
docker compose run --rm app alembic upgrade head
```

Run migrations BEFORE `up -d` when the new image requires new tables: start db
if not running, wait healthy, migrate, then `up -d`.

## 4. Rollback to the previous version tag (D4)

```sh
cd /opt/questr/deploy
export QUESTR_VERSION=<previous-tag>
docker compose -p questr up -d        # recreates app against the old pinned tag
docker compose -p questr ps           # healthy again
# If a migration was applied, review with the team before downgrading data:
#   docker compose -p questr run --rm app alembic downgrade <previous-revision>
```

Rollback targets the previous version tag kept on the registry; the registry
retains every pushed semver tag, which is what makes rollback possible.
