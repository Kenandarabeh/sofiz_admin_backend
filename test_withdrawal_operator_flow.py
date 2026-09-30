"""
Verification test for Withdrawal Operations Officer & Direct Reçu Deduction
"""
import os
import django
from decimal import Decimal
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from rest_framework.test import APIRequestFactory, force_authenticate
from monitoring.models import (
    StellarWallet, BaridiMobAccount, WithdrawalRecord,
    WalletSweepLog, ExpenseRecord, WithdrawalStage, WalletFamily, WalletRole
)
from monitoring.api_views import WithdrawalRecordViewSet
from monitoring.services.balance_engine import BalanceEngine
from monitoring.services.rbac_service import RBACService

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"{status} {name}" + (f" -- {detail}" if detail else ""))

print("=" * 70)
print("TESTING WITHDRAWAL OPERATIONS OFFICER & DIRECT REÇU DEDUCTION")
print("=" * 70)

# 1. User and Role Verification
user = User.objects.filter(username='walid_withdrawal').first()
test("User 'walid_withdrawal' exists", user is not None)
role_info = RBACService.get_user_role_info(user)
test("Role badge is 'Withdrawal Operations Officer'",
     role_info.get('name') == 'Withdrawal Operations Officer',
     f"badge={role_info.get('name')}")
test("User has add_withdrawalrecord permission",
     user.has_perm('monitoring.add_withdrawalrecord'))

# 2. Direct Reçu Deduction on Gaming Account
factory = APIRequestFactory()
view = WithdrawalRecordViewSet.as_view({'post': 'create'})

games_withdrawal = StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, family=WalletFamily.GAME).first()
main_treasury = StellarWallet.objects.filter(role=WalletRole.VAULT).first()

print(f"\nBefore test: Games Withdrawal Wallet balance = {games_withdrawal.dzt_balance} DZT")
print(f"Before test: Main Treasury Wallet balance = {main_treasury.dzt_balance} DZT")

initial_games_bal = games_withdrawal.dzt_balance
initial_treasury_bal = main_treasury.dzt_balance
test_amount = Decimal("25000.00")

with db_transaction.atomic():
    # Construct synthetic valid BaridiMob receipt payload
    import hashlib
    content = b"PDF-RECEIPT-CONTENT-WALID-OPERATOR-TEST"
    f_hash = hashlib.sha256(content).hexdigest()
    ref_num = f"BM-TEST-{int(timezone.now().timestamp())}"

    # We mock ReceiptParserService.parse_receipt during the request
    from unittest.mock import patch

    mock_parsed = {
        'amount_dzd': test_amount,
        'reference': ref_num,
        'fee_dzd': Decimal("50.00"),
        'sender_rip': '00799999001738866533',
        'recipient_rip': '00799999002233445566',
        'file_hash': f_hash,
        'receipt_date': timezone.now().date(),
        'account_verification': {
            'is_registered': True,
            'account_id': BaridiMobAccount.objects.first().id,
            'account_name': 'BaridiMob Main Settlement Account',
            'rip_number': '00799999002233445566'
        }
    }

    dummy_file = SimpleUploadedFile("recu_today.pdf", content, content_type="application/pdf")

    with patch('monitoring.services.receipt_parser_service.ReceiptParserService.parse_receipt', return_value=mock_parsed):
        with patch('monitoring.services.receipt_parser_service.ReceiptParserService.check_receipt_usage', return_value={'is_used': False}):
            request = factory.post(
                '/api/monitoring/withdrawals/',
                {
                    'title': 'G2Bulk Wholesale Balance Funding (Binance P2P)',
                    'purpose_code': 'G2BULK_P2P',
                    'system_type': 'GAMING',
                    'withdrawal_type': 'SUPPLIER_FUNDING',
                    'receipt_file': dummy_file,
                    'notes': 'Test automated deduction by Walid'
                },
                format='multipart'
            )
            force_authenticate(request, user=user)
            response = view(request)

    print("\nAPI Response status code:", response.status_code)
    test("Withdrawal creation returned HTTP 201 CREATED", response.status_code == 201)

    games_withdrawal.refresh_from_db()
    main_treasury.refresh_from_db()

    # Verify deduction from Games Withdrawal Wallet
    expected_games_bal = initial_games_bal - test_amount
    expected_treasury_bal = initial_treasury_bal + test_amount

    test(f"Games Withdrawal Wallet deducted by {test_amount} DZT",
         games_withdrawal.dzt_balance == expected_games_bal,
         f"Actual: {games_withdrawal.dzt_balance} vs Expected: {expected_games_bal}")

    test(f"Main Treasury Vault credited by {test_amount} DZT",
         main_treasury.dzt_balance == expected_treasury_bal,
         f"Actual: {main_treasury.dzt_balance} vs Expected: {expected_treasury_bal}")

    # Verify audit log & expense creation
    log = WalletSweepLog.objects.filter(
        source_wallet=games_withdrawal,
        destination_wallet=main_treasury,
        amount_dzt=test_amount
    ).first()
    test("Audit log (WalletSweepLog) created with SUCCESS status",
         log is not None and log.status == "SUCCESS",
         f"hash={log.stellar_tx_hash if log else 'None'}")

    fee_exp = ExpenseRecord.objects.filter(reference=ref_num).first()
    test("BaridiMob 50 DZD transfer fee auto-logged in ExpenseRecord",
         fee_exp is not None and fee_exp.amount_dzd == Decimal("50.00"))

    # Verify Golden Equation during this in-transit state
    audit = BalanceEngine.run_audit(sync_live=False, send_alerts=False)
    test("Withdrawal counted under in_transit_dzd_total in BalanceEngine",
         audit.get('in_transit_dzd_total') >= test_amount,
         f"in_transit={audit.get('in_transit_dzd_total')}")

    # Roll back test data to prevent DB pollution
    db_transaction.set_rollback(True)

# 3. Overdraft Protection Test
print("\n--- Overdraft Liquidity Check ---")
with db_transaction.atomic():
    games_withdrawal.refresh_from_db()
    insufficient_amt = (games_withdrawal.dzt_balance + Decimal("100000.00")).quantize(Decimal("0.01"))

    mock_over = mock_parsed.copy()
    mock_over['amount_dzd'] = insufficient_amt
    mock_over['reference'] = "BM-OVERDRAFT-TEST"
    dummy_file_over = SimpleUploadedFile("recu_over.pdf", content, content_type="application/pdf")

    with patch('monitoring.services.receipt_parser_service.ReceiptParserService.parse_receipt', return_value=mock_over):
        with patch('monitoring.services.receipt_parser_service.ReceiptParserService.check_receipt_usage', return_value={'is_used': False}):
            request = factory.post(
                '/api/monitoring/withdrawals/',
                {
                    'title': 'G2Bulk Overdraft Test',
                    'purpose_code': 'G2BULK_P2P',
                    'system_type': 'GAMING',
                    'withdrawal_type': 'SUPPLIER_FUNDING',
                    'receipt_file': dummy_file_over,
                },
                format='multipart'
            )
            force_authenticate(request, user=user)
            response_over = view(request)

    test("Overdraft creation rejected with HTTP 400 Bad Request",
         response_over.status_code == 400,
         f"status={response_over.status_code}")
    test("Error message explains liquidity issue",
         "liquidity" in str(response_over.data).lower(),
         str(response_over.data)[:100])

    db_transaction.set_rollback(True)

print("=" * 70)
passed = sum(1 for r in results if r[0] == PASS)
total = len(results)
print(f"RESULTS: {passed}/{total} tests passed")
print("=" * 70)
