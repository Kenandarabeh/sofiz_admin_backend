"""
Institutional Staff Audit Service.
Provides comprehensive tracking of operator actions, model modifications,
and critical operations execution across the entire SofizPay platform.
Strictly complies with Institutional Fintech Standards (100% English).
"""
import logging
from decimal import Decimal
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class AuditService:
    @staticmethod
    def get_client_ip(request):
        """Extracts the client IP address from the HTTP request headers."""
        if not request:
            return None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    @staticmethod
    def get_user_agent(request):
        """Extracts the client User-Agent string from the HTTP request headers."""
        if not request:
            return None
        return request.META.get('HTTP_USER_AGENT', '')[:500]

    @classmethod
    def log_action(
        cls,
        operator,
        action_type,
        target_model,
        object_repr,
        changes_summary,
        object_id=None,
        request=None
    ):
        """
        Creates an immutable institutional audit log entry for any staff operator action.
        """
        from monitoring.models import OperatorActionLog

        username = "system"
        family = "SYSTEM"
        op_user = None

        if operator and hasattr(operator, 'is_authenticated') and operator.is_authenticated:
            op_user = operator
            username = operator.username
            if hasattr(operator, 'operator_profile') and operator.operator_profile:
                family = operator.operator_profile.mission_role
            elif operator.is_superuser:
                family = "ALL_FAMILIES"
            else:
                family = "STAFF"
        elif isinstance(operator, str):
            username = operator

        ip = cls.get_client_ip(request)
        ua = cls.get_user_agent(request)

        try:
            log_entry = OperatorActionLog.objects.create(
                operator=op_user,
                operator_username=username,
                operator_family=family,
                action_type=action_type,
                target_model=str(target_model)[:100],
                object_id=str(object_id)[:100] if object_id is not None else "",
                object_repr=str(object_repr)[:255],
                changes_summary=str(changes_summary),
                ip_address=ip,
                user_agent=ua,
            )
            return log_entry
        except Exception as e:
            logger.error(f"AuditService failed to record action: {e}", exc_info=True)
            return None

    @classmethod
    def diff_model_changes(cls, form, instance):
        """
        Generates a human-readable diff summary of modified fields between the original
        and current state of an object.
        """
        if not hasattr(form, 'changed_data') or not form.changed_data:
            return "No field changes detected."

        diff_lines = []
        for field_name in form.changed_data:
            new_val = form.cleaned_data.get(field_name)
            # Fetch old value from initial data if available
            old_val = form.initial.get(field_name, "<unrecorded>")
            
            # Format numbers or masks if needed
            if isinstance(new_val, Decimal) or isinstance(old_val, Decimal):
                old_display = f"{old_val:,.2f}" if isinstance(old_val, Decimal) else str(old_val)
                new_display = f"{new_val:,.2f}" if isinstance(new_val, Decimal) else str(new_val)
            else:
                old_display = str(old_val)
                new_display = str(new_val)

            diff_lines.append(f"• {field_name}: '{old_display}' ➔ '{new_display}'")

        return "\n".join(diff_lines)
