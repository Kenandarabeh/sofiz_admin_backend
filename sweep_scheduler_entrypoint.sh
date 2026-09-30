#!/bin/bash
# ============================================================
#  SofizAdmin - Sweep Scheduler Container Entrypoint
#  Installs a cron job that runs the daily sweep at 00:01
#  every night, then keeps the container alive via cron daemon.
# ============================================================

set -e

echo "======================================================="
echo " [SofizAdmin] Sweep Scheduler Container Starting..."
echo " Timezone: ${TZ:-UTC}"
echo " Cron Schedule: 1 0 * * * (daily at 00:01)"
echo "======================================================="

# Wait for DB to be ready (same host as web container)
echo "Waiting for database to be ready..."
until python /app/manage.py migrate --check --no-input 2>/dev/null; do
    echo "  Database not ready yet, retrying in 5s..."
    sleep 5
done
echo "Database ready."

# Install cron
apt-get install -y --no-install-recommends cron >/dev/null 2>&1 || true

# Build the crontab - runs at 00:01 every day
CRON_JOB="1 0 * * * /bin/bash /app/sweep_cron.sh >> /app/logs/sweep/cron_daemon.log 2>&1"

# Write crontab for root user
echo "$CRON_JOB" | crontab -

echo ""
echo " Cron job registered:"
echo "   $CRON_JOB"
echo ""
echo " Sweep logs will be stored at: /app/logs/sweep/"
echo "======================================================="

# Create logs directory
mkdir -p /app/logs/sweep

# Start cron in foreground
echo " Starting cron daemon..."
cron -f
