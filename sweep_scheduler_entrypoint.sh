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

# Automated midnight cron is explicitly disabled per operational requirements.
# Sweep runs strictly on-demand via the UI Sweep Button.
echo " Automated midnight cron is DISABLED. Sweep is on-demand via UI only."
echo " Container staying alive in dormant idle mode."
tail -f /dev/null
