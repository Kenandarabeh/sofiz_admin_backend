"""
SofizPay Debug & Email Alert Engine (Imported & Enhanced from Epay)
Handles mission-critical system debugging, email dispatching, and alert cooldowns.
"""
import logging
import traceback
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_ERROR_ALERT_EMAIL = getattr(settings, "DEFAULT_ERROR_ALERT_EMAIL", "rabeh2020ken@gmail.com")
DEFAULT_ALERT_COOLDOWN_MINUTES = 60


def send_email(email_address: str, subject: str, message: str, html_message: str = None, attachments: list = None) -> bool:
    """
    Standard email dispatcher matching Epay email_sender architecture.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "eurlsofizpay@gmail.com")
    recipient_list = [email_address] if isinstance(email_address, str) else email_address

    if html_message:
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=from_email,
            to=recipient_list,
        )
        email.attach_alternative(html_message, "text/html")
    else:
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=from_email,
            to=recipient_list,
        )

    if attachments:
        for attachment in attachments:
            email.attach(
                filename=attachment.get('filename', 'document.pdf'),
                content=attachment.get('content'),
                mimetype=attachment.get('mimetype', 'application/pdf')
            )

    try:
        email.send(fail_silently=False)
        logger.info(f"[SofizPay Email] Dispatched to {recipient_list} | Subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"[SofizPay Email] Failed to send email to {recipient_list}: {e}")
        traceback.print_exc()
        return False


def get_alert_recipients() -> list[str]:
    """Returns recipient list for financial and debug alerts"""
    recipients = [DEFAULT_ERROR_ALERT_EMAIL]
    admin_emails = getattr(settings, "ADMIN_ALERT_EMAILS", [])
    for email in admin_emails:
        if email and email not in recipients:
            recipients.append(email)
    return recipients


def send_sofizpay_debug_alert(service: str, error_msg: str, exc: Exception = None) -> bool:
    """
    Sends a system debug alert to admin email with cooldown logic.
    """
    safe_service = service.replace(" ", "_").lower()
    cooldown_key = f"last_debug_alert_{safe_service}"
    
    if cache.get(cooldown_key):
        logger.info(f"[SofizPay Debug] Skipping alert for '{service}' (Cooldown active).")
        return False

    recipients = get_alert_recipients()
    subject = f"🔴 [SofizPay Debug Alert] {service} - Error Encountered"
    
    trace_info = traceback.format_exc() if exc else "No traceback available."
    
    body = f"""
============================================================
🚨 SOFIZPAY DEBUG ALERT - SYSTEM MONITOR
============================================================
Service: {service}
Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
Error: {error_msg}

Traceback / Details:
{trace_info}

============================================================
Admin Portal: http://localhost:8383/admin/
"""
    success = send_email(recipients, subject, body)
    if success:
        cache.set(cooldown_key, True, timeout=DEFAULT_ALERT_COOLDOWN_MINUTES * 60)
    return success


def send_financial_discrepancy_alert(discrepancy: Decimal, audit_data: dict = None) -> bool:
    """
    Sends rich HTML + Text alert when the Golden Balance equation is violated.
    """
    recipients = get_alert_recipients()
    subject = f"🚨 URGENT: SofizAdmin Financial Discrepancy Detected ({discrepancy:,.2f} DZT)"

    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    
    text_body = f"""
============================================================
⚠️ SOFIZADMIN FINANCIAL MONITORING - URGENT ALERT
============================================================
Timestamp: {timestamp}
Discrepancy: {discrepancy:,.2f} DZT
Status: CRITICAL MISMATCH

Equation Formula:
[Stellar DZT + G2Bulk (DZD)] + [Expenses] != [Capital Inflows + Game Profits]

Please inspect: http://localhost:8383/admin/
============================================================
"""

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; background: #ffffff;">
        <div style="text-align: center; border-bottom: 2px solid #ef4444; padding-bottom: 16px; margin-bottom: 20px;">
            <h2 style="color: #dc2626; margin: 0;">🚨 Financial Discrepancy Alert</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 6px;">SofizAdmin Golden Balance Guard</p>
        </div>
        <div style="background: #fef2f2; border: 1px solid #fee2e2; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <p style="margin: 0; font-size: 16px; color: #991b1b; font-weight: bold;">
                Discrepancy Amount: <span style="font-size: 20px;">{discrepancy:,.2f} DZT</span>
            </p>
            <p style="margin: 6px 0 0 0; font-size: 13px; color: #b91c1c;">
                Timestamp: {timestamp}
            </p>
        </div>
        <div style="font-size: 14px; color: #334155; line-height: 1.6; margin-bottom: 24px;">
            <p>A mismatch was detected in the Golden Balance equation between on-chain assets, operational expenses, capital entries, and gaming profits.</p>
            <p><strong>Action Required:</strong> Please log into the admin dashboard and review the audit log immediately.</p>
        </div>
        <div style="text-align: center;">
            <a href="http://localhost:8383/admin/" style="background: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Open SofizAdmin Portal</a>
        </div>
        <div style="border-top: 1px solid #e2e8f0; margin-top: 24px; padding-top: 12px; text-align: center; font-size: 12px; color: #94a3b8;">
            SofizPay Financial Monitoring System &copy; {datetime.utcnow().year}
        </div>
    </div>
    """

    return send_email(recipients, subject, text_body, html_message=html_body)
