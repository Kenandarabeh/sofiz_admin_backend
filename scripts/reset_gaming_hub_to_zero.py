import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sofiz_admin.settings')
django.setup()

from django.db import transaction, connection
from monitoring.models import WithdrawalRecord, SubSystemType
import json


def reset_gaming_hub_to_zero():
    print("=" * 60)
    print("RESETTING GAMING OPERATIONS HUB TO ABSOLUTE ZERO (0.00 DZD)")
    print("=" * 60)

    # 1. Fetch all GAMING withdrawal and refill records
    qs = WithdrawalRecord.objects.filter(system_type=SubSystemType.GAMING)
    total_count = qs.count()

    print(f"Found {total_count} GAMING operations in database (Walid refills + Sofiane dispatches).")

    # 2. Atomic deletion
    with transaction.atomic():
        deleted_count, _ = qs.delete()
        print(f"Successfully deleted {deleted_count} GAMING records.")

    # 3. Verify PostgreSQL native PL/pgSQL balance engine
    with connection.cursor() as cursor:
        cursor.execute("SELECT fn_get_operational_account_balance(%s);", ['GAMING'])
        row = cursor.fetchone()
        balance_data = row[0]
        if isinstance(balance_data, str):
            balance_data = json.loads(balance_data)

    print("-" * 60)
    print("VERIFIED POST-RESET METRICS (PostgreSQL PL/pgSQL Engine):")
    print(f"  • Total Inflows (Walid / Finance):     {balance_data.get('total_funded_dzd', 0):>10} DZD")
    print(f"  • Total Outflows (Sofiane / Ops):      {balance_data.get('total_spent_dzd', 0):>10} DZD")
    print(f"  • Net Operational Account Balance:     {balance_data.get('current_balance_dzd', 0):>10} DZD")
    print(f"  • Account Status:                      {balance_data.get('status', 'DEPLETED'):>10}")
    print("=" * 60)
    print("Gaming Operations Hub is now completely at 0.00 DZD.")


if __name__ == '__main__':
    reset_gaming_hub_to_zero()
