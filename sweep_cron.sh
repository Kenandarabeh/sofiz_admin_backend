#!/bin/bash
# ============================================================
#  SofizAdmin - Stellar Daily Sweep Cron Runner
#  Runs every night at midnight (00:01) automatically.
#  Logs output to /app/logs/sweep/ with date-stamped files.
# ============================================================

set -e

LOG_DIR="/app/logs/sweep"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="$LOG_DIR/sweep_${TIMESTAMP}.log"
DATE_TODAY=$(date '+%Y-%m-%d')

echo "=================================================" | tee -a "$LOG_FILE"
echo " [SofizAdmin] Daily Stellar Sweep Started"        | tee -a "$LOG_FILE"
echo " Date: ${DATE_TODAY}  Time: ${TIMESTAMP}"         | tee -a "$LOG_FILE"
echo "=================================================" | tee -a "$LOG_FILE"

# Run the Django management command
python /app/manage.py execute_daily_sweep 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo "" | tee -a "$LOG_FILE"
echo "=================================================" | tee -a "$LOG_FILE"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo " [SofizAdmin] Sweep Completed Successfully." | tee -a "$LOG_FILE"
else
    echo " [SofizAdmin] Sweep FAILED with exit code: $EXIT_CODE" | tee -a "$LOG_FILE"
fi
echo "=================================================" | tee -a "$LOG_FILE"

# Keep only last 30 days of logs
find "$LOG_DIR" -name "sweep_*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
