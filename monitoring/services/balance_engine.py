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

        # Auto-evaluate any expired replenishment windows before audit
        try:
            from ..models import G2BulkReplenishmentWindow
            G2BulkReplenishmentWindow.evaluate_and_expire_windows()
        except Exception as e:
            logger.error(f"Error evaluating expired G2Bulk windows: {e}")

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
        for b_acc in binance_accounts:
            b_acc.update_dzd_equivalent()
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

    @classmethod
    def run_esim_audit(cls, sync_live: bool = True) -> dict:
        """
        Executes dedicated audit check for isolated eSIM Subsystem:
        Assets:
        - Bybit Accounts (USDT funding / unified converted to DZD)
        - Airalo Account (Wholesale balance USD converted to DZD)
        - eSIM Stellar Collection Wallet (DZT)
        - In-Transit eSIM Refills (Stages 1 to 3)
        - eSIM Operational Expenses (DZD)
        Capital & Profits:
        - eSIM Initial Working Capital (DZD)
        - eSIM Live Net Profits (DZD)
        Equation:
        Left Side = Bybit DZD + Airalo DZD + eSIM Wallets DZT + In-Transit DZD + eSIM Expenses DZD
        Right Side = eSIM Capital DZD + eSIM Net Profits DZD
        Discrepancy = Left Side - Right Side
        """
        from ..models import (
            BybitAccount,
            AiraloAccount,
            eSIMFundingRecord,
            eSIMFundingStage,
            eSIMOrderRecord,
            SubSystemType,
            OperationalFamily,
            WalletFamily,
            AuditStatus
        )
        from .bybit_service import BybitService
        from .airalo_service import AiraloService

        sync_reports = {"bybit": None, "airalo": None}

        if sync_live:
            try:
                sync_reports["bybit"] = BybitService.sync_account()
            except Exception as e:
                logger.error(f"Failed to sync Bybit in eSIM audit: {e}")

            try:
                sync_reports["airalo"] = AiraloService.sync_account()
            except Exception as e:
                logger.error(f"Failed to sync Airalo in eSIM audit: {e}")

        # 1. Bybit USDT in DZD
        bybit_accounts = BybitAccount.objects.filter(is_active=True)
        bybit_dzd_sum = Decimal("0.00")
        for b_acc in bybit_accounts:
            b_acc.update_dzd_equivalent()
            b_acc.save(update_fields=['balance_dzd_equivalent'])
            bybit_dzd_sum += b_acc.balance_dzd_equivalent

        # 2. Airalo USD in DZD
        airalo_accounts = AiraloAccount.objects.filter(is_active=True)
        airalo_dzd_sum = Decimal("0.00")
        for a_acc in airalo_accounts:
            airalo_dzd_sum += a_acc.balance_dzd_equivalent

        # 3. eSIM Stellar Wallets (DZT) - Collection & Profit
        esim_wallets = StellarWallet.objects.filter(is_active=True, family=WalletFamily.ESIM)
        esim_wallets_dzt = esim_wallets.aggregate(total=Sum('dzt_balance'))['total'] or Decimal("0.00")

        # 4. In-transit eSIM replenishments (Stages 1 to 3)
        in_transit_qs = eSIMFundingRecord.objects.filter(
            stage__in=[
                eSIMFundingStage.BARIDIMOB_DISPATCHED,
                eSIMFundingStage.BINANCE_P2P,
                eSIMFundingStage.BYBIT_FUNDED
            ]
        )
        in_transit_dzd = in_transit_qs.aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")

        # 5. Operational Expenses assigned to eSIM
        esim_expenses = ExpenseRecord.objects.filter(
            system_type=OperationalFamily.ESIM
        ).aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")

        # 6. Available eSIM Cash in Shared BaridiMob Account (Salah)
        salah_allocation = cls.get_salah_baridimob_allocation()
        esim_baridi_available = Decimal(str(salah_allocation['esim']['available_balance_dzd']))
        esim_baridi_expected = Decimal(str(salah_allocation['esim']['expected_balance_dzd']))

        # Left Side Total (Assets + In-Transit + Available BaridiMob + Expenses)
        left_side = (bybit_dzd_sum + airalo_dzd_sum + esim_wallets_dzt + in_transit_dzd + esim_expenses + esim_baridi_available).quantize(Decimal("0.01"))

        # Right Side: Working Capital + Accrued Net Profits
        settings = MonitoringGlobalSettings.get_settings()
        esim_capital = settings.effective_esim_capital
        if esim_capital <= 0:
            esim_capital = CapitalEntry.objects.filter(
                destination_wallet__family=WalletFamily.ESIM
            ).aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")

        esim_profits = eSIMOrderRecord.objects.filter(
            status='COMPLETED'
        ).aggregate(total=Sum('net_profit_dzd'))['total'] or Decimal("0.00")

        right_side = (esim_capital + esim_profits).quantize(Decimal("0.01"))

        discrepancy = (left_side - right_side).quantize(Decimal("0.01"))
        is_balanced = abs(discrepancy) < Decimal("1.00")
        status = AuditStatus.BALANCED if is_balanced else AuditStatus.DISCREPANCY_DETECTED

        return {
            "timestamp": timezone.now(),
            "status": status,
            "is_balanced": is_balanced,
            "discrepancy": discrepancy,
            "bybit_dzd_total": bybit_dzd_sum,
            "airalo_dzd_total": airalo_dzd_sum,
            "esim_wallets_dzt": esim_wallets_dzt,
            "in_transit_dzd": in_transit_dzd,
            "esim_expenses": esim_expenses,
            "esim_baridimob_available": esim_baridi_available,
            "esim_baridimob_expected": esim_baridi_expected,
            "left_side_total": left_side,
            "esim_capital": esim_capital,
            "esim_profits": esim_profits,
            "right_side_total": right_side,
            "sync_reports": sync_reports,
            "salah_allocation": salah_allocation
        }

    @classmethod
    def get_walid_withdrawal_quotas(cls) -> dict:
        """
        Dynamically computes the operational quotas based on the withdrawals
        created and dispatched by Walid (Withdrawal Operations Officer).
        The quotas are NOT fixed ratios, but reflect live withdrawal demand:
        - Gaming Quota: Amount withdrawn/targeted by Walid for Gaming (e.g. 10,000 DZD)
        - eSIM Quota: Amount withdrawn/targeted by Walid for eSIM (e.g. 2,000 DZD)
        - Factures Quota: Amount withdrawn/targeted by Walid for Factures (e.g. 50,000 DZD)
        """
        from ..models import (
            WithdrawalRecord,
            WithdrawalStage,
            SubSystemType,
            eSIMFundingRecord,
            eSIMFundingStage,
        )

        # 1. Gaming withdrawal demand from Walid's active receipts
        active_gaming = WithdrawalRecord.objects.filter(
            system_type=SubSystemType.GAMING,
            stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]
        ).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')

        # 2. eSIM withdrawal demand from Walid's active receipts / fundings
        active_esim_w = WithdrawalRecord.objects.filter(
            system_type=SubSystemType.ESIM,
            stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]
        ).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')
        active_esim_f = eSIMFundingRecord.objects.filter(
            stage__in=[eSIMFundingStage.BARIDIMOB_DISPATCHED, eSIMFundingStage.BINANCE_P2P, eSIMFundingStage.BYBIT_FUNDED]
        ).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')
        active_esim = active_esim_w + active_esim_f

        # 3. Factures / Utility withdrawal demand from Walid's active receipts
        active_factures = WithdrawalRecord.objects.filter(
            system_type=SubSystemType.UTILITY,
            stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]
        ).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')

        return {
            'gaming_target_quota': active_gaming.quantize(Decimal('0.01')),
            'esim_target_quota': active_esim.quantize(Decimal('0.01')),
            'factures_target_quota': active_factures.quantize(Decimal('0.01')),
        }

    @classmethod
    def get_salah_baridimob_allocation(cls) -> dict:
        """
        Computes mathematical breakdown of Salah's shared BaridiMob account
        (RIP: 00799999001738866535) between Gaming and eSIM subsystems:
        1. Operational withdrawal quota for Gaming (Walid)
        2. Operational withdrawal quota for eSIM (Walid)
        3. Real live postal card balance
        4. Real available balance allocated to Gaming vs eSIM
        5. Total reconciliation variance
        """
        from ..models import (
            BaridiMobAccount,
            StellarWallet,
            MonitoringGlobalSettings,
            SupplierAccount,
            BinanceAccount,
            BybitAccount,
            AiraloAccount,
            BaridiMobFundingReceipt,
            FundingCycleStatus,
            WithdrawalRecord,
            WithdrawalStage,
            GameProfitRecord,
            GamingExpenseRecord,
            ExpenseRecord,
            eSIMFundingRecord,
            eSIMFundingStage,
            eSIMOrderRecord,
            WalletFamily,
            OperationalFamily
        )
        settings = MonitoringGlobalSettings.get_settings()

        # 1. Operational Quotas derived from Walid's withdrawals
        quotas = cls.get_walid_withdrawal_quotas()
        expected_gaming = quotas['gaming_target_quota']
        expected_esim = quotas['esim_target_quota']

        gaming_cap = settings.effective_gaming_capital
        db_game_profit = GameProfitRecord.objects.aggregate(t=Sum('net_profit_dzd'))['t'] or Decimal('0.00')
        g_profit = settings.total_live_profits_dzd if settings.total_live_profits_dzd > 0 else (db_game_profit if db_game_profit > 0 else Decimal('0.00'))

        g2bulk_dzd = sum(s.balance_dzd_equivalent for s in SupplierAccount.objects.filter(is_active=True))
        binance_dzd = sum(b.balance_dzd_equivalent for b in BinanceAccount.objects.filter(is_active=True))
        g_wallets_dzt = StellarWallet.objects.filter(family=WalletFamily.GAME, is_active=True).aggregate(t=Sum('dzt_balance'))['t'] or Decimal('0.00')
        g_expenses = GamingExpenseRecord.objects.aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')

        pending_rc = BaridiMobFundingReceipt.objects.filter(status__in=[FundingCycleStatus.PENDING_P2P, FundingCycleStatus.P2P_COMPLETED])
        rc_ids = set(pending_rc.values_list('id', flat=True))
        in_transit_dzd = (pending_rc.aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')) + (
            WithdrawalRecord.objects.filter(stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]).exclude(funding_receipt_id__in=rc_ids).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')
        )
        gaming_external = (g2bulk_dzd + binance_dzd + g_wallets_dzt + in_transit_dzd + g_expenses).quantize(Decimal('0.01'))

        # eSIM external assets
        esim_cap = settings.effective_esim_capital
        esim_profit = (eSIMOrderRecord.objects.filter(status='COMPLETED').aggregate(t=Sum('net_profit_dzd'))['t'] or Decimal('0.00')).quantize(Decimal('0.01'))

        bybit_dzd = sum(b.balance_dzd_equivalent for b in BybitAccount.objects.filter(is_active=True))
        airalo_dzd = sum(a.balance_dzd_equivalent for a in AiraloAccount.objects.filter(is_active=True))
        esim_wallets_dzt = StellarWallet.objects.filter(family=WalletFamily.ESIM, is_active=True).aggregate(t=Sum('dzt_balance'))['t'] or Decimal('0.00')
        esim_expenses = ExpenseRecord.objects.filter(system_type=OperationalFamily.ESIM).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')
        esim_in_transit = eSIMFundingRecord.objects.filter(stage__in=[
            eSIMFundingStage.BARIDIMOB_DISPATCHED, eSIMFundingStage.BINANCE_P2P, eSIMFundingStage.BYBIT_FUNDED
        ]).aggregate(t=Sum('amount_dzd'))['t'] or Decimal('0.00')
        esim_external = (bybit_dzd + airalo_dzd + esim_wallets_dzt + esim_in_transit + esim_expenses).quantize(Decimal('0.01'))

        # Real postal account details (Using official ECCP Extrait de Compte solde)
        salah_acc = BaridiMobAccount.objects.filter(
            models.Q(rip_number__icontains='00799999001738866535') | models.Q(account_name__icontains='salah')
        ).first()
        eccp_solde = salah_acc.eccp_balance_dzd if (salah_acc and salah_acc.eccp_balance_dzd and salah_acc.eccp_balance_dzd > Decimal('0.00')) else Decimal('0.00')
        real_balance = eccp_solde

        expected_total = (expected_gaming + expected_esim).quantize(Decimal('0.01'))
        variance = (real_balance - expected_total).quantize(Decimal('0.01'))

        # Allocation based on Walid's withdrawal requirements:
        # If real_balance covers both quotas, each gets 100% of its Walid withdrawal requirement
        if real_balance >= expected_total:
            available_gaming = expected_gaming
            available_esim = expected_esim
            surplus = real_balance - expected_total
            shortfall = Decimal('0.00')
        elif expected_total > Decimal('0.00'):
            ratio_g = expected_gaming / expected_total
            available_gaming = (real_balance * ratio_g).quantize(Decimal('0.01'))
            available_esim = (real_balance - available_gaming).quantize(Decimal('0.01'))
            surplus = Decimal('0.00')
            shortfall = (expected_total - real_balance).quantize(Decimal('0.01'))
        else:
            available_gaming = Decimal('0.00')
            available_esim = Decimal('0.00')
            surplus = real_balance
            shortfall = Decimal('0.00')

        return {
            'account_id': salah_acc.id if salah_acc else None,
            'account_name': salah_acc.account_name if salah_acc else "Salah Shared Account",
            'rip_number': salah_acc.rip_number if salah_acc else "00799999001738866535",
            'account_email': salah_acc.account_email if salah_acc else "salahsofi",
            'real_balance_dzd': float(real_balance),
            'expected_total_dzd': float(expected_total),
            'variance_dzd': float(variance),
            'is_balanced': abs(variance) <= Decimal('1.00'),
            'surplus_dzd': float(surplus),
            'shortfall_dzd': float(shortfall),
            'gaming': {
                'expected_balance_dzd': float(expected_gaming),
                'available_balance_dzd': float(available_gaming),
                'capital_dzd': float(gaming_cap),
                'profit_dzd': float(g_profit),
                'external_assets_dzd': float(gaming_external),
                'shortfall_dzd': float(max(Decimal('0.00'), expected_gaming - available_gaming)),
            },
            'esim': {
                'expected_balance_dzd': float(expected_esim),
                'available_balance_dzd': float(available_esim),
                'capital_dzd': float(esim_cap),
                'profit_dzd': float(esim_profit),
                'external_assets_dzd': float(esim_external),
                'shortfall_dzd': float(max(Decimal('0.00'), expected_esim - available_esim)),
            }
        }

