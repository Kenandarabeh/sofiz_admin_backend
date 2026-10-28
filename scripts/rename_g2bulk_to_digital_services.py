import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import transaction
from monitoring.models import (
    SupplierAccount,
    WithdrawalRecord,
    BaridiMobFundingReceipt,
)


def migrate_g2bulk_to_digital_services():
    """
    Renames all occurrences of 'G2Bulk' in database records to 'Digital Services Account ( g2bulk )'.
    - Updates SupplierAccount name.
    - Updates WithdrawalRecord titles and notes.
    - Updates BaridiMobFundingReceipt notes.
    """
    print("=" * 65)
    print("MIGRATING G2BULK TO Digital Services Account ( g2bulk ) IN DATABASE")
    print("=" * 65)

    with transaction.atomic():
        # 1. Update SupplierAccount
        suppliers = SupplierAccount.objects.filter(provider='G2BULK')
        for sup in suppliers:
            old_name = sup.name
            sup.name = "Digital Services Account ( g2bulk )"
            sup.save(update_fields=['name', 'updated_at'])
            print(f"[1] SupplierAccount #{sup.id}: Renamed '{old_name}' -> '{sup.name}'")

        # 2. Update WithdrawalRecord titles
        withdrawals = WithdrawalRecord.objects.filter(title__icontains='G2Bulk')
        w_count = 0
        for w in withdrawals:
            old_title = w.title
            w.title = w.title.replace('G2Bulk', 'Digital Services Account ( g2bulk )').replace('g2bulk', 'Digital Services Account ( g2bulk )')
            if w.destination_recipient and 'G2Bulk' in w.destination_recipient:
                w.destination_recipient = w.destination_recipient.replace('G2Bulk', 'Digital Services Account ( g2bulk )')
            if w.notes and 'G2Bulk' in w.notes:
                w.notes = w.notes.replace('G2Bulk', 'Digital Services Account ( g2bulk )')
            w.save(update_fields=['title', 'destination_recipient', 'notes', 'updated_at'])
            w_count += 1
            print(f"[2] WithdrawalRecord #{w.id}: Updated title '{old_title}' -> '{w.title}'")
        print(f"Total WithdrawalRecords updated: {w_count}")

        # 3. Update BaridiMobFundingReceipt
        receipts = BaridiMobFundingReceipt.objects.filter(notes__icontains='G2Bulk')
        r_count = 0
        for r in receipts:
            r.notes = r.notes.replace('G2Bulk', 'Digital Services Account ( g2bulk )')
            r.save(update_fields=['notes'])
            r_count += 1
        print(f"[3] Total BaridiMobFundingReceipts updated: {r_count}")

    print("=" * 65)
    print("Database migration completed successfully.")


if __name__ == '__main__':
    migrate_g2bulk_to_digital_services()
