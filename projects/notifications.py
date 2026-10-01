import logging
import threading
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    'TODO': 'قيد الانتظار (To Do)',
    'IN_PROGRESS': 'قيد التنفيذ (In Progress)',
    'IN_REVIEW': 'قيد المراجعة والتدقيق (In Review)',
    'DONE': 'مكتملة ومُنجزة (Done)',
    'BLOCKED': 'معلقة / متوقفة (Blocked)',
}

STATUS_COLORS = {
    'TODO': '#64748b',
    'IN_PROGRESS': '#0d6efd',
    'IN_REVIEW': '#8b5cf6',
    'DONE': '#10b981',
    'BLOCKED': '#ef4444',
}

PRIORITY_LABELS = {
    'URGENT': 'عاجلة جداً (Urgent)',
    'HIGH': 'أولوية عالية (High)',
    'MEDIUM': 'متوسطة (Medium)',
    'LOW': 'منخفضة (Low)',
}

PRIORITY_COLORS = {
    'URGENT': '#ef4444',
    'HIGH': '#f97316',
    'MEDIUM': '#3b82f6',
    'LOW': '#64748b',
}


def _send_email_worker(recipient_list, subject, text_content, html_content):
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'eurlsofizpay@gmail.com')
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipient_list,
        )
        email.attach_alternative(html_content, 'text/html')
        email.send(fail_silently=False)
        logger.info(f"[Task Notification] Email successfully sent to {recipient_list} | Subject: {subject}")
    except Exception as e:
        logger.error(f"[Task Notification] Failed to send email to {recipient_list}: {e}", exc_info=True)


def _dispatch_async_email(recipient_list, subject, text_content, html_content):
    valid_recipients = [r.strip() for r in recipient_list if r and '@' in r]
    if not valid_recipients:
        logger.warning(f"[Task Notification] No valid recipient email found. Skipped subject: {subject}")
        return

    thread = threading.Thread(
        target=_send_email_worker,
        args=(valid_recipients, subject, text_content, html_content),
        daemon=True
    )
    thread.start()


def _get_base_template(headline, preheader, task_key, task_title, project_name, status, priority, due_date_str, extra_body_html, cta_url):
    status_label = STATUS_LABELS.get(status, status)
    status_color = STATUS_COLORS.get(status, '#0d6efd')
    priority_label = PRIORITY_LABELS.get(priority, priority)
    priority_color = PRIORITY_COLORS.get(priority, '#3b82f6')

    return '''<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>''' + str(headline) + '''</title>
  <style>
    body {
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f1f5f9;
      color: #1e293b;
      line-height: 1.6;
    }
    .wrapper {
      width: 100%;
      background-color: #f1f5f9;
      padding: 30px 15px;
      box-sizing: border-box;
    }
    .card {
      max-width: 600px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
      border: 1px solid #e2e8f0;
    }
    .header {
      background: linear-gradient(135deg, #0d6efd 0%, #1e40af 100%);
      color: #ffffff;
      padding: 24px;
      text-align: right;
    }
    .badge-pill {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: rgba(255, 255, 255, 0.2);
      color: #ffffff;
      margin-bottom: 8px;
    }
    .header h1 {
      margin: 6px 0 0 0;
      font-size: 20px;
      font-weight: 800;
    }
    .body {
      padding: 28px 24px;
      text-align: right;
    }
    .task-title {
      font-size: 18px;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 16px;
    }
    .meta-table {
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0;
      background: #f8fafc;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid #e2e8f0;
    }
    .meta-table td {
      padding: 10px 14px;
      font-size: 13px;
      border-bottom: 1px solid #e2e8f0;
    }
    .meta-table tr:last-child td {
      border-bottom: none;
    }
    .meta-label {
      color: #64748b;
      font-weight: 600;
      width: 32%;
    }
    .meta-value {
      color: #0f172a;
      font-weight: 700;
    }
    .status-tag {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      color: #ffffff;
      font-size: 11px;
      font-weight: 700;
      background: ''' + str(status_color) + ''';
    }
    .priority-tag {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      color: #ffffff;
      font-size: 11px;
      font-weight: 700;
      background: ''' + str(priority_color) + ''';
    }
    .cta-container {
      text-align: center;
      margin-top: 28px;
      padding-top: 15px;
    }
    .btn {
      display: inline-block;
      background: #0d6efd;
      color: #ffffff !important;
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
      padding: 12px 28px;
      border-radius: 8px;
      box-shadow: 0 4px 10px rgba(13, 110, 253, 0.25);
    }
    .footer {
      background: #f8fafc;
      padding: 16px 24px;
      text-align: center;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid #e2e8f0;
    }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <span class="badge-pill">SOFIZ WORKFLOW &bull; ''' + str(task_key) + '''</span>
        <h1>''' + str(headline) + '''</h1>
      </div>
      <div class="body">
        <div class="task-title">[''' + str(task_key) + '''] ''' + str(task_title) + '''</div>
        <p style="color: #475569; font-size: 13px; margin: 0 0 16px 0;">''' + str(preheader) + '''</p>
        
        <table class="meta-table">
          <tr>
            <td class="meta-label">المشروع:</td>
            <td class="meta-value">''' + str(project_name) + '''</td>
          </tr>
          <tr>
            <td class="meta-label">الحالة الحالية:</td>
            <td class="meta-value"><span class="status-tag">''' + str(status_label) + '''</span></td>
          </tr>
          <tr>
            <td class="meta-label">مستوى الأولوية:</td>
            <td class="meta-value"><span class="priority-tag">''' + str(priority_label) + '''</span></td>
          </tr>
          <tr>
            <td class="meta-label">تاريخ الاستحقاق:</td>
            <td class="meta-value">''' + str(due_date_str) + '''</td>
          </tr>
        </table>

        ''' + str(extra_body_html) + '''

        <div class="cta-container">
          <a href="''' + str(cta_url) + '''" class="btn" target="_blank">الانتقال للمهمة في النظام &larr;</a>
        </div>
      </div>
      <div class="footer">
        هذا إشعار تلقائي من نظام إدارة المهام والمشاريع التابع لمنصة Sofiz &bull; لا تقم بالرد مباشرة على هذه الرسالة.
      </div>
    </div>
  </div>
</body>
</html>'''


