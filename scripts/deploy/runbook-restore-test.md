# Runbook: Restore Test (questr production stack)

Change 008, Phase 1. Authored in Phase 1, executed at real deployment time
(after Phase 3) and monthly thereafter (cron in the first-deployment runbook).

A container volume is not a backup strategy. This drill proves the nightly
`pg_dump -Fc` output actually restores.

## 1. Locate the latest dump

```sh
ls -lt /var/backups/questr/ | head   # expect db-YYYY-MM-DD.dump (pg_dump -Fc)
```

## 2. Manual restore drill

```sh
# Restore into a throwaway database, not the live one
docker exec -i questr-db-1 pg_restore -U questr -d restore_test --clean --if-exists < /var/backups/questr/db-latest.dump
```

`--clean --if-exists` makes the drill repeatable (drops and recreates objects).

## 3. Verify

```sh
docker exec questr-db-1 psql -U questr -d restore_test -c '\dt' | head
docker exec questr-db-1 psql -U questr -d restore_test -c 'select count(*) from users;'
# Row counts must be plausible against the live database:
docker exec questr-db-1 psql -U questr -d questr_db -c 'select count(*) from users;'
```

## 4. Log the result

```sh
logger -t restore-test OK   # or FAILED, matching the monthly cron's alert line
```

## 5. Cleanup

`restore_test` is a throwaway database; leave it in place for the next monthly
run (the `--clean` flag resets it), or drop it:

```sh
docker exec questr-db-1 psql -U questr -d questr_db -c 'drop database restore_test;'
```

## Failure handling

If restore fails: `logger -t restore-test FAILED` fires from the cron line.
Treat as an incident: the backup discipline is broken until a restore
succeeds. Check dump integrity first:

```sh
pg_restore --list /var/backups/questr/db-latest.dump | head
```
