# Deployment & security notes

## First-time setup
```bash
ssh root@<server> 'bash -s' < deploy/server-setup.sh
certbot --nginx -d <your-domain>   # issue a cert; nginx then enforces HTTPS
```

`server-setup.sh` creates a dedicated **non-root** `backtest` system user, a
Python **virtualenv** at `backend/.venv`, log rotation, and a daily SQLite
backup cron.

## Security posture

| Area | Status | Notes |
|------|--------|-------|
| Service user | `backtest` (non-root) | systemd unit also sets `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`, and a narrow `ReadWritePaths`. |
| TLS | Enforced once a cert exists | `nginx.conf` redirects 80→443 and serves ACME challenges from `/var/www/certbot`. Before the first cert, uncomment the pre-TLS fallback block. |
| Auth | Opt-in API key | Set `API_KEY` in `backend/.env` to require `X-API-Key` on `/api/custom` and `/api/ai/*`. The frontend sends it via `VITE_API_KEY` at build time. |
| Upload size | 50 MB | Enforced both at nginx (`client_max_body_size`) and in `custom.py` (streamed read). |
| Backups | Daily, 14-day retention | `backtest-backup.sh` via cron; consistent `sqlite3 .backup`. |

## Residual risk: strategy sandbox (S4)

`app/strategies/runner.py` runs uploaded strategy code in a **subprocess** with
`setrlimit` CPU/memory caps, a blocked `socket`, and an import allowlist. As the
file itself documents, this is **defence-in-depth, not a hardened security
boundary** — Python introspection can still reach builtins. It is adequate for a
single-tenant, trusted-but-careless deployment **behind the API key**.

For untrusted multi-tenant use, run the sandbox in a container (gVisor / a
locked-down Docker image with `--network=none`, read-only rootfs, dropped
capabilities, and a seccomp profile) or a microVM. That is a larger change and
is intentionally **not** part of this config-level hardening.