def notify_task_assigned_async(task, assigned_by=None):
    if not task.assignee or not task.assignee.email:
        return

    recipient_email = task.assignee.email.strip()
    assignee_name = task.assignee.get_full_name() or task.assignee.username
    assigned_by_name = (assigned_by.get_full_name() or assigned_by.username) if assigned_by else "إدارة النظام"
    project_name = task.project.name if task.project else "العام"
    due_date_str = task.due_date.strftime('%Y-%m-%d') if task.due_date else "غير محدد"

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    cta_url = f"{frontend_url.rstrip('/')}/projects"

    subject = f"[Jira / Sofiz] تم إسناد مهمة جديدة إليك: {task.task_key} - {task.title}"

    description_html = ""
    if task.description:
        formatted_desc = task.description.replace('\n', '<br>')
        description_html = f'''
        <div style="background: #f1f5f9; padding: 12px 16px; border-radius: 8px; border-right: 4px solid #0d6efd; margin-top: 16px; font-size: 13px; color: #334155;">
          <strong style="display: block; margin-bottom: 4px; color: #0f172a;">تفاصيل المهمة:</strong>
          {formatted_desc}
        </div>
        '''

    extra_body = f'''
    <p style="font-size: 13px; color: #334155; margin-bottom: 12px;">
      مرحباً <strong>{assignee_name}</strong>، تم تكليفك بمهمة عمل جديدة بواسطة <strong>{assigned_by_name}</strong>. يرجى الاطلاع على التفاصيل والمباشرة في العمل عليها:
    </p>
    {description_html}
    '''

    text_content = (
        f"مرحباً {assignee_name}،\n"
        f"تم إسناد مهمة جديدة إليك في نظام Sofiz للمشاريع بواسطة {assigned_by_name}.\n\n"
        f"المهمة: [{task.task_key}] {task.title}\n"
        f"المشروع: {project_name}\n"
        f"الأولوية: {PRIORITY_LABELS.get(task.priority, task.priority)}\n"
        f"تاريخ الاستحقاق: {due_date_str}\n\n"
        f"التفاصيل:\n{task.description or 'لا توجد تفاصيل إضافية'}\n\n"
        f"يمكنك الاطلاع على المهمة ومتابعتها عبر الرابط:\n{cta_url}\n"
    )

    html_content = _get_base_template(
        headline="تم إسناد مهمة جديدة إليك",
        preheader=f"المُكلف بالمهمة: {assigned_by_name}",
        task_key=task.task_key,
        task_title=task.title,
        project_name=project_name,
        status=task.status,
        priority=task.priority,
        due_date_str=due_date_str,
        extra_body_html=extra_body,
        cta_url=cta_url
    )

    _dispatch_async_email([recipient_email], subject, text_content, html_content)


