# deploy/secrets/ (change 008)

Real secret files live here and are NEVER committed. Git ignores everything
in this directory except this README and the `*.example` templates.

Setup (also documented in `scripts/deploy/runbook-first-deployment.md`):

```sh
cd deploy/secrets
cp pg_password.example pg_password
cp redis_password.example redis_password
cp app.env.example app.env
# Then replace the placeholder values with real generated secrets:
openssl rand -base64 32 > pg_password
openssl rand -base64 32 > redis_password
# Edit app.env: copy the generated passwords in, set APP_URL.
chmod 600 pg_password redis_password app.env
```

On the VM these files must be root-owned, mode 0600.

Files:
- `pg_password`: password for the questr Postgres role (also in app.env).
- `redis_password`: password for Redis requirepass (also in app.env).
- `app.env`: env_file loaded by the app service.
