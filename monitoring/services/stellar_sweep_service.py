"""
Stellar Daily Sweep & Profit Reserve Service for SofizAdmin
Handles:
1. Midnight automated reconciliation (Epay daily profits & sales vs. Stellar collection wallets).
2. Segregated transfers:
   - Daily net profits from Epay -> Profit Reserve Vault Wallet
   - Remaining operational balance -> Daily Sweep Vault Wallet
3. Pre-sweep safety audit & instant email alerts on discrepancy or failure (rabeh2020ken@gmail.com).
"""
import logging
from decimal import Decimal
from datetime import datetime, date
from django.db import models
from django.utils import timezone
from django.conf import settings as dj_settings
from ..models import (
    StellarWallet,
    GamingWallet,
    SweepVaultWallet,
    ProfitVaultWallet,
    WalletSweepLog,
    MonitoringGlobalSettings,
    WalletFamily,
    WalletRole
)
from .stellar_service import StellarService
from .epay_service import EpaySyncService
from .email_alerts import EmailAlertService
from .sofizpay_debug import send_email, get_alert_recipients

logger = logging.getLogger(__name__)


class StellarSweepService:

    @staticmethod
    def _match_wallet_game_key(wallet_name: str) -> str:
        """Helper to match a Stellar operational collection wallet to its ePay game key"""
        name_l = str(wallet_name).lower()
        if 'free fire' in name_l or 'freefire' in name_l:
            return 'freefire'
        elif 'pubg' in name_l:
            return 'pubg'
        elif 'app' in name_l:
            return 'app'
        elif 'game' in name_l:
            return 'game'
        return 'other'

    @classmethod
    def pre_sweep_audit(cls, target_date: date = None, family: str = 'GAME') -> dict:
        """
        Pre-flight audit before midnight sweep:
        1. Queries Epay API for today's completed sales and net profit (filtered by system and game breakdown).
        2. Syncs and inspects operational collection wallets.
        3. Calculates precise per-wallet profit allocation and remaining operational capital.
        4. Validates that Sweep Vault and Profit Vault wallets are configured.
        5. Validates secret keys (S...).
        6. Checks for financial discrepancies.
        """
        if target_date is None:
            target_date = timezone.now().date()
        date_str = target_date.strftime('%Y-%m-%d')

        errors = []
        warnings = []
        settings = MonitoringGlobalSettings.get_settings()

        # 1. Fetch Today's metrics from Epay API (Focus on GAMING system with game breakdown)
        epay_product = 'gaming' if family == 'GAME' else 'all'
        epay_data = EpaySyncService.sync_financial_summary(product=epay_product, from_date=date_str, to_date=date_str)
        today_profit = Decimal("0.00")
        today_sales = Decimal("0.00")
        today_orders = 0
        breakdown = {}

        if epay_data.get("success"):
            systems = epay_data.get("systems") or epay_data.get("raw", {}).get("systems") or {}
            breakdown = epay_data.get("breakdown") or {}
            gaming_stats = systems.get("GAMING") if family == 'GAME' else None
            if gaming_stats:
                today_profit = Decimal(str(gaming_stats.get("net_profit_dzd", 0.0)))
                today_sales = Decimal(str(gaming_stats.get("total_sales_dzd", 0.0)))
                today_orders = int(gaming_stats.get("orders_count", 0))
            else:
                today_profit = Decimal(str(epay_data.get("total_profit_dzd", 0.0)))
                today_sales = Decimal(str(epay_data.get("total_sales_dzd", 0.0)))
                today_orders = int(epay_data.get("total_orders", 0))
        else:
            err = f"Failed to fetch daily financial summary from Epay: {epay_data.get('error')}"
            errors.append(err)
            logger.error(err)

        # 2. Check Destination Vault Wallets (Per-Family or Central Vaults)
        if family == 'GAME':
            profit_vault = (
                StellarWallet.objects.filter(family=WalletFamily.GAME, role=WalletRole.PROFIT, is_active=True).first() or
                StellarWallet.objects.filter(role=WalletRole.PROFIT, is_active=True).first()
            )
            sweep_vault = (
                StellarWallet.objects.filter(family=WalletFamily.GAME, role=WalletRole.WITHDRAWAL, is_active=True).first() or
                StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.VAULT, is_active=True).first()
            )
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.GAME,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        elif family in ['FACTURE', 'UTILITY']:
            profit_vault = (
                StellarWallet.objects.filter(family=WalletFamily.FACTURE, role=WalletRole.PROFIT, is_active=True).first() or
                StellarWallet.objects.filter(role=WalletRole.PROFIT, is_active=True).first()
            )
            sweep_vault = (
                StellarWallet.objects.filter(family=WalletFamily.FACTURE, role=WalletRole.WITHDRAWAL, is_active=True).first() or
                StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.VAULT, is_active=True).first()
            )
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.FACTURE,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        elif family == 'ESIM':
            profit_vault = (
                StellarWallet.objects.filter(family=WalletFamily.ESIM, role=WalletRole.PROFIT, is_active=True).first() or
                StellarWallet.objects.filter(role=WalletRole.PROFIT, is_active=True).first()
            )
            sweep_vault = (
                StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.VAULT, is_active=True).first() or
                StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, is_active=True).first()
            )
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.ESIM,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        elif family == 'IDOOM':
            profit_vault = (
                StellarWallet.objects.filter(family=WalletFamily.IDOOM, role=WalletRole.PROFIT, is_active=True).first() or
                StellarWallet.objects.filter(role=WalletRole.PROFIT, is_active=True).first()
            )
            sweep_vault = (
                StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.VAULT, is_active=True).first() or
                StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, is_active=True).first()
            )
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.IDOOM,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        else:
            sweep_vault = (
                StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.VAULT, is_active=True).first() or
                StellarWallet.objects.filter(category='SWEEP_VAULT', is_active=True).first() or
                StellarWallet.objects.filter(category='TREASURY', is_active=True).first()
            )
            profit_vault = (
                StellarWallet.objects.filter(role=WalletRole.PROFIT, is_active=True).first() or
                StellarWallet.objects.filter(category='PROFIT_VAULT', is_active=True).first()
            )
            collection_wallets = list(StellarWallet.objects.filter(
                role=WalletRole.COLLECTION,
                is_active=True
            ))

        if not sweep_vault:
            errors.append("⚠️ Sweep destination wallet is NOT configured or inactive. Please activate a Games Withdrawal Wallet or Master Vault.")
        if not profit_vault:
            errors.append("⚠️ Profit Reserve Vault wallet is NOT configured or inactive. Please activate a Games Profit Wallet or Profit Reserve.")

        if not collection_wallets:
            warnings.append(f"No active operational collection wallets found for family '{family}'.")

        total_collection_dzt = Decimal("0.0000")
        total_ready_collection_dzt = Decimal("0.0000")
        total_profit_to_allocate = Decimal("0.0000")
        total_capital_to_sweep = Decimal("0.0000")
        wallets_audit_info = []

        for w in collection_wallets:
            sync_res = StellarService.sync_wallet(w)
            dzt_bal = w.dzt_balance or Decimal("0.0000")
            total_collection_dzt += dzt_bal

            has_secret = bool(w.secret_seed and str(w.secret_seed).strip().startswith('S') and len(str(w.secret_seed).strip()) == 56)
            total_ready_collection_dzt += dzt_bal
            if not has_secret and dzt_bal > 0:
                warnings.append(f"Wallet '{w.name}' will be swept via Audited Internal Ledger mode (no secret seed configured).")

            # Game breakdown matching & profit/capital calculation for today's operations
            game_key = cls._match_wallet_game_key(w.name)
            game_metrics = breakdown.get(game_key, {})
            game_sales = Decimal(str(game_metrics.get("sales_dzd", 0.0)))
            game_profit = Decimal(str(game_metrics.get("profit_dzd", 0.0)))
            game_cost = Decimal(str(game_metrics.get("cost_dzd", 0.0)))
            if game_cost <= Decimal("0.0000") and game_sales > game_profit:
                game_cost = game_sales - game_profit

            # Allocate strictly today's profit and today's capital up to the wallet's available balance
            profit_for_wallet = min(game_profit, dzt_bal).quantize(Decimal("0.0001"))
            remaining_after_profit = max(Decimal("0.0000"), dzt_bal - profit_for_wallet)
            capital_for_wallet = min(game_cost, remaining_after_profit).quantize(Decimal("0.0001"))

            total_profit_to_allocate += profit_for_wallet
            total_capital_to_sweep += capital_for_wallet

            w_info = {
                "id": w.id,
                "name": w.name,
                "public_address": w.public_address,
                "dzt_balance": dzt_bal,
                "game_key": game_key,
                "today_sales": game_sales,
                "epay_game_profit": game_profit,
                "profit_to_allocate": profit_for_wallet,
                "capital_to_sweep": capital_for_wallet,
                "total_today_sweep": profit_for_wallet + capital_for_wallet,
                "has_secret": has_secret,
                "mode": "ON_CHAIN" if has_secret else "INTERNAL_LEDGER",
                "error": sync_res.get("error")
            }
            wallets_audit_info.append(w_info)

        # Fallback allocation for products without game-specific breakdown
        unallocated_profit = max(Decimal("0.0000"), today_profit - total_profit_to_allocate)
        if unallocated_profit > Decimal("0.0000"):
            for w_info in wallets_audit_info:
                if unallocated_profit <= Decimal("0.0000"):
                    break
                rem_bal = max(Decimal("0.0000"), w_info["dzt_balance"] - w_info["profit_to_allocate"] - w_info["capital_to_sweep"])
                if rem_bal > Decimal("0.0000"):
                    extra_p = min(unallocated_profit, rem_bal).quantize(Decimal("0.0001"))
                    w_info["profit_to_allocate"] += extra_p
                    total_profit_to_allocate += extra_p
                    unallocated_profit -= extra_p

        # 4. Discrepancy Check (Epay vs. Wallets)
        if today_profit > 0 and total_ready_collection_dzt < today_profit:
            diff = today_profit - total_ready_collection_dzt
            errors.append(
                f"🔴 Discrepancy Detected: Epay reports today's profit as {today_profit:,.2f} DZD, "
                f"but total ready DZT available across sweepable wallets is only {total_ready_collection_dzt:,.2f} DZT! (Shortfall: {diff:,.2f} DZT)."
            )

        can_proceed = len(errors) == 0

        sweep_vault_info = {
            "id": sweep_vault.id,
            "name": sweep_vault.name,
            "public_address": sweep_vault.public_address,
            "dzt_balance": float(sweep_vault.dzt_balance),
        } if sweep_vault else None

        profit_vault_info = {
            "id": profit_vault.id,
            "name": profit_vault.name,
            "public_address": profit_vault.public_address,
            "dzt_balance": float(profit_vault.dzt_balance),
        } if profit_vault else None

        return {
            "can_proceed": can_proceed,
            "date": date_str,
            "family": family,
            "today_profit": today_profit,
            "today_sales": today_sales,
            "today_orders": today_orders,
            "breakdown": breakdown,
            "total_collection_dzt": total_collection_dzt,
            "total_ready_collection_dzt": total_ready_collection_dzt,
            "total_profit_to_allocate": total_profit_to_allocate,
            "total_capital_to_sweep": total_capital_to_sweep,
            "sweep_vault": sweep_vault_info,
            "profit_vault": profit_vault_info,
            "sweep_vault_obj": sweep_vault,
            "profit_vault_obj": profit_vault,
            "collection_wallets": wallets_audit_info,
            "errors": errors,
            "warnings": warnings,
        }

    @classmethod
    def send_sweep_failure_alert(cls, audit_result: dict, context_msg: str = "") -> bool:
        """
        Sends an immediate high-priority email alert to rabeh2020ken@gmail.com and admins
        when the daily sweep cannot proceed or encounters errors.
        """
        recipients = get_alert_recipients()
        date_str = audit_result.get("date", timezone.now().strftime('%Y-%m-%d'))
        subject = f"🚨 [SofizAdmin Alert] Stellar Daily Sweep & Profit Segregation Failed ({date_str})"

        errors_html = "".join([f"<li style='color: #b91c1c; font-weight: bold; margin-bottom: 6px;'>{err}</li>" for err in audit_result.get("errors", [])])
        warnings_html = "".join([f"<li style='color: #d97706; margin-bottom: 4px;'>{warn}</li>" for warn in audit_result.get("warnings", [])])

        wallets_rows = ""
        for w in audit_result.get("collection_wallets", []):
            status_badge = "🟢 Ready" if w["has_secret"] else "🔴 Missing SK"
            wallets_rows += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #e2e8f0;">{w['name']}</td>
                <td style="padding: 8px; border: 1px solid #e2e8f0; font-family: monospace;">{w['public_address'][:8]}...{w['public_address'][-6:]}</td>
                <td style="padding: 8px; border: 1px solid #e2e8f0; font-weight: bold;">{w['dzt_balance']:,.2f} DZT</td>
                <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{status_badge}</td>
            </tr>
            """

        html_body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 700px; margin: 0 auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
            <div style="background: #991b1b; color: #fff; padding: 20px 24px;">
                <h2 style="margin: 0; font-size: 20px;">🚨 Critical Alert: Daily Sweep Automatically Aborted</h2>
                <p style="margin: 6px 0 0 0; opacity: 0.9; font-size: 14px;">Date: {date_str} | Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
            
            <div style="padding: 24px;">
                <p style="font-size: 15px; line-height: 1.6; color: #1e293b;">
                    Pre-sweep safety audit detected discrepancies or critical configuration errors. 
                    <strong>The sweep execution has been halted immediately</strong> to prevent financial leakage or unverified transfers.
                </p>

                <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 14px 18px; margin: 18px 0; border-radius: 4px;">
                    <h4 style="margin: 0 0 8px 0; color: #991b1b; font-size: 15px;">Detected Errors:</h4>
                    <ul style="margin: 0; padding-left: 20px;">
                        {errors_html}
                    </ul>
                </div>

                <h4 style="color: #334155; margin: 20px 0 10px 0;">📊 Balance & Reconciliation Summary:</h4>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13.5px;">
                    <tr style="background: #f8fafc;">
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: left;">Item</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">Amount / Value</th>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Today's Epay Reported Net Profit:</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; font-weight: bold; color: #16a34a; text-align: right;">{audit_result.get('today_profit', 0):,.2f} DZD</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Today's Epay Sales ({audit_result.get('today_orders', 0)} orders):</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">{audit_result.get('today_sales', 0):,.2f} DZD</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Total DZT Available in Collection Wallets:</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; font-weight: bold; color: #2563eb; text-align: right;">{audit_result.get('total_collection_dzt', 0):,.2f} DZT</td>
                    </tr>
                </table>

                <h4 style="color: #334155; margin: 20px 0 10px 0;">👛 Collection Wallets Status:</h4>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <tr style="background: #f8fafc;">
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: left;">Wallet</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: left;">Address</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">DZT Balance</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">Status</th>
                    </tr>
                    {wallets_rows}
                </table>

                <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #64748b;">
                    Please review the admin panel to resolve issues: <a href="http://127.0.0.1:8000/admin/monitoring/stellarwallet/" style="color: #2563eb;">Stellar Wallets Admin</a>
                </div>
            </div>
        </div>
        """

        text_body = f"""
        [SofizAdmin Critical Alert] Stellar Daily Sweep & Profit Segregation Failed ({date_str})
        
        Detected Errors:
        {chr(10).join(audit_result.get('errors', []))}
        
        Today Epay Profit: {audit_result.get('today_profit', 0):,.2f} DZD
        Total Collection DZT: {audit_result.get('total_collection_dzt', 0):,.2f} DZT
        
        Sweep execution has been halted until issues are resolved.
        """

        return send_email(recipients, subject, text_body, html_message=html_body)

    @classmethod
    def execute_daily_sweep(cls, dry_run: bool = False, force: bool = False, target_date: date = None, family: str = 'ALL') -> dict:
        """
        Executes the midnight sweep across all institutional wallet stages:
        1. Runs pre_sweep_audit.
        2. If audit fails and not force: aborts and sends email alert.
        3. If audit passes (or force=True):
           - Stage 1: Transfer Profit Allocation (strictly 1.0000 DZT) to dedicated Family Profit Wallet.
           - Stage 2: Transfer Operational Sweep (strictly 1.0000 DZT) to dedicated Family Withdrawal Wallet.
           - Stage 3: Transfer Operational Consolidation (strictly 1.0000 DZT) from Family Withdrawal Wallet to Central Treasury Vault.
        """
        audit = cls.pre_sweep_audit(target_date=target_date, family=family)

        if not audit["can_proceed"] and not force:
            logger.warning(f"Aborting daily sweep due to pre-flight audit failures: {audit['errors']}")
            cls.send_sweep_failure_alert(audit)

            # Record aborted log
            WalletSweepLog.objects.create(
                amount_dzt=Decimal("0.0000"),
                sweep_type='SWEEP_TRANSFER',
                epay_reported_profit=audit.get("today_profit"),
                epay_reported_sales=audit.get("today_sales"),
                status='ABORTED_DISCREPANCY',
                error_details="\n".join(audit["errors"])
            )

            return {
                "success": False,
                "aborted": True,
                "errors": audit["errors"],
                "audit": audit
            }

        sweep_vault = audit.get("sweep_vault_obj")
        profit_vault = audit.get("profit_vault_obj")
        today_profit = audit["today_profit"]
        remaining_profit_to_allocate = today_profit
        executed_transfers = []

        if dry_run:
            logger.info("DRY-RUN MODE: No Stellar transactions will be submitted to Horizon.")
            return {
                "success": True,
                "dry_run": True,
                "audit": audit,
                "message": "Dry-run audit passed successfully."
            }

        # Setup Stellar SDK Horizon Server
        import stellar_sdk
        from stellar_sdk import Server, Keypair, TransactionBuilder, Network, Asset

        settings = MonitoringGlobalSettings.get_settings()
        horizon_url = settings.stellar_horizon_url.rstrip('/')
        server = Server(horizon_url=horizon_url)
        dzt_asset = Asset(settings.dzt_asset_code, settings.dzt_asset_issuer)

        if family == 'GAME':
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.GAME,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        elif family in ['FACTURE', 'UTILITY']:
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.FACTURE,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        elif family == 'ESIM':
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.ESIM,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        elif family == 'IDOOM':
            collection_wallets = list(StellarWallet.objects.filter(
                family=WalletFamily.IDOOM,
                role=WalletRole.COLLECTION,
                is_active=True
            ))
        else:
            collection_wallets = list(StellarWallet.objects.filter(
                role=WalletRole.COLLECTION,
                is_active=True
            ))

        # Date string for audit memos
        date_memo_str = str(audit.get('date', timezone.now().date()))

        # Map wallet allocations from pre_sweep_audit
        wallet_alloc_map = {
            w_info["id"]: w_info
            for w_info in audit.get("collection_wallets", [])
        }

        for wallet in collection_wallets:
            if wallet.dzt_balance <= Decimal("0.0000"):
                continue

            # Resolve Dedicated Family Profit and Sweep Destinations
            family_profit_dest = (
                StellarWallet.objects.filter(family=wallet.family, role=WalletRole.PROFIT, is_active=True).first() or
                profit_vault
            )
            family_sweep_dest = (
                StellarWallet.objects.filter(family=wallet.family, role=WalletRole.WITHDRAWAL, is_active=True).first() or
                sweep_vault
            )

            w_alloc = wallet_alloc_map.get(wallet.id, {})
            profit_amt = w_alloc.get("profit_to_allocate", Decimal("0.0000"))

            # Stage 1: Transfer Exact Calculated Profit Allocation to Family Profit Wallet
            if family_profit_dest and profit_amt > Decimal("0.0000") and wallet.dzt_balance >= profit_amt:
                res_profit = StellarService.send_payment(
                    source_wallet=wallet,
                    destination_wallet=family_profit_dest,
                    amount=profit_amt,
                    memo_text=f"PROFIT-{date_memo_str}"[:28],
                    sweep_type='PROFIT_TRANSFER'
                )
                executed_transfers.append(res_profit)

            # Refresh wallet balance from database before Stage 2
            wallet.refresh_from_db()

            # Stage 2: Operational Capital Sweep to Family Withdrawal Wallet (strictly today's operational cost)
            capital_amt = w_alloc.get("capital_to_sweep", Decimal("0.0000"))
            if family_sweep_dest and capital_amt > Decimal("0.0000") and wallet.dzt_balance >= capital_amt:
                res_sweep = StellarService.send_payment(
                    source_wallet=wallet,
                    destination_wallet=family_sweep_dest,
                    amount=capital_amt,
                    memo_text=f"SWEEP-{date_memo_str}"[:28],
                    sweep_type='SWEEP_TRANSFER'
                )
                executed_transfers.append(res_sweep)

        # Refresh wallet balances
        StellarService.sync_all_wallets()

        # Clean model instances so audit is 100% JSON serializable
        audit.pop("sweep_vault_obj", None)
        audit.pop("profit_vault_obj", None)

        return {
            "success": True,
            "aborted": False,
            "audit": audit,
            "transfers": executed_transfers
        }

    @classmethod
    def _submit_stellar_payment(
        cls,
        server,
        source_wallet: StellarWallet,
        destination_address: str,
        destination_wallet: StellarWallet,
        asset,
        amount: Decimal,
        sweep_type: str,
        reported_profit: Decimal = None,
        reported_sales: Decimal = None
    ) -> dict:
        """Submits a signed DZT payment on Stellar network and logs result"""
        from stellar_sdk import Keypair, TransactionBuilder, Network

        amount_str = f"{amount:.4f}"
        log_entry = WalletSweepLog.objects.create(
            source_wallet=source_wallet,
            destination_wallet=destination_wallet,
            amount_dzt=amount,
            sweep_type=sweep_type,
            epay_reported_profit=reported_profit,
            epay_reported_sales=reported_sales,
            status='FAILED'
        )

        try:
            source_keypair = Keypair.from_secret(source_wallet.secret_seed.strip())
            source_account = server.load_account(source_keypair.public_key)

            base_fee = server.fetch_base_fee()
            tx = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                    base_fee=base_fee,
                )
                .append_payment_op(
                    destination=destination_address.strip(),
                    asset=asset,
                    amount=amount_str,
                )
                .set_timeout(30)
                .build()
            )

            tx.sign(source_keypair)
            response = server.submit_transaction(tx)

            tx_hash = response.get('hash', '')
            log_entry.stellar_tx_hash = tx_hash
            log_entry.status = 'SUCCESS'
            log_entry.save(update_fields=['stellar_tx_hash', 'status'])

            logger.info(f"Stellar payment successful! [{sweep_type}] {amount_str} DZT -> {destination_address} (TX: {tx_hash})")
            return {
                "success": True,
                "amount": amount,
                "tx_hash": tx_hash,
                "log_id": log_entry.id
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Stellar payment failed: {error_msg}")
            log_entry.error_details = error_msg
            log_entry.status = 'FAILED'
            log_entry.save(update_fields=['error_details', 'status'])

            # Send email alert for individual failed transaction
            cls.send_sweep_failure_alert({
                "errors": [f"Failed to submit Stellar transaction for {amount_str} DZT from '{source_wallet.name}' to '{destination_wallet.name}': {error_msg}"],
                "date": timezone.now().strftime('%Y-%m-%d')
            })

            return {
                "success": False,
                "amount": amount,
                "error": error_msg,
                "log_id": log_entry.id
            }