def notify_task_status_changed_async(task, old_status, new_status, changed_by=None):
    recipients = set()
    changed_by_id = changed_by.id if (changed_by and changed_by.is_authenticated) else None

    if task.assignee and task.assignee.email and task.assignee.id != changed_by_id:
        recipients.add(task.assignee.email.strip())

    if task.reporter and task.reporter.email and task.reporter.id != changed_by_id:
        recipients.add(task.reporter.email.strip())

    if not recipients:
        return

    changed_by_name = (changed_by.get_full_name() or changed_by.username) if changed_by else "أحد أعضاء الفريق"
    old_status_label = STATUS_LABELS.get(old_status, old_status)
    new_status_label = STATUS_LABELS.get(new_status, new_status)
    project_name = task.project.name if task.project else "العام"
    due_date_str = task.due_date.strftime('%Y-%m-%d') if task.due_date else "غير محدد"

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    cta_url = f"{frontend_url.rstrip('/')}/projects"

    subject = f"[Jira / Sofiz] تحديث حالة المهمة {task.task_key}: {new_status_label}"

    extra_body = f'''
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 14px; border-radius: 8px; margin: 16px 0; text-align: center;">
      <span style="color: #64748b; font-size: 12px; display: block; margin-bottom: 6px;">تغيير الحالة بواسطة <strong>{changed_by_name}</strong></span>
      <div style="font-size: 14px; font-weight: 700;">
        <span style="text-decoration: line-through; color: #94a3b8;">{old_status_label}</span>
        <span style="margin: 0 10px; color: #0d6efd;">&larr;</span>
        <span style="color: {STATUS_COLORS.get(new_status, '#0d6efd')};">{new_status_label}</span>
      </div>
    </div>
    '''

    text_content = (
        f"مرحباً،\n"
        f"تم تحديث حالة المهمة [{task.task_key}] {task.title} بواسطة {changed_by_name}.\n\n"
        f"الحالة السابقة: {old_status_label}\n"
        f"الحالة الجديدة: {new_status_label}\n"
        f"المشروع: {project_name}\n\n"
        f"الرابط المباشر:\n{cta_url}\n"
    )

    html_content = _get_base_template(
        headline=f"تحديث حالة المهمة &larr; {new_status_label}",
        preheader=f"قام {changed_by_name} بتعديل مسار المهمة",
        task_key=task.task_key,
        task_title=task.title,
        project_name=project_name,
        status=new_status,
        priority=task.priority,
        due_date_str=due_date_str,
        extra_body_html=extra_body,
        cta_url=cta_url
    )

    _dispatch_async_email(list(recipients), subject, text_content, html_content)


def notify_task_comment_added_async(task, comment, author=None):
    recipients = set()
    author_id = author.id if (author and author.is_authenticated) else None

    if task.assignee and task.assignee.email and task.assignee.id != author_id:
        recipients.add(task.assignee.email.strip())

    if task.reporter and task.reporter.email and task.reporter.id != author_id:
        recipients.add(task.reporter.email.strip())

    if not recipients:
        return

    author_name = (author.get_full_name() or author.username) if author else "عضو في الفريق"
    project_name = task.project.name if task.project else "العام"
    due_date_str = task.due_date.strftime('%Y-%m-%d') if task.due_date else "غير محدد"

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    cta_url = f"{frontend_url.rstrip('/')}/projects"

    subject = f"[Jira / Sofiz] تعليق جديد على المهمة {task.task_key} بواسطة {author_name}"

    formatted_comment = comment.content.replace('\n', '<br>')
    comment_html = f'''
    <div style="background: #eff6ff; padding: 14px 18px; border-radius: 8px; border-right: 4px solid #3b82f6; margin-top: 16px; font-size: 13px; color: #1e3a8a;">
      <strong style="display: block; margin-bottom: 4px;">تعليق {author_name}:</strong>
      {formatted_comment}
    </div>
    '''

    text_content = (
        f"مرحباً،\n"
        f"أضاف {author_name} تعليقاً جديداً على المهمة [{task.task_key}] {task.title}:\n\n"
        f'\"{comment.content}\"\n\n'
        f"المشروع: {project_name}\n"
        f"الرابط المباشر:\n{cta_url}\n"
    )

    html_content = _get_base_template(
        headline="تعليق جديد على المهمة",
        preheader=f"أضاف {author_name} ملاحظة أو تعليقاً",
        task_key=task.task_key,
        task_title=task.title,
        project_name=project_name,
        status=task.status,
        priority=task.priority,
        due_date_str=due_date_str,
        extra_body_html=comment_html,
        cta_url=cta_url
    )

    _dispatch_async_email(list(recipients), subject, text_content, html_content)
