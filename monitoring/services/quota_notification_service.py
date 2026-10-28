"""
Quota Notification Service:
Dispatches automated real-time email alerts to track (Gaming Operations Manager)
and CCs the Administrator whenever faming (Withdrawal & Treasury Officer) replenishes
or adds balance/quota to any operational subsystem (Gaming, eSIM, Factures, Flexy, Idoom, IPTV, XLM).
"""
import logging
import threading
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

logger = logging.getLogger(__name__)

# Unrestricted Refill Notification Policy: Sends real-time notification for every confirmed refill
ALERT_COOLDOWN_SECONDS = 0
_LAST_NOTIFICATION_TIMES = {}


SUBSYSTEM_LABELS = {
    'GAMING': 'Gaming Working Quota (Digital Services & Cards)',
    'ESIM': 'eSIM Operational Quota (eSIM Account & Roaming)',
    'UTILITY': 'Factures & National Utilities Quota (Sonelgaz/ADE/AT)',
    'FACTURE': 'Factures & National Utilities Quota (Sonelgaz/ADE/AT)',
    'FLEXY': 'Flexy Telecom Operational Pool (Shemsnet)',
    'IDOOM': 'Idoom Vouchers & Inventory Stock',
    'IPTV': 'IPTV Server Subscriptions Stock',
    'XLM': 'Central Treasury XLM Vault Refill',
}


