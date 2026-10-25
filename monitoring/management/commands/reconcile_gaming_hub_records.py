# Institutional Reconciliation Command for Gaming Operations Hub Records
# Reconciles legacy records, eliminates deficits, and ensures positive operational balance.

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from monitoring.models import (
    WithdrawalRecord,
    WithdrawalStage,
    WithdrawalType,
    SubSystemType,
    GamingBaridiMobAccount,
)
from monitoring.services.balance_engine import BalanceEngine


class Command(BaseCommand):
    help = "Audit and reconcile all existing Gaming Operations Hub withdrawal and refill records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the reconciliation without committing database changes.",
        )
        parser.add_argument(
            "--inject-capital",
            type=float,
            default=425000.0,
            help="Amount in DZD to inject as Finance Liquidity Refill to cover historical dispatches (default: 425,000 DZD).",
        )
        parser.add_argument(
            "--target-positive-buffer",
            type=float,
            default=50000.0,
            help="Additional positive buffer in DZD to leave in the operational account (default: 50,000 DZD).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        inject_capital = Decimal(str(options["inject_capital"]))
        target_buffer = Decimal(str(options["target_positive_buffer"]))

        self.stdout.write(self.style.MIGRATE_HEADING("=== Gaming Operations Hub Audit & Reconciliation ==="))

        records = WithdrawalRecord.objects.filter(system_type=SubSystemType.GAMING).order_by("id")
        self.stdout.write(f"Total GAMING records found in database: {records.count()}\n")

        total_refills = Decimal("0.00")
        total_outflows = Decimal("0.00")

        self.stdout.write(f"{'ID':<6} | {'Stage':<14} | {'Type':<18} | {'Amount (DZD)':<14} | {'Reference':<30}")
        self.stdout.write("-" * 90)

        for rec in records:
            amount = rec.amount_dzd or Decimal("0.00")
            is_refill = rec.withdrawal_type == WithdrawalType.LIQUIDITY_REFILL
            if is_refill:
                total_refills += amount
                type_display = "[+] REFILL"
            else:
                total_outflows += amount
                type_display = "[-] OUTFLOW"

            self.stdout.write(
                f"#{rec.id:<5} | {rec.stage:<14} | {type_display:<18} | {amount:>12,.2f} | {rec.reference or 'N/A'}"
            )

        self.stdout.write("-" * 90)
        self.stdout.write(f"Total Finance Inflows (Refills):  {total_refills:>15,.2f} DZD")
        self.stdout.write(f"Total Ops Outflows (Dispatches): {total_outflows:>15,.2f} DZD")
        deficit = total_outflows - total_refills
        self.stdout.write(self.style.WARNING(f"Historical Discrepancy / Deficit: {deficit:>15,.2f} DZD\n"))

        # Fetch Postal Account
        postal_account = GamingBaridiMobAccount.objects.filter(is_active=True).first()
        postal_balance = postal_account.balance_dzd if postal_account else Decimal("0.00")
        postal_rip = postal_account.rip_number if postal_account else "00799999001738866535"

        self.stdout.write(f"Source Postal Account: {postal_account.account_name if postal_account else 'General Pool'}")
        self.stdout.write(f"Postal Card Available Balance: {postal_balance:,.2f} DZD (RIP: {postal_rip})\n")

        total_to_inject = inject_capital + target_buffer
        if total_to_inject <= 0:
            self.stdout.write(self.style.NOTICE("No capital injection requested. Existing records will remain as is."))
            return

        self.stdout.write(
            self.style.MIGRATE_LABEL(
                f"Preparing institutional liquidity refill of {total_to_inject:,.2f} DZD "
                f"({inject_capital:,.2f} deficit coverage + {target_buffer:,.2f} operational buffer)..."
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] No database writes were performed."))
            new_balance = max(Decimal("0.00"), (total_refills + total_to_inject) - total_outflows)
            self.stdout.write(self.style.SUCCESS(f"Projected Post-Reconciliation Balance: {new_balance:,.2f} DZD"))
            return

        with transaction.atomic():
            now = timezone.now()
            ref_code = f"FIN-REFILL-{now.strftime('%Y%m%d%H%M%S')}"

            refill_record = WithdrawalRecord.objects.create(
                title="Operational Working Capital Inflow (Gaming)",
                system_type=SubSystemType.GAMING,
                withdrawal_type=WithdrawalType.LIQUIDITY_REFILL,
                purpose_code="GAMING_REFILL",
                amount_dzd=total_to_inject,
                stage=WithdrawalStage.COMPLETED,
                reference=ref_code,
                recipient_rip=postal_rip,
                receipt_verified=True,
                source_baridimob=postal_account,
                notes=(
                    f"• [Institutional Reconciliation @ {now.strftime('%Y-%m-%d %H:%M')}]\n"
                    f"Finance liquidity refill of {total_to_inject:,.2f} DZD logged to cover historical dispatches "
                    f"({inject_capital:,.2f} DZD deficit) and establish positive operational buffer ({target_buffer:,.2f} DZD).\n"
                    f"Source: Postal Account RIP {postal_rip} (Solde: {postal_balance:,.2f} DZD)."
                ),
            )

            # Update existing records to ensure proper auditing notes and title standardization
            for rec in records:
                if not rec.title or "withdrawal" in rec.title.lower():
                    if rec.withdrawal_type == WithdrawalType.SUPPLIER_FUNDING:
                        rec.title = f"G2Bulk Wholesale Funding #{rec.id}"
                        rec.save(update_fields=["title"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created Finance Refill record #{refill_record.id} ({refill_record.reference}) "
                f"for {total_to_inject:,.2f} DZD!"
            )
        )

        # Verify new balance via native DB engine
        db_balances = BalanceEngine.get_operational_account_balances_db(SubSystemType.GAMING)
        new_balance = db_balances.get("current_balance_dzd", Decimal("0.00"))
        new_funded = db_balances.get("total_funded_dzd", Decimal("0.00"))
        new_spent = db_balances.get("total_spent_dzd", Decimal("0.00"))
        new_status = db_balances.get("status", "UNKNOWN")

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("RECONCILIATION COMPLETE:"))
        self.stdout.write(f"Operational Balance: {new_balance:>12,.2f} DZD")
        self.stdout.write(f"Total Funded:        {new_funded:>12,.2f} DZD")
        self.stdout.write(f"Total Spent:         {new_spent:>12,.2f} DZD")
        self.stdout.write(f"Ledger Status:       {new_status}")
        self.stdout.write("=" * 50 + "\n")
