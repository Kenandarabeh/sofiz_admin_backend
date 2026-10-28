import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from monitoring.models import (
    WithdrawalRecord,
    WithdrawalStage,
    SubSystemType,
    G2BulkReplenishmentWindow,
    StellarWallet,
)


def cancel_old_states(delete_mode=False):
    """
    Cancels or removes old/active in-progress gaming and operation states.
    - Cancels ALLOCATED / BINANCE_P2P records (or deletes if delete_mode=True).
    - If a wallet balance was deducted (e.g. DZT on source_wallet), refunds it back.
    - Closes/expires open replenishment windows.
    """
    print("=" * 65)
    print("FINANCIAL MONITORING - CANCEL OLD STATES SCRIPT")
    print(f"Mode: {'DELETE (Permanent purge)' if delete_mode else 'CANCEL (Mark as CANCELLED & refund balances)'}")
    print("=" * 65)

    # 1. Find all in-progress records (stages ALLOCATED and BINANCE_P2P)
    in_progress_qs = WithdrawalRecord.objects.filter(
        stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]
    ).order_by('id')

    total_in_progress = in_progress_qs.count()
    print(f"\n[1] In-Progress / Unfinished Records Found: {total_in_progress}")

    with transaction.atomic():
        for rec in in_progress_qs:
            print(f"  • ID #{rec.id} | Stage: {rec.stage} | Amount: {rec.amount_dzd:,.2f} DZD | Ref: {rec.reference}")
            
            # Check if any DZT was deducted from source_wallet in notes
            # e.g.: "Deducted available 8,449.50 DZT from [Games Collection & Withdrawal Wallet]"
            if rec.source_wallet:
                try:
                    import re
                    match = re.search(r'Deducted available ([\d,\.]+) DZT', rec.notes or '')
                    if match:
                        deducted_str = match.group(1).replace(',', '')
                        deducted_dzt = Decimal(deducted_str)
                        if deducted_dzt > 0:
                            wallet = StellarWallet.objects.select_for_update().get(id=rec.source_wallet.id)
                            old_bal = wallet.dzt_balance
                            wallet.dzt_balance += deducted_dzt
                            wallet.save(update_fields=['dzt_balance', 'updated_at'])
                            print(f"    -> Refunded {deducted_dzt:,.2f} DZT back to wallet '{wallet.name}' ({old_bal:,.2f} -> {wallet.dzt_balance:,.2f} DZT)")
                except Exception as ex:
                    print(f"    -> Warning while refunding wallet balance: {ex}")

            if delete_mode:
                rec_id = rec.id
                rec.delete()
                print(f"    -> Deleted record #{rec_id} permanently.")
            else:
                rec.stage = WithdrawalStage.CANCELLED
                note_append = "\n• [CANCELLED] In-progress cycle cancelled and voided by administrative script."
                rec.notes = (rec.notes or '') + note_append
                rec.save(update_fields=['stage', 'notes', 'updated_at'])
                print(f"    -> Marked record #{rec.id} as CANCELLED.")

        # 2. Check for any active replenishment windows
        open_windows = G2BulkReplenishmentWindow.objects.filter(status='ACTIVE')
        for win in open_windows:
            win.status = 'COMPLETED'
            win.notes = (win.notes or '') + "\n• Window closed by administrative cancel_old_states script."
            win.save(update_fields=['status', 'notes', 'updated_at'])
            print(f"\n[2] Closed active Replenishment Window ID #{win.id}")

    print("\n" + "-" * 65)
    print("VERIFYING CURRENT ACTIVE IN-PROGRESS PIPELINE:")
    remaining_active = WithdrawalRecord.objects.filter(
        stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P]
    ).count()
    print(f"  • Remaining active in-progress records: {remaining_active}")

    # Display remaining summary by stage
    from django.db.models import Count
    breakdown = list(WithdrawalRecord.objects.values('stage').annotate(cnt=Count('id')))
    print(f"  • Stages in DB: {breakdown}")
    print("=" * 65)
    print("Script execution completed successfully.")


if __name__ == '__main__':
    delete_flag = '--delete' in sys.argv
    cancel_old_states(delete_mode=delete_flag)
