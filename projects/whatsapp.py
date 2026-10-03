import json
import logging
import re
import threading
import urllib.request
import urllib.error
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ITEM_TYPE_LABELS = {
    'TASK': 'مهمة عمل (Task)',
    'EVENT': 'مناسبة / حدث (Event)',
    'MEETING': 'موعد / لقاء (Meeting)',
}


def normalize_phone_to_chat_id(phone: str) -> str:
    """
    Normalizes a phone number into WhatsApp chatId format (e.g. 213670011093@c.us).
    Handles Algerian local prefixes (06, 05, 07) as well as international numbers.
    """
    if not phone:
        return ''
    cleaned = str(phone).strip()
    if cleaned.endswith('@c.us') or cleaned.endswith('@g.us'):
        return cleaned

    # Remove spaces, dashes, parentheses, plus
    digits = re.sub(r'\D', '', cleaned)

    # Algerian local numbers starting with 05, 06, 07
    if len(digits) == 10 and digits.startswith('0'):
        digits = '213' + digits[1:]
    # Algerian numbers without leading zero (9 digits, starts with 5, 6, 7)
    elif len(digits) == 9 and digits[0] in ('5', '6', '7'):
        digits = '213' + digits

    if not digits:
        return ''

    return f'{digits}@c.us'


def send_whatsapp_message(phone: str, text: str) -> dict:
    """
    Sends a text message using OpenWA WhatsApp API.
    """
    chat_id = normalize_phone_to_chat_id(phone)
    if not chat_id:
        return {'success': False, 'error': f'رقم الهاتف غير صالح: {phone}'}

    base_url = getattr(settings, 'OPENWA_BASE_URL', 'https://whats.sofizpay.com').rstrip('/')
    api_key = getattr(settings, 'OPENWA_API_KEY', '')
    session_id = getattr(settings, 'OPENWA_SESSION_ID', '5169c587-641a-46c3-a6a2-4bd4329439ae')

    url = f'{base_url}/api/sessions/{session_id}/messages/send-text'

    payload = json.dumps({
        'chatId': chat_id,
        'text': text
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, headers={
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    })

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp_body = resp.read().decode('utf-8')
            data = json.loads(resp_body) if resp_body else {}
            logger.info(f'[OpenWA WhatsApp] Message sent to {chat_id}: {data}')
            return {
                'success': True,
                'chat_id': chat_id,
                'message_id': data.get('messageId') or data.get('id'),
                'response': data
            }
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8') if e.fp else str(e)
        logger.error(f'[OpenWA WhatsApp] HTTP Error {e.code} sending to {chat_id}: {err_msg}')
        return {'success': False, 'error': f'OpenWA HTTP Error {e.code}: {err_msg}'}
    except Exception as e:
        logger.error(f'[OpenWA WhatsApp] Error sending to {chat_id}: {e}', exc_info=True)
        return {'success': False, 'error': str(e)}


def format_calendar_reminder_message(task, custom_note=None) -> str:
    """
    Formats a modern Arabic WhatsApp reminder for an appointment, event, or task.
    """
    item_type = getattr(task, 'item_type', 'TASK')
    type_label = ITEM_TYPE_LABELS.get(item_type, 'موعد / مناسبة')
    
    type_emoji = '📅' if item_type == 'EVENT' else ('🤝' if item_type == 'MEETING' else '📌')
    
    project_name = task.project.name if task.project else 'العام'
    assignee_name = (task.assignee.get_full_name() or task.assignee.username) if task.assignee else 'فريق العمل'
    
    date_str = task.due_date.strftime('%Y-%m-%d') if task.due_date else 'اليوم'
    
    due_time_str = ''
    if hasattr(task, 'due_time') and task.due_time:
        due_time_str = task.due_time.strftime('%H:%M')
    elif isinstance(task.tags, dict) and task.tags.get('time'):
        due_time_str = str(task.tags.get('time'))
    
    time_display = f'الساعة {due_time_str}' if due_time_str else 'طوال اليوم'
    
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
    cta_url = f'{frontend_url}/projects'

    lines = [
        f'{type_emoji} *تذكير بـ {type_label} - منصة Sofiz*',
        '━━━━━━━━━━━━━━━━━━━━━',
        f'📌 *العنوان:* {task.title}',
        f'🗓️ *التاريخ:* {date_str}',
        f'⏰ *التوقيت:* {time_display}',
    ]
    if task.project:
        lines.append(f'📁 *المشروع / القسم:* {task.project.name}')
    lines.append(f'👤 *المعني:* {assignee_name}')

    if task.description:
        lines.append('')
        lines.append('📝 *التفاصيل:*')
        lines.append(task.description.strip())

    if custom_note:
        lines.append('')
        lines.append('💡 *ملاحظة إضافية:*')
        lines.append(custom_note.strip())

    lines.extend([
        '━━━━━━━━━━━━━━━━━━━━━',
        f'🔗 *الرابط في التقويم:* {cta_url}',
        '⚡ _تم الإرسال تلقائياً عبر نظام إدارة المهام والمواعيد Sofiz_'
    ])

    return '\n'.join(lines)


def send_task_whatsapp_reminder_sync(task, target_phone=None, custom_message=None, user=None) -> dict:
    """
    Sends WhatsApp reminder synchronously and updates task audit logs.
    """
    from .models import TaskActivityLog

    phone = target_phone or getattr(task, 'whatsapp_phone', '')
    if not phone and task.assignee:
        profile = getattr(task.assignee, 'operator_profile', None)
        phone = profile.phone_number if profile else ''

    if not phone:
        return {'success': False, 'error': 'لم يتم تحديد رقم هاتف للتذكير'}

    text = custom_message if custom_message else format_calendar_reminder_message(task)
    result = send_whatsapp_message(phone, text)

    if result.get('success'):
        if hasattr(task, 'whatsapp_sent_at'):
            task.whatsapp_sent_at = timezone.now()
            task.save(update_fields=['whatsapp_sent_at'])

        TaskActivityLog.objects.create(
            task=task,
            user=user if (user and user.is_authenticated) else None,
            action='WHATSAPP_REMINDER_SENT',
            details={
                'phone': phone,
                'chat_id': result.get('chat_id'),
                'message_id': result.get('message_id')
            }
        )

    return result


def send_task_whatsapp_reminder_async(task, target_phone=None, custom_message=None, user=None):
    """
    Dispatches WhatsApp reminder asynchronously in a background thread.
    """
    thread = threading.Thread(
        target=send_task_whatsapp_reminder_sync,
        args=(task, target_phone, custom_message, user),
        daemon=True
    )
    thread.start()
