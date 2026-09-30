"""
Golden Balance Equation Engine for SofizAdmin
Formula:
[Stellar DZT Balances + G2Bulk (DZD) + BaridiMob (DZD)] + [Total Expenses] = [Total Capital Inflows] + [Total Game Profits]
"""
import logging
from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from ..models import (
    StellarWallet,
    SupplierAccount,
    BaridiMobAccount,
    CapitalEntry,
    ExpenseRecord,
    GameProfitRecord,
    BalanceAuditLog,
    MonitoringGlobalSettings,
    BaridiMobFundingReceipt,
    FundingCycleStatus,
    WithdrawalRecord,
    WithdrawalStage
)
from .stellar_service import StellarService
from .g2bulk_service import G2BulkService
from .epay_service import EpaySyncService
from .email_alerts import EmailAlertService

logger = logging.getLogger(__name__)


class BalanceEngine:
    @classmethod
    def run_audit(cls, sync_live: bool = True, send_alerts: bool = True) -> dict:
        """
        Executes a periodic financial audit check.
        1. Syncs live Stellar Horizon wallet balances.
        2. Syncs live G2Bulk supplier balance.
        3. Syncs recent completed game orders and profit margins from Epay.
        4. Calculates the Golden Balance equation.
        5. Logs the audit record and dispatches email alerts if discrepancy is detected.
        """
        sync_reports = {"stellar": [], "g2bulk": None, "epay_profits": None}

        if sync_live:
            # 1. Sync live Stellar Wallets (DZT)
            sync_reports["stellar"] = StellarService.sync_all_wallets()
            
            # 2. Sync live G2Bulk Supplier Account
            sync_reports["g2bulk"] = G2BulkService.sync_supplier()

            # 3. Sync live BaridiMob Settlement Account
            from .baridimob_service import BaridiMobService
            sync_reports["baridimob"] = BaridiMobService.sync_baridi_balance()

            # 4. Sync live game profits from Epay
            sync_reports["epay_profits"] = EpaySyncService.sync_game_profits_from_epay()

            # 5. Sync live utility bills & commissions from Epay
            try:
                sync_reports["utility_bills"] = EpaySyncService.sync_utility_bills()
            except Exception as e:
                logger.error(f"Failed to sync utility bills: {e}")
            
            # Update settings last sync timestamp
            settings = MonitoringGlobalSettings.get_settings()
            settings.last_global_sync = timezone.now()
            settings.save(update_fields=['last_global_sync'])

        # Aggregate Balances (Assets) - Exclude Central Master Treasury Issuer Vault
        from ..models import WalletFamily, WalletRole
        dzt_sum = StellarWallet.objects.filter(is_active=True).exclude(
            models.Q(family=WalletFamily.TREASURY) | models.Q(role=WalletRole.VAULT) | models.Q(name__icontains='Treasury')
        ).aggregate(total=Sum('dzt_balance'))['total'] or Decimal("0.00")

        
        # Ensure supplier DZD equivalent is refreshed
        suppliers = SupplierAccount.objects.filter(is_active=True)
        g2bulk_dzd_sum = Decimal("0.00")
        for sup in suppliers:
            sup.update_dzd_equivalent()
            sup.save(update_fields=['balance_dzd_equivalent'])
            g2bulk_dzd_sum += sup.balance_dzd_equivalent

            # Check low balance threshold alert
            if send_alerts and sup.balance_usd < Decimal("50.00"):
                EmailAlertService.send_low_balance_alert(
                    provider_name=sup.name,
                    current_balance=sup.balance_usd,
                    threshold=Decimal("50.00"),
                    currency="USD"
                )

        # Aggregate BaridiMob Working Capital for Utility Bills
        baridi_accounts = BaridiMobAccount.objects.filter(is_active=True)
        baridimob_sum = Decimal("0.00")
        glitched_accounts = []
        for b_acc in baridi_accounts:
            if getattr(b_acc, 'is_glitch_quarantined', False):
                # Institutional Protection: Use last verified stable balance to protect Golden Equation from Algérie Poste server anomalies
                effective_b = b_acc.last_stable_balance if b_acc.last_stable_balance > Decimal("0.00") else max(Decimal("0.00"), b_acc.balance_dzd)
                baridimob_sum += effective_b
                glitched_accounts.append(b_acc)
            else:
                baridimob_sum += max(Decimal("0.00"), b_acc.balance_dzd)
        baridimob_sum = baridimob_sum.quantize(Decimal("0.01"))

        # Aggregate Binance Corporate Crypto Accounts (USDT Reserves & Balances)
        from ..models import BinanceAccount
        binance_accounts = BinanceAccount.objects.filter(is_active=True)
        binance_dzd_sum = Decimal("0.00")
        settings = MonitoringGlobalSettings.get_settings()
        for b_acc in binance_accounts:
            b_acc.update_dzd_equivalent(settings.usd_to_dzd_exchange_rate)
            b_acc.save(update_fields=['balance_dzd_equivalent'])
            binance_dzd_sum += b_acc.balance_dzd_equivalent
        binance_dzd_sum = binance_dzd_sum.quantize(Decimal("0.01"))

        # Aggregate In-Transit Funding Refills (Pending P2P or In-Custody for G2Bulk)
        pending_receipts = BaridiMobFundingReceipt.objects.filter(
            status__in=[FundingCycleStatus.PENDING_P2P, FundingCycleStatus.P2P_COMPLETED]
        )
        receipts_in_transit = pending_receipts.aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")
        counted_receipt_ids = set(pending_receipts.values_list('id', flat=True))

        pending_withdrawals = WithdrawalRecord.objects.filter(
            stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]
        ).exclude(funding_receipt_id__in=counted_receipt_ids)
        withdrawals_in_transit = pending_withdrawals.aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")

        in_transit_sum = (receipts_in_transit + withdrawals_in_transit).quantize(Decimal("0.01"))

        total_assets = (dzt_sum + g2bulk_dzd_sum + binance_dzd_sum + baridimob_sum + in_transit_sum).quantize(Decimal("0.01"))

        # Aggregate Expenses
        expenses_sum = (ExpenseRecord.objects.aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")).quantize(Decimal("0.01"))

        # Left side = Total Assets + Total Expenses
        left_side = (total_assets + expenses_sum).quantize(Decimal("0.01"))

        # Aggregate Capital Inflows (Direct Admin Control or Capital Entries)
        settings = MonitoringGlobalSettings.get_settings()
        capital_sum = settings.effective_total_capital

        # Aggregate Game Profits (from live Epay API)
        local_db_profits = GameProfitRecord.objects.aggregate(total=Sum('net_profit_dzd'))['total'] or Decimal("0.00")
        profits_sum = (settings.total_live_profits_dzd if settings.total_live_profits_dzd > 0 else local_db_profits).quantize(Decimal("0.01"))

        # Right side = Capital + Profits
        right_side = (capital_sum + profits_sum).quantize(Decimal("0.01"))

        # Discrepancy
        discrepancy = (left_side - right_side).quantize(Decimal("0.01"))
        
        # Consider balanced if discrepancy is practically zero (<= 0.05 DZD tolerance)
        is_balanced = abs(discrepancy) <= Decimal("0.05")
        status = 'BALANCED' if is_balanced else 'DISCREPANCY_DETECTED'

        notes_parts = []
        if is_balanced:
            notes_parts.append("Financial balance is 100% verified. Zero discrepancy detected.")
        else:
            if discrepancy > 0:
                notes_parts.append(f"Alert: Assets and expenses exceed capital and profits by {discrepancy:,.2f} DZT (possible unrecorded inflow).")
            else:
                notes_parts.append(f"Critical Alert: Asset deficit of {abs(discrepancy):,.2f} DZT (possible fund leakage, unrecorded expense, or failed order).")

        if in_transit_sum > 0:
            notes_parts.append(f"In-Transit Pipeline: {in_transit_sum:,.2f} DZD currently active across P2P / G2Bulk replenishment workflow.")

        if glitched_accounts:
            for g_acc in glitched_accounts:
                notes_parts.append(
                    f"⚠️ Algérie Poste Glitch Quarantined: Account [{g_acc.account_name}] reported postal anomaly balance of {g_acc.quarantined_glitch_amount:,.2f} DZD. "
                    f"Quarantined with stable balance {g_acc.last_stable_balance:,.2f} DZD to preserve Golden Balance integrity."
                )

        audit_log = BalanceAuditLog.objects.create(
            total_dzt_wallets=dzt_sum.quantize(Decimal("0.01")),
            total_g2bulk_dzd=g2bulk_dzd_sum.quantize(Decimal("0.01")),
            total_baridimob_dzd=baridimob_sum.quantize(Decimal("0.01")),
            total_in_transit_dzd=in_transit_sum,
            total_assets_dzd=total_assets,
            total_expenses_dzd=expenses_sum,
            left_side_total=left_side,
            total_capital_dzd=capital_sum,
            total_profits_dzd=profits_sum,
            right_side_total=right_side,
            discrepancy_dzd=discrepancy,
            status=status,
            notes="\n".join(notes_parts)
        )

        # Dispatch Email Alert on discrepancy
        if send_alerts and not is_balanced:
            EmailAlertService.send_discrepancy_alert(discrepancy, audit_log)

        return {
            "timestamp": audit_log.checked_at,
            "status": status,
            "is_balanced": is_balanced,
            "discrepancy": discrepancy,
            "dzt_wallets_total": dzt_sum,
            "g2bulk_dzd_total": g2bulk_dzd_sum,
            "baridimob_dzd_total": baridimob_sum,
            "in_transit_dzd_total": in_transit_sum,
            "total_assets": total_assets,
            "total_expenses": expenses_sum,
            "left_side_total": left_side,
            "total_capital": capital_sum,
            "total_profits": profits_sum,
            "right_side_total": right_side,
            "sync_reports": sync_reports,
            "audit_id": audit_log.id,
            "notes": "\n".join(notes_parts)
        }
