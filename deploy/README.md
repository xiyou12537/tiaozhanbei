# Production deployment

The public service uses Nginx on port 80, proxies `/api` to a single Uvicorn
worker on `127.0.0.1:8000`, and serves the Vite build from
`/var/www/tiaozhanbei`.

The backend runs as the `ubuntu` system user. Its systemd unit receives the
Docker supplementary group because each molecular workflow invokes the pinned
`liangzhi-qchem:local` image through the host Docker daemon.

Required server paths:

- source: `/opt/tiaozhanbei`
- Python environment: `/opt/tiaozhanbei/.venv`
- persistent SQLite data: `/opt/tiaozhanbei/data`
- frontend build: `/var/www/tiaozhanbei`
- private environment: `/etc/tiaozhanbei/backend.env`

Generate a unique `JWT_SECRET` on the server. Do not deploy the placeholder in
`backend.env.example`. Validate the Nginx configuration with `nginx -t` and the
systemd unit with `systemd-analyze verify` before enabling either service.

## P1.2 database release procedure

The release uses a repeatable SQLite migration for additive molecular Study and
Bond Scan tables/columns. P1.1 scientific diagnostics, implementation versions,
particle-number evidence and routed-plan evidence are stored in additive JSON
result documents; historical JSON is never rewritten. The API returns nullable
audit fields for old Workflow/Study/Scan results and flags terminal scans that
predate the release fields with `legacy_result_missing_release_fields`.

Run the following on the server as the service user, after stopping the single
backend worker and before installing the new systemd unit:

```bash
cd /opt/tiaozhanbei
/opt/tiaozhanbei/.venv/bin/python -m backend.scripts.migrate_molecular_release \
  --database-url "sqlite:////opt/tiaozhanbei/data/partitioning.db" \
  --backup-dir /opt/tiaozhanbei/data/backups
```

The script takes a SQLite online backup before it writes the migration ledger,
creates missing P1/P1.1 tables, or adds a missing additive column. It records
`20260813_p12_molecular_release` with a checksum in `schema_migrations`.
Re-running the command verifies that ledger entry and makes no schema/data
change. Do not run this against an in-memory database or use a destructive
SQLite dump/restore command.

Rollback is a service-level database restore, not a down migration: stop the
backend, retain the failed database under a timestamped forensic filename,
copy the migration-created backup back to `data/partitioning.db`, then start
the prior application version. Verify `PRAGMA integrity_check;` before the
restart. Because the migration only adds schema, rolling the application code
back without restoring the backup is also safe if no data rollback is needed.

## Runtime protection and deployment checks

Keep `--workers 1`: `MOLECULAR_COMPUTE_MAX_CONCURRENT=1` is a process-local
guard calibrated for the 4-core, 3.6 GiB server. A synchronous Workflow sent
while the slot is occupied receives typed HTTP 503
`molecular_compute_capacity_exhausted`; accepted asynchronous Study/Scan tasks
wait for the slot and retain stable queued/running partial results. Do not raise
the worker count unless a cross-process queue/lock is deployed.

The PySCF adapter uses a unique scoped Docker container name plus `--rm`; on a
client timeout it invokes `docker rm -f` for that name. Preflight Docker access
with `sudo -u ubuntu docker image inspect liangzhi-qchem:local` and verify no
residual task containers after a smoke test using
`docker ps --filter 'name=liangzhi-qchem-'`.

Suggested maintenance window: **2–5 minutes** for stopping one local worker,
backup/migration, service restart and health/OpenAPI checks. The migration is
local SQLite metadata work; no planned data rewrite or frontend deployment is
included. Preserve Authorization and Idempotency-Key forwarding in Nginx (the
default proxy configuration forwards request headers unchanged).

The deployment is a logical virtual-QPU simulator and does not represent real
QPU execution.
