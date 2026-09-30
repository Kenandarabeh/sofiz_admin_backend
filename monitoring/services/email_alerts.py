"""
Email Alerts Router for SofizAdmin Financial Monitoring
Powered by SofizPay Debug Engine
"""
from decimal import Decimal
from .sofizpay_debug import (
    send_email,
    send_sofizpay_debug_alert,
    send_financial_discrepancy_alert,
    get_alert_recipients
)


class EmailAlertService:
    @staticmethod
    def get_recipient_emails():
        return get_alert_recipients()

    @classmethod
    def send_discrepancy_alert(cls, discrepancy_amount: Decimal, audit_log=None):
        return send_financial_discrepancy_alert(discrepancy_amount)

    @classmethod
    def send_low_balance_alert(cls, provider_name: str, current_balance: Decimal, threshold: Decimal, currency: str = "USD"):
        subject = f"⚠️ Low Balance Warning: {provider_name} ({current_balance:,.2f} {currency})"
        message = f"Supplier account {provider_name} is below the threshold of {threshold:,.2f} {currency}. Current: {current_balance:,.2f} {currency}."
        return send_sofizpay_debug_alert(f"{provider_name} Balance", message)
