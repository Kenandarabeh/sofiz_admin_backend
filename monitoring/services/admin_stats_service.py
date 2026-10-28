"""
Institutional Admin Statistics Service.
Computes real-time cryptographic health, gateway balances, and workflow metrics
for the institutional Django Admin Dashboard and Vite Terminal synchronization.
"""
from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.utils import timezone
from ..models import (
    StellarWallet,
    WalletFamily,
    WalletRole,
    SupplierAccount,
    BaridiMobAccount,
    WithdrawalRecord,
    WithdrawalStage,
    MonitoringGlobalSettings,
    CapitalEntry,
    ExpenseRecord,
    LoginAuditLog
)

User = get_user_model()


class AdminStatsService:
    @classmethod
    def get_dashboard_statistics(cls):
        """
        Gathers high-precision institutional statistics for the Django Admin home dashboard.
        """
        settings = MonitoringGlobalSettings.get_settings()
        now = timezone.now()

        # 1. Cryptographic Wallets & Keypair Health (PK & SK)
        active_wallets = StellarWallet.objects.filter(is_active=True)
        total_wallets = active_wallets.count()
        total_dzt = float(active_wallets.exclude(
            models.Q(family=WalletFamily.TREASURY) | models.Q(role=WalletRole.VAULT) | models.Q(name__icontains='Treasury')
        ).aggregate(total=Sum('dzt_balance'))['total'] or 0)


        wallets_with_sk = 0
        wallets_missing_sk = 0

        for w in active_wallets:
            if w.secret_seed and str(w.secret_seed).strip().startswith('S') and len(str(w.secret_seed).strip()) == 56:
                wallets_with_sk += 1
            else:
                wallets_missing_sk += 1

        # 2. Institutional Gateway Liquidity - Always sync G2Bulk live from official API
        try:
            from .g2bulk_service import G2BulkService
            G2BulkService.sync_supplier()
        except Exception:
            pass
        g2bulk = SupplierAccount.objects.filter(provider='G2BULK').first()
        g2b_usd = float(g2bulk.balance_usd) if g2bulk else 0.0
        g2b_dzd = float(g2bulk.balance_dzd_equivalent) if g2bulk else 0.0
        g2b_synced_at = g2bulk.last_synced_at.strftime('%Y-%m-%d %H:%M') if (g2bulk and g2bulk.last_synced_at) else 'Pending'

        bm_accounts = BaridiMobAccount.objects.filter(is_active=True)
        bm_total_dzd = float(bm_accounts.aggregate(total=Sum('balance_dzd'))['total'] or 0)
        bm_count = bm_accounts.count()

        # 3. Strict 3-Stage Outflow Pipeline Metrics
        stage_1_allocated = WithdrawalRecord.objects.filter(stage=WithdrawalStage.ALLOCATED).count()
        stage_2_p2p = WithdrawalRecord.objects.filter(stage=WithdrawalStage.BINANCE_P2P).count()
        stage_3_completed = WithdrawalRecord.objects.filter(stage=WithdrawalStage.COMPLETED).count()
        total_outflows_dzd = float(WithdrawalRecord.objects.aggregate(total=Sum('amount_dzd'))['total'] or 0)

        # 4. Total Capital Deposited vs Expenses
        total_capital_dzd = float(settings.effective_total_capital)
        total_expenses_dzd = float(ExpenseRecord.objects.aggregate(total=Sum('amount_dzd'))['total'] or 0)

        # 5. Security & Operator Logins
        failed_logins_24h = LoginAuditLog.objects.filter(is_success=False, timestamp__gte=now - timezone.timedelta(hours=24)).count()
        total_staff_users = User.objects.filter(is_staff=True).count()

        return {
            'stellar': {
                'total_dzt_reserve': total_dzt,
                'total_wallets_count': total_wallets,
                'wallets_with_sk': wallets_with_sk,
                'wallets_missing_sk': wallets_missing_sk,
                'horizon_url': settings.stellar_horizon_url,
                'asset_code': settings.dzt_asset_code,
                'asset_issuer': settings.dzt_asset_issuer,
            },
            'gateways': {
                'g2bulk_usd': g2b_usd,
                'g2bulk_dzd': g2b_dzd,
                'g2bulk_synced_at': g2b_synced_at,
                'digital_services_usd': g2b_usd,
                'digital_services_dzd': g2b_dzd,
                'digital_services_synced_at': g2b_synced_at,
                'baridimob_dzd': bm_total_dzd,
                'baridimob_accounts_count': bm_count,
                'epay_live_profits': float(settings.total_live_profits_dzd),
                'epay_live_sales': float(settings.total_live_sales_dzd),
                'exchange_rate': float(settings.usd_to_dzd_exchange_rate),
            },
            'pipeline': {
                'stage_1_allocated': stage_1_allocated,
                'stage_2_p2p': stage_2_p2p,
                'stage_3_completed': stage_3_completed,
                'total_active': stage_1_allocated + stage_2_p2p,
                'total_outflows_dzd': total_outflows_dzd,
                'total_capital_dzd': total_capital_dzd,
                'total_expenses_dzd': total_expenses_dzd,
            },
            'security': {
                'total_staff_users': total_staff_users,
                'failed_logins_24h': failed_logins_24h,
                'is_auto_sync_enabled': settings.is_auto_sync_enabled,
                'last_global_sync': settings.last_global_sync.strftime('%Y-%m-%d %H:%M') if settings.last_global_sync else 'Never',
            }
        }
