#!/bin/bash
# Run this ONCE on the Alibaba Cloud server to set up the environment.
# Usage: ssh root@8.217.224.101 'bash -s' < server-setup.sh

set -euo pipefail

REPO=/var/www/credit-backtest-studio
APP_USER=backtest

echo "=== Installing system packages ==="
apt-get update -q
apt-get install -y python3 python3-pip python3-venv nginx git certbot python3-certbot-nginx

echo "=== Creating dedicated service user (non-root) ==="
if ! id "$APP_USER" >/dev/null 2>&1; then
  # System account, no login shell, no home login — least privilege.
  useradd --system --shell /usr/sbin/nologin --home-dir "$REPO/backend" "$APP_USER"
fi

echo "=== Creating app directories ==="
mkdir -p /var/www/credit-backtest-studio-frontend
mkdir -p /var/www/certbot                  # Let's Encrypt HTTP-01 webroot

echo "=== Cloning repository ==="
if [ ! -d "$REPO" ]; then
  git clone https://github.com/oct28th-creator/credit-backtest-studio.git "$REPO"
else
  cd "$REPO" && git pull
fi

echo "=== Creating Python virtualenv & installing deps ==="
cd "$REPO/backend"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "=== Copying .env ==="
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "ACTION REQUIRED: Edit $REPO/backend/.env and add DEEPSEEK_API_KEY (and API_KEY to require auth)"
fi

echo "=== Setting ownership (app data writable by service user only) ==="
mkdir -p "$REPO/backend/data"
chown -R "$APP_USER:$APP_USER" "$REPO/backend/data"
chmod 750 "$REPO/backend/data"

echo "=== Installing nginx config ==="
cp "$REPO/deploy/nginx.conf" /etc/nginx/sites-available/credit-backtest-studio
ln -sf /etc/nginx/sites-available/credit-backtest-studio /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== Installing log rotation ==="
cp "$REPO/deploy/backtest-logrotate" /etc/logrotate.d/backtest-backend 2>/dev/null || true

echo "=== Installing daily SQLite backup ==="
cp "$REPO/deploy/backtest-backup.sh" /usr/local/bin/backtest-backup.sh
chmod +x /usr/local/bin/backtest-backup.sh
# 03:15 daily, keep last 14 days (see script).
( crontab -l 2>/dev/null | grep -v backtest-backup.sh ; \
  echo "15 3 * * * /usr/local/bin/backtest-backup.sh" ) | crontab -

echo "=== Installing systemd service ==="
cp "$REPO/deploy/backtest-backend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable backtest-backend
systemctl start backtest-backend

echo ""
echo "=== Setup complete! ==="
echo "Backend: systemctl status backtest-backend"
echo "Logs:    journalctl -u backtest-backend -f"
echo "TLS:     certbot --nginx -d <your-domain>   # then HTTPS is enforced"
echo "Site:    http://8.217.224.101  (until a domain + cert are configured)"
