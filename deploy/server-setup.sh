#!/bin/bash
# Run this ONCE on the Alibaba Cloud server to set up the environment.
# Usage: ssh root@8.217.224.101 'bash -s' < server-setup.sh

set -e

echo "=== Installing system packages ==="
apt-get update -q
apt-get install -y python3 python3-pip nginx git

echo "=== Creating app directories ==="
mkdir -p /var/www/credit-backtest-studio-frontend

echo "=== Cloning repository ==="
if [ ! -d "/var/www/credit-backtest-studio" ]; then
  git clone https://github.com/oct28th-creator/credit-backtest-studio.git /var/www/credit-backtest-studio
else
  cd /var/www/credit-backtest-studio && git pull
fi

echo "=== Installing Python dependencies ==="
cd /var/www/credit-backtest-studio/backend
pip3 install -r requirements.txt -q

echo "=== Copying .env ==="
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "ACTION REQUIRED: Edit /var/www/credit-backtest-studio/backend/.env and add DEEPSEEK_API_KEY"
fi

echo "=== Installing nginx config ==="
cp /var/www/credit-backtest-studio/deploy/nginx.conf /etc/nginx/sites-available/credit-backtest-studio
ln -sf /etc/nginx/sites-available/credit-backtest-studio /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== Installing systemd service ==="
cp /var/www/credit-backtest-studio/deploy/backtest-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable backtest-backend
systemctl start backtest-backend

echo ""
echo "=== Setup complete! ==="
echo "Backend: systemctl status backtest-backend"
echo "Logs:    journalctl -u backtest-backend -f"
echo "Site:    http://8.217.224.101"
