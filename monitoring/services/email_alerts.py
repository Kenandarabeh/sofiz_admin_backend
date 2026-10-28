"""
Email Alerts Router for SofizAdmin Financial Monitoring
Powered by SofizPay Debug Engine
"""
import logging
from decimal import Decimal
from django.conf import settings
from .sofizpay_debug import (
    send_email,
    send_sofizpay_debug_alert,
    send_financial_discrepancy_alert,
    get_alert_recipients
)

logger = logging.getLogger(__name__)


class EmailAlertService:
    @staticmethod
    def get_recipient_emails():
        return get_alert_recipients()

    @classmethod
    def send_discrepancy_alert(cls, discrepancy_amount: Decimal, audit_log=None):
        if not getattr(settings, "EMAIL_ALERTS_ENABLED", False):
            logger.info(f"[EmailAlertService] Suppressed discrepancy alert ({discrepancy_amount:,.2f} DZT): Email alerts globally disabled.")
            return False
        try:
            from monitoring.models import G2BulkReplenishmentWindow
            if G2BulkReplenishmentWindow.is_replenishment_active():
                G2BulkReplenishmentWindow.record_suppressed_alert(
                    alert_type="DISCREPANCY",
                    amount=discrepancy_amount
                )
                logger.warning(
                    f"[G2Bulk Replenishment Grace Active] Discrepancy alert suppressed ({discrepancy_amount:,.2f} DZT). "
                    f"Continuous system operations preserved during 30h replenishment window."
                )
                return False
        except Exception as e:
            logger.error(f"Error checking replenishment window in send_discrepancy_alert: {e}")

        return send_financial_discrepancy_alert(discrepancy_amount)

    @classmethod
    def send_low_balance_alert(cls, provider_name: str, current_balance: Decimal, threshold: Decimal, currency: str = "USD"):
        if not getattr(settings, "EMAIL_ALERTS_ENABLED", False):
            logger.info(f"[EmailAlertService] Suppressed low balance alert for {provider_name}: Email alerts globally disabled.")
            return False
        if provider_name and ("G2Bulk" in provider_name or "G2BULK" in provider_name):
            try:
                from monitoring.models import G2BulkReplenishmentWindow
                if G2BulkReplenishmentWindow.is_replenishment_active():
                    G2BulkReplenishmentWindow.record_suppressed_alert(
                        alert_type="LOW_BALANCE",
                        amount=current_balance
                    )
                    logger.warning(
                        f"[G2Bulk Replenishment Grace Active] Low balance alert suppressed for {provider_name} "
                        f"({current_balance:,.2f} {currency}). Continuous system operations preserved."
                    )
                    return False
            except Exception as e:
                logger.error(f"Error checking replenishment window in send_low_balance_alert: {e}")

        subject = f"⚠️ Low Balance Warning: {provider_name} ({current_balance:,.2f} {currency})"
        message = f"Supplier account {provider_name} is below the threshold of {threshold:,.2f} {currency}. Current: {current_balance:,.2f} {currency}."
        return send_sofizpay_debug_alert(f"{provider_name} Balance", message)

    @classmethod
    def send_gaming_capital_discrepancy_alert(cls, discrepancy_dzd: Decimal, left_side: dict, right_side: dict) -> bool:
        """
        Direct mission-critical alert dispatched to administrator email when
        Gaming Capital does not reconcile with the 5 operational holding assets.
        Throttled by smart cooldown to avoid inbox flooding, but dispatches immediately on mismatch change.
        """
        from django.core.cache import cache
        from datetime import datetime

        if not getattr(settings, "EMAIL_ALERTS_ENABLED", False):
            logger.info("[EmailAlertService] Suppressed gaming discrepancy alert: Email alerts globally disabled.")
            return False

        discrepancy_val = float(discrepancy_dzd)
        # Asymmetric Safety Invariant: Surplus (Left >= Right) is safe operational float.
        # Deficit (Left < Right) is strictly forbidden and triggers immediate emergency email alert.
        if discrepancy_val >= -1.0:
            return False

        rounded_disc = round(discrepancy_val, 0)
        cooldown_key = f"gaming_capital_deficit_alert_{rounded_disc}"
        if cache.get(cooldown_key):
            logger.info(f"[EmailAlertService] Skipping gaming capital deficit alert ({discrepancy_val:,.2f} DZD). Cooldown active.")
            return False

        recipients = get_alert_recipients()
        direction = "DEFICIT"
        sign = ""
        subject = f"🚨 [CRITICAL DEFICIT] Gaming Capital Shortfall: {discrepancy_val:,.2f} DZD"

        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        right_cap = float(right_side.get('gaming_capital_dzd') or right_side.get('total_dzd') or 0)
        left_tot = float(left_side.get('total_dzd') or 0)
        compte_g = float(left_side.get('compte_g_dzd') or 0)
        wallets_tot = float(left_side.get('four_wallets_total_dzt') or 0)
        withdrawal_tot = float(left_side.get('withdrawal_wallet_dzt') or 0)
        g2bulk_dzd = float(left_side.get('g2bulk_dzd') or 0)
        g2bulk_usd = float(left_side.get('g2bulk_usd') or 0)
        binance_dzd = float(left_side.get('binance_dzd') or 0)
        binance_usdt = float(left_side.get('binance_usdt') or 0)

        text_body = f"""
============================================================
🚨 SOFIZADMIN FINANCIAL MONITORING - CRITICAL CAPITAL ALERT
============================================================
Timestamp: {timestamp}
Status: {direction} DETECTED
Discrepancy: {sign}{discrepancy_val:,.2f} DZD

RECONCILIATION SUMMARY:
- Left Side (5 Operational Assets): {left_tot:,.2f} DZD
  1. Digital Services Operational Account (BaridiMob Quota): {compte_g:,.2f} DZD
  2. 4 Game Collection Wallets: {wallets_tot:,.2f} DZT
  3. Games Collection & Withdrawal Wallet: {withdrawal_tot:,.2f} DZT
  4. G2Bulk Supplier: ${g2bulk_usd:,.2f} USD ({g2bulk_dzd:,.2f} DZD)
  5. Binance USDT: {binance_usdt:,.2f} USDT ({binance_dzd:,.2f} DZD)

- Right Side (Authorized Capital Standard): {right_cap:,.2f} DZD

Formula: Left Side Total - Right Side Capital = Discrepancy
{left_tot:,.2f} DZD - {right_cap:,.2f} DZD = {sign}{discrepancy_val:,.2f} DZD

Action Required:
Immediate administrative review required. Please inspect the Gaming Operations Hub:
http://localhost:5172/game
============================================================
"""

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 620px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #ffffff;">
            <div style="background: {'#2563eb' if discrepancy_val > 0 else '#dc2626'}; padding: 20px; text-align: center; color: #ffffff;">
                <h1 style="margin: 0; font-size: 20px; font-weight: 800; letter-spacing: -0.5px;">🚨 Gaming Capital Reconciliation Alert</h1>
                <p style="margin: 6px 0 0 0; font-size: 13px; opacity: 0.9;">Institutional Financial Balance Guard</p>
            </div>
            
            <div style="padding: 24px;">
                <div style="background: {'#eff6ff' if discrepancy_val > 0 else '#fef2f2'}; border: 1px solid {'#bfdbfe' if discrepancy_val > 0 else '#fee2e2'}; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                    <p style="margin: 0; font-size: 13px; color: #64748b; font-weight: 600; text-transform: uppercase;">Detected Discrepancy ({direction})</p>
                    <p style="margin: 4px 0 0 0; font-size: 24px; font-weight: 900; color: {'#1d4ed8' if discrepancy_val > 0 else '#b91c1c'}; font-family: monospace;">
                        {sign}{discrepancy_val:,.2f} DZD
                    </p>
                    <p style="margin: 6px 0 0 0; font-size: 12px; color: #64748b;">Timestamp: {timestamp}</p>
                </div>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px;">
                    <thead>
                        <tr style="border-bottom: 2px solid #e2e8f0; text-align: left;">
                            <th style="padding: 8px 0; color: #475569;">Component</th>
                            <th style="padding: 8px 0; text-align: right; color: #475569;">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 8px 0; color: #334155;">1. Digital Services Operational Account (BaridiMob Ops Quota)</td>
                            <td style="padding: 8px 0; text-align: right; font-family: monospace; font-weight: 600;">{compte_g:,.2f} DZD</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 8px 0; color: #334155;">2. 4 Gaming Collection Wallets</td>
                            <td style="padding: 8px 0; text-align: right; font-family: monospace; font-weight: 600;">{wallets_tot:,.2f} DZT</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 8px 0; color: #334155;">3. Games Collection & Withdrawal Wallet</td>
                            <td style="padding: 8px 0; text-align: right; font-family: monospace; font-weight: 600;">{withdrawal_tot:,.2f} DZT</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 8px 0; color: #334155;">4. G2Bulk Supplier Balance (${g2bulk_usd:,.2f})</td>
                            <td style="padding: 8px 0; text-align: right; font-family: monospace; font-weight: 600;">{g2bulk_dzd:,.2f} DZD</td>
                        </tr>
                        <tr style="border-bottom: 2px solid #e2e8f0;">
                            <td style="padding: 8px 0; color: #334155;">5. Binance Corporate USDT ({binance_usdt:,.2f})</td>
                            <td style="padding: 8px 0; text-align: right; font-family: monospace; font-weight: 600;">{binance_dzd:,.2f} DZD</td>
                        </tr>
                        <tr style="background: #f8fafc; font-weight: 800;">
                            <td style="padding: 10px 0; color: #0f172a;">Total Left Side Assets</td>
                            <td style="padding: 10px 0; text-align: right; font-family: monospace; color: #0f172a;">{left_tot:,.2f} DZD</td>
                        </tr>
                        <tr style="background: #f8fafc; font-weight: 800; border-top: 1px solid #e2e8f0;">
                            <td style="padding: 10px 0; color: #059669;">Right Side: Authorized Gaming Capital</td>
                            <td style="padding: 10px 0; text-align: right; font-family: monospace; color: #059669;">{right_cap:,.2f} DZD</td>
                        </tr>
                    </tbody>
                </table>

                <p style="font-size: 13px; color: #475569; line-height: 1.5; margin: 0 0 20px 0;">
                    <strong>Action Required:</strong> The 5 operational holding places must reconcile strictly with authorized Gaming Capital. Please inspect the operations hub immediately.
                </p>

                <div style="text-align: center; margin-top: 24px;">
                    <a href="http://localhost:5172/game" style="background: #0f172a; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block;">Open Gaming Operations Hub</a>
                </div>
            </div>

            <div style="border-top: 1px solid #f1f5f9; background: #f8fafc; padding: 14px 24px; text-align: center; font-size: 11px; color: #94a3b8;">
                SofizPay Institutional Treasury System &copy; {datetime.utcnow().year}
            </div>
        </div>
        """

        success = send_email(recipients, subject, text_body, html_message=html_body)
        if success:
            cache.set(cooldown_key, True, timeout=900)
        return success

