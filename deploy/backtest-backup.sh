#!/bin/bash
# Daily SQLite backup for BackTest Studio. Installed to
# /usr/local/bin/backtest-backup.sh and run from cron by server-setup.sh.
#
# Uses the sqlite3 .backup command (consistent snapshot even while the API is
# running) and keeps the last 14 days.
set -euo pipefail

DB=/var/www/credit-backtest-studio/backend/data/backtest_studio.db
BACKUP_DIR=/var/backups/backtest
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB" ]; then
  echo "no database at $DB yet — nothing to back up"
  exit 0
fi

STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$BACKUP_DIR/backtest_studio-$STAMP.db"

# Consistent online backup.
sqlite3 "$DB" ".backup '$OUT'"
gzip -f "$OUT"

# Prune old backups.
find "$BACKUP_DIR" -name 'backtest_studio-*.db.gz' -mtime +"$KEEP_DAYS" -delete

echo "backup written: $OUT.gz"
