"""
Email Alerts Router for SofizAdmin Financial Monitoring
Powered by SofizPay Debug Engine
"""
import logging
from decimal import Decimal
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
