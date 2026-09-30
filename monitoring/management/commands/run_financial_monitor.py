"""
Background Periodic Financial Monitor Daemon for SofizAdmin
Runs automated periodic balance auditing, Stellar Horizon sync, G2Bulk sync, Epay profits sync, and dispatches email alerts.

Usage:
    python manage.py run_financial_monitor
    python manage.py run_financial_monitor --interval 300
    python manage.py run_financial_monitor --once
"""
import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.services.balance_engine import BalanceEngine
from monitoring.models import MonitoringGlobalSettings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Runs automated periodic financial monitoring and balance auditing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=300,
            help='Audit interval in seconds (default: 300s / 5 minutes)'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run a single audit check and exit immediately'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        run_once = options['once']

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("🚀 Starting SofizAdmin Financial Monitoring Daemon"))
        self.stdout.write(self.style.SUCCESS(f"⏱️ Interval: {interval} seconds"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        while True:
            try:
                now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                self.stdout.write(f"\n[{now_str}] 🔍 Running scheduled financial audit...")

                result = BalanceEngine.run_audit(sync_live=True, send_alerts=True)

                status_color = self.style.SUCCESS if result['is_balanced'] else self.style.ERROR
                self.stdout.write(status_color(
                    f"Audit Completed: Status={result['status']} | Discrepancy={result['discrepancy']:,.2f} DZT"
                ))
                self.stdout.write(
                    f"Assets={result['total_assets']:,.2f} DZT | Expenses={result['total_expenses']:,.2f} DZT | "
                    f"Capital={result['total_capital']:,.2f} DZT | Profits={result['total_profits']:,.2f} DZT"
                )

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error during audit cycle: {e}"))
                logger.exception("Error in financial monitor daemon")

            if run_once:
                break

            self.stdout.write(f"Sleeping for {interval} seconds until next audit cycle...")
            time.sleep(interval)
