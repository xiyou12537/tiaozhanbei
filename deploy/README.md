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

The deployment is a logical virtual-QPU simulator and does not represent real
QPU execution.
