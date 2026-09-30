"""
Django Management Command to execute automated daily sweep & profit reserve allocation.

Usage:
    python manage.py execute_daily_sweep
    python manage.py execute_daily_sweep --dry-run
    python manage.py execute_daily_sweep --audit-only
    python manage.py execute_daily_sweep --force
"""
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.services.stellar_sweep_service import StellarSweepService


class Command(BaseCommand):
    help = 'Executes midnight Stellar daily sweep and profit reserve allocation with pre-flight audit'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate audit and execution without submitting Stellar transactions'
        )
        parser.add_argument(
            '--audit-only',
            action='store_true',
            help='Only run the pre-sweep safety audit and print report'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force execution even if audit detected discrepancies (Use with caution!)'
        )
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Target date in YYYY-MM-DD format (default: today)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        audit_only = options['audit_only']
        force = options['force']
        date_str = options['date']

        target_date = None
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid date format '{date_str}'. Use YYYY-MM-DD."))
                return

        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(self.style.SUCCESS("🏦 SOFIZADMIN: STELLAR MIDNIGHT SWEEP & PROFIT ALLOCATION"))
        self.stdout.write(self.style.SUCCESS(f"📅 Target Date: {target_date or timezone.now().date()}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️ Mode: DRY-RUN (Simulation only)"))
        if force:
            self.stdout.write(self.style.ERROR("⚠️ Mode: FORCE (Bypassing audit errors)"))
        self.stdout.write(self.style.SUCCESS("=" * 65))

        if audit_only:
            self.stdout.write("\n🔍 Running Pre-Sweep Safety Audit...")
            audit = StellarSweepService.pre_sweep_audit(target_date=target_date)
            self._print_audit_report(audit)
            return

        self.stdout.write("\n🚀 Starting Sweep Pipeline...")
        result = StellarSweepService.execute_daily_sweep(
            dry_run=dry_run,
            force=force,
            target_date=target_date
        )

        audit = result.get("audit", {})
        self._print_audit_report(audit)

        if result.get("aborted"):
            self.stdout.write(self.style.ERROR("\n🔴 SWEEP ABORTED!"))
            self.stdout.write(self.style.ERROR("Email alert has been dispatched to admin (rabeh2020ken@gmail.com)."))
            for err in result.get("errors", []):
                self.stdout.write(self.style.ERROR(f"  - {err}"))
        elif result.get("success"):
            if dry_run:
                self.stdout.write(self.style.SUCCESS("\n🟢 Dry-Run Audit Completed Successfully! No issues found."))
            else:
                self.stdout.write(self.style.SUCCESS("\n🟢 Sweep Executed Successfully!"))
                for t in result.get("transfers", []):
                    if t.get("success"):
                        self.stdout.write(self.style.SUCCESS(f"  + Transferred {t['amount']:,.2f} DZT | TX: {t.get('tx_hash')}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"  - Transfer failed: {t.get('error')}"))

    def _print_audit_report(self, audit: dict):
        self.stdout.write("\n--- 📊 Audit Summary ---")
        self.stdout.write(f"Epay Today's Profit: {audit.get('today_profit', 0):,.2f} DZD")
        self.stdout.write(f"Epay Today's Sales:  {audit.get('today_sales', 0):,.2f} DZD ({audit.get('today_orders', 0)} orders)")
        self.stdout.write(f"Total Collection DZT: {audit.get('total_collection_dzt', 0):,.2f} DZT")

        sweep_vault = audit.get("sweep_vault")
        profit_vault = audit.get("profit_vault")
        self.stdout.write(f"Daily Sweep Vault:   {sweep_vault.name if sweep_vault else '❌ NOT CONFIGURED'}")
        self.stdout.write(f"Profit Reserve Vault: {profit_vault.name if profit_vault else '❌ NOT CONFIGURED'}")

        self.stdout.write("\n--- 👛 Collection Wallets ---")
        for w in audit.get("collection_wallets", []):
            secret_badge = "Has Secret: YES" if w["has_secret"] else "Has Secret: NO (Needs S... key)"
            self.stdout.write(f"  • {w['name']} | {w['dzt_balance']:,.2f} DZT | {secret_badge}")

        if audit.get("errors"):
            self.stdout.write(self.style.ERROR("\n--- ⚠️ Audit Errors ---"))
            for err in audit["errors"]:
                self.stdout.write(self.style.ERROR(f"  - {err}"))

        if audit.get("warnings"):
            self.stdout.write(self.style.WARNING("\n--- ℹ️ Warnings ---"))
            for warn in audit["warnings"]:
                self.stdout.write(self.style.WARNING(f"  - {warn}"))