def _build_html_email(
    subsystem: str,
    subsystem_label: str,
    amount_dzd: Decimal,
    operator_display: str,
    reference: str,
    notes: str,
    timestamp_str: str,
) -> str:
    amount_formatted = f"{amount_dzd:,.2f} DZD"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quota Refill Notification</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #080c1d;
      color: #e2e8f0;
      margin: 0;
      padding: 24px;
    }}
    .container {{
      max-width: 600px;
      margin: 0 auto;
      background-color: #0c122b;
      border: 1px solid rgba(59, 130, 246, 0.25);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }}
    .header {{
      background: linear-gradient(135deg, #1e1b4b 0%, #0c122b 100%);
      padding: 28px 24px;
      text-align: center;
      border-bottom: 1px solid rgba(99, 102, 241, 0.2);
    }}
    .brand {{
      font-size: 11px;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: #818cf8;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .headline {{
      font-size: 20px;
      font-weight: 800;
      color: #ffffff;
      margin: 0;
    }}
    .content {{
      padding: 28px 24px;
    }}
    .hero-card {{
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(5, 150, 105, 0.05) 100%);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      margin-bottom: 24px;
    }}
    .hero-label {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: #34d399;
      letter-spacing: 1px;
      margin-bottom: 6px;
    }}
    .hero-amount {{
      font-size: 32px;
      font-weight: 900;
      font-family: 'Courier New', Courier, monospace;
      color: #10b981;
      margin: 0;
    }}
    .badge {{
      display: inline-block;
      margin-top: 8px;
      padding: 4px 10px;
      border-radius: 9999px;
      background-color: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #a5b4fc;
      font-size: 11px;
      font-weight: 700;
    }}
    .details-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20px;
    }}
    .details-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.1);
      font-size: 13px;
    }}
    .label-col {{
      color: #94a3b8;
      width: 38%;
      font-weight: 500;
    }}
    .val-col {{
      color: #f1f5f9;
      font-weight: 700;
      font-family: 'Courier New', Courier, monospace;
    }}
    .notes-box {{
      background-color: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 10px;
      padding: 12px;
      font-size: 12px;
      color: #cbd5e1;
      margin-top: 16px;
      line-height: 1.5;
    }}
    .footer {{
      background-color: #070b1e;
      padding: 16px 24px;
      text-align: center;
      font-size: 11px;
      color: #64748b;
      border-top: 1px solid rgba(148, 163, 184, 0.08);
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">SofizPay Operational Treasury</div>
      <h1 class="headline">Working Capital Quota Refill Notice</h1>
    </div>

    <div class="content">
      <div class="hero-card">
        <div class="hero-label">Funds Added to Working Quota</div>
        <div class="hero-amount">+{amount_formatted}</div>
        <div class="badge">{subsystem_label}</div>
      </div>

      <table class="details-table">
        <tr>
          <td class="label-col">Target Subsystem:</td>
          <td class="val-col">{subsystem_label}</td>
        </tr>
        <tr>
          <td class="label-col">Amount Credited:</td>
          <td class="val-col" style="color: #10b981;">{amount_formatted}</td>
        </tr>
        <tr>
          <td class="label-col">Initiating Officer:</td>
          <td class="val-col">{operator_display}</td>
        </tr>
        <tr>
          <td class="label-col">Transaction Ref:</td>
          <td class="val-col">#{reference}</td>
        </tr>
        <tr>
          <td class="label-col">Execution Time:</td>
          <td class="val-col">{timestamp_str}</td>
        </tr>
      </table>

      {f'<div class="notes-box"><strong>Operation Notes:</strong><br>{notes}</div>' if notes else ''}
    </div>

    <div class="footer">
      Automated System Dispatch &bull; SofizPay Central Liquidity & Quota Monitoring &bull; Strict Zero-Discrepancy Audit
    </div>
  </div>
</body>
</html>
"""


def _send_email_worker(
    subsystem: str,
    amount_dzd: Decimal,
    operator_display: str,
    reference: str,
    notes: str,
    timestamp_str: str,
):
    try:
        subsystem_key = str(subsystem).upper()
        subsystem_label = SUBSYSTEM_LABELS.get(subsystem_key, f"{subsystem_key} Operational Quota")

        recipient_to = getattr(settings, 'track_NOTIFICATION_EMAIL', 'gaming@sofizpay.com')
        recipient_cc = getattr(settings, 'ADMIN_NOTIFICATION_EMAIL', 'rabeh2020ken@gmail.com')
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'eurlsofizpay@gmail.com')

        subject = f"[SofizPay Quota Refill] +{amount_dzd:,.2f} DZD Added to {subsystem_key} Quota by {operator_display}"

        plain_text = (
            f"SofizPay Working Capital Quota Refill Notification\n"
            f"==================================================\n\n"
            f"Subsystem: {subsystem_label}\n"
            f"Amount Credited: +{amount_dzd:,.2f} DZD\n"
            f"Executed By: {operator_display}\n"
            f"Reference: #{reference}\n"
            f"Timestamp: {timestamp_str}\n"
        )
        if notes:
            plain_text += f"Notes: {notes}\n"

        html_content = _build_html_email(
            subsystem=subsystem_key,
            subsystem_label=subsystem_label,
            amount_dzd=amount_dzd,
            operator_display=operator_display,
            reference=reference,
            notes=notes,
            timestamp_str=timestamp_str,
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            from_email=from_email,
            to=[recipient_to],
            cc=[recipient_cc] if recipient_cc else None,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info(
            f"[QuotaNotificationService] Successfully sent refill notification to {recipient_to} (CC: {recipient_cc}) "
            f"for +{amount_dzd} DZD on {subsystem_key}."
        )
    except Exception as exc:
        logger.error(f"[QuotaNotificationService] Failed to send email alert: {exc}", exc_info=True)


def notify_quota_refill(
    subsystem: str,
    amount_dzd,
    operator=None,
    reference: str = None,
    notes: str = None,
    async_send: bool = True,
    force: bool = False,
):
    """
    Entry point to trigger quota refill email notification.
    Safe against null values, negative amounts, or missing parameters.
    Dispatches asynchronously in a daemon thread so API responses are immediate.
    """
    try:
        if not getattr(settings, 'EMAIL_ALERTS_ENABLED', False):
            return

        dec_amount = Decimal(str(amount_dzd or 0.00))
        if dec_amount <= Decimal("0.00"):
            return

        subsystem_key = str(subsystem).upper()

        # Quiet / Stop Window: Suppress alerts during active replenishment grace shield
        try:
            from monitoring.models import G2BulkReplenishmentWindow
            if G2BulkReplenishmentWindow.is_replenishment_active():
                G2BulkReplenishmentWindow.record_suppressed_alert(
                    alert_type="QUOTA_REFILL",
                    amount=dec_amount
                )
                logger.info(
                    f"[QuotaNotificationService] Refill email alert suppressed (+{dec_amount:,.2f} DZD for {subsystem}). "
                    f"Replenishment Grace Shield is active (Quiet Transit Window)."
                )
                return
        except Exception as shield_err:
            logger.debug(f"[QuotaNotificationService] Shield check exception: {shield_err}")

        _LAST_NOTIFICATION_TIMES[subsystem_key] = timezone.now()


        operator_display = "Walid (Finance / Treasury Officer)"
        if operator:
            if hasattr(operator, 'get_full_name') and operator.get_full_name():
                operator_display = f"{operator.get_full_name()} ({operator.username})"
            elif hasattr(operator, 'username'):
                operator_display = f"{operator.username} (Finance / Treasury Officer)"
            elif isinstance(operator, str):
                operator_display = operator

        ref_str = str(reference or timezone.now().strftime('%Y%m%d%H%M%S'))
        now_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')

        args = (
            str(subsystem),
            dec_amount,
            operator_display,
            ref_str,
            str(notes or ''),
            now_str,
        )

        if async_send:
            thread = threading.Thread(target=_send_email_worker, args=args, daemon=True)
            thread.start()
        else:
            _send_email_worker(*args)

    except Exception as err:
        logger.error(f"[QuotaNotificationService] Error initiating notification: {err}", exc_info=True)
