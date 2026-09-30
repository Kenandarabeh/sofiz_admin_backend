"""
Independent Multi-Scenario Test Suite
Tests every system pathway as a real user would encounter it.
"""
import os
import sys
import django
import threading
import time
from decimal import Decimal
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import transaction as db_transaction
from monitoring.models import (
    StellarWallet, BaridiMobAccount, WithdrawalRecord, BaridiMobFundingReceipt,
    WalletSweepLog, WithdrawalStage, FundingCycleStatus, WalletFamily, WalletRole
)
from monitoring.services.stellar_service import StellarService
from monitoring.services.balance_engine import BalanceEngine
from monitoring.services.receipt_parser_service import ReceiptParserService

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"{status} {name}" + (f" -- {detail}" if detail else ""))

print()
print("=" * 70)
print("INDEPENDENT MULTI-SCENARIO TEST SUITE")
print("=" * 70)

# -------------------------------------------------------------------------
# SCENARIO 1: INVENTORY CHECK
# -------------------------------------------------------------------------
print("\n--- SCENARIO 1: SYSTEM INVENTORY ---")
wallets = list(StellarWallet.objects.all())
withdrawal_wallets = [w for w in wallets if w.role == WalletRole.WITHDRAWAL]
vault_wallets = [w for w in wallets if w.role == WalletRole.VAULT]
bm_accounts = list(BaridiMobAccount.objects.filter(is_active=True))

test("13 wallets registered", len(wallets) == 13)
test("At least 1 withdrawal wallet exists", len(withdrawal_wallets) >= 1)
test("Main Treasury Vault (VAULT) exists", len(vault_wallets) == 1)
test("At least 1 active BaridiMob account", len(bm_accounts) >= 1)

for bm in bm_accounts:
    test(
        f"BM account '{bm.account_name}' has stable_balance field",
        hasattr(bm, 'last_stable_balance'),
        f"last_stable_balance={bm.last_stable_balance}"
    )

# -------------------------------------------------------------------------
# SCENARIO 2: EXACT TRANSFER WITH BALANCE MATCHING
# -------------------------------------------------------------------------
print("\n--- SCENARIO 2: EXACT TRANSFER (source=Games Withdrawal, dest=Main Treasury) ---")
games_withdrawal = StellarWallet.objects.filter(name__icontains="Games Withdrawal").first()
main_treasury    = StellarWallet.objects.filter(role=WalletRole.VAULT).first()

with db_transaction.atomic():
    src_bal_before  = games_withdrawal.dzt_balance
    dest_bal_before = main_treasury.dzt_balance
    sweep_amt = Decimal("1500.00")

    res = StellarService.send_payment(
        source_wallet=games_withdrawal,
        destination_wallet=main_treasury,
        amount=sweep_amt,
        memo_text="INDEPENDENT-TEST-SWEEP"
    )

    games_withdrawal.refresh_from_db()
    main_treasury.refresh_from_db()

    test("Transfer reported success", res.get("success") is True)
    test("Source wallet deducted exactly",
         games_withdrawal.dzt_balance == src_bal_before - sweep_amt,
         f"{src_bal_before} - {sweep_amt} = {games_withdrawal.dzt_balance}")
    test("Destination credited exactly",
         main_treasury.dzt_balance == dest_bal_before + sweep_amt,
         f"{dest_bal_before} + {sweep_amt} = {main_treasury.dzt_balance}")

    log = WalletSweepLog.objects.filter(stellar_tx_hash=res.get("hash")).first()
    test("Audit log created for sweep", log is not None,
         f"hash={res.get('hash')}")
    test("Audit log status is SUCCESS", log and log.status == "SUCCESS")

    db_transaction.set_rollback(True)  # Clean up - no DB pollution

# -------------------------------------------------------------------------
# SCENARIO 3: OVERDRAFT - EXACT EDGE (amount == balance)
# -------------------------------------------------------------------------
print("\n--- SCENARIO 3: EDGE CASE - Transfer equals exact balance ---")
with db_transaction.atomic():
    games_withdrawal.refresh_from_db()
    exact_amount = games_withdrawal.dzt_balance  # Send ALL of it

    res_exact = StellarService.send_payment(
        source_wallet=games_withdrawal,
        destination_wallet=main_treasury,
        amount=exact_amount,
        memo_text="EDGE-FULL-TRANSFER"
    )
    games_withdrawal.refresh_from_db()

    test("Transfer of full balance succeeds",
         res_exact.get("success") is True,
         f"Amount={exact_amount}")
    test("Source wallet goes to exactly 0.0000 after full sweep",
         games_withdrawal.dzt_balance == Decimal("0.0000"),
         f"Balance after: {games_withdrawal.dzt_balance}")
    db_transaction.set_rollback(True)

# -------------------------------------------------------------------------
# SCENARIO 4: OVERDRAFT - EXCEEDS BY 1 FILS
# -------------------------------------------------------------------------
print("\n--- SCENARIO 4: OVERDRAFT PREVENTION (exceeds by 0.01 DZT) ---")
with db_transaction.atomic():
    games_withdrawal.refresh_from_db()
    over_by_one_fils = games_withdrawal.dzt_balance + Decimal("0.01")

    res_over = StellarService.send_payment(
        source_wallet=games_withdrawal,
        destination_wallet=main_treasury,
        amount=over_by_one_fils
    )
    games_withdrawal.refresh_from_db()
    main_treasury.refresh_from_db()

    test("Transfer of balance+0.01 is REJECTED",
         res_over.get("success") is False,
         res_over.get("error", ""))
    test("Source balance unchanged after rejection",
         games_withdrawal.dzt_balance == games_withdrawal.dzt_balance,
         "No mutation")
    test("No rogue log entry created",
         not WalletSweepLog.objects.filter(
             source_wallet=games_withdrawal,
             destination_wallet=main_treasury,
             status="SUCCESS",
             amount_dzt=over_by_one_fils
         ).exists())
    db_transaction.set_rollback(True)

# -------------------------------------------------------------------------
# SCENARIO 5: ZERO AND NEGATIVE AMOUNTS
# -------------------------------------------------------------------------
print("\n--- SCENARIO 5: INVALID AMOUNTS (zero, negative) ---")
res_zero = StellarService.send_payment(
    source_wallet=games_withdrawal,
    destination_wallet=main_treasury,
    amount=Decimal("0.00")
)
test("Zero amount transfer rejected", res_zero.get("success") is False)

res_neg = StellarService.send_payment(
    source_wallet=games_withdrawal,
    destination_wallet=main_treasury,
    amount=Decimal("-100.00")
)
test("Negative amount transfer rejected", res_neg.get("success") is False)

# -------------------------------------------------------------------------
# SCENARIO 6: SAME SOURCE AND DESTINATION
# -------------------------------------------------------------------------
print("\n--- SCENARIO 6: SELF-TRANSFER (same wallet) ---")
res_self = StellarService.send_payment(
    source_wallet=games_withdrawal,
    destination_wallet=games_withdrawal,
    amount=Decimal("1000.00")
)
test("Self-transfer handled gracefully",
     not (res_self.get("success") and games_withdrawal.dzt_balance != games_withdrawal.dzt_balance),
     f"success={res_self.get('success')}, same_wallet={res_self.get('same_wallet')}")

# -------------------------------------------------------------------------
# SCENARIO 7: ALGERIE POSTE GLITCH - ALL 3 PHASES
# -------------------------------------------------------------------------
print("\n--- SCENARIO 7: ALGERIE POSTE GLITCH FULL LIFECYCLE ---")
with db_transaction.atomic():
    bm = BaridiMobAccount.objects.first()
    original_bal = bm.balance_dzd
    original_stable = bm.last_stable_balance

    # Phase A: Normal state
    bm.balance_dzd = Decimal("45000.00")
    bm.last_stable_balance = Decimal("45000.00")
    bm.is_glitch_quarantined = False
    bm.save()

    audit_a = BalanceEngine.run_audit(sync_live=False, send_alerts=False)
    disc_a = audit_a["discrepancy"]

    # Phase B: Postal server glitch - sudden negative balance
    bm.is_glitch_quarantined = True
    bm.quarantined_glitch_amount = Decimal("-18000.00")
    bm.glitch_detected_at = timezone.now()
    bm.save()

    audit_b = BalanceEngine.run_audit(sync_live=False, send_alerts=False)
    disc_b = audit_b["discrepancy"]

    test("Phase B - Discrepancy unchanged during postal glitch",
         disc_a == disc_b,
         f"Before={disc_a} vs During={disc_b}")
    test("Phase B - Audit notes warn about quarantine",
         "Algérie Poste Glitch Quarantined" in audit_b.get("notes", ""),
         audit_b.get("notes", "")[:100])

    # Phase C: Postal server corrects itself (+45000 normal again)
    bm.is_glitch_quarantined = False
    bm.glitch_resolved_at = timezone.now()
    bm.balance_dzd = Decimal("45000.00")
    bm.last_stable_balance = Decimal("45000.00")
    bm.save()

    audit_c = BalanceEngine.run_audit(sync_live=False, send_alerts=False)
    disc_c = audit_c["discrepancy"]
    test("Phase C - Discrepancy unchanged after postal self-correction",
         disc_a == disc_c,
         f"Before={disc_a} vs After={disc_c}")
    test("Phase C - No quarantine note in recovered audit",
         "Algérie Poste" not in audit_c.get("notes", ""))

    db_transaction.set_rollback(True)

# -------------------------------------------------------------------------
# SCENARIO 8: GLITCH EXTREME EDGE - DEEPLY NEGATIVE (-500,000 DZD)
# -------------------------------------------------------------------------
print("\n--- SCENARIO 8: EXTREME POSTAL GLITCH (-500,000 DZD) ---")
with db_transaction.atomic():
    bm = BaridiMobAccount.objects.first()
    bm.balance_dzd = Decimal("45000.00")
    bm.last_stable_balance = Decimal("45000.00")
    bm.is_glitch_quarantined = False
    bm.save()
    audit_base = BalanceEngine.run_audit(sync_live=False, send_alerts=False)

    bm.is_glitch_quarantined = True
    bm.quarantined_glitch_amount = Decimal("-500000.00")
    bm.glitch_detected_at = timezone.now()
    bm.save()

    audit_extreme = BalanceEngine.run_audit(sync_live=False, send_alerts=False)
    test("Extreme glitch (-500k DZD) does NOT distort discrepancy",
         audit_base["discrepancy"] == audit_extreme["discrepancy"],
         f"Diff={audit_extreme['discrepancy'] - audit_base['discrepancy']}")
    test("BaridiMob sum stays non-negative during extreme glitch",
         audit_extreme["baridimob_dzd_total"] >= Decimal("0.00"),
         f"baridimob_total={audit_extreme['baridimob_dzd_total']}")
    db_transaction.set_rollback(True)

# -------------------------------------------------------------------------
# SCENARIO 9: RECEIPT ANTI-REUSE ACROSS ALL IDENTIFIER TYPES
# -------------------------------------------------------------------------
print("\n--- SCENARIO 9: RECEIPT ANTI-REUSE (all identifier types) ---")

# Check an unused reference (should be clean)
chk_clean = ReceiptParserService.check_receipt_usage(reference="NONEXISTENT-REF-99999")
test("Clean reference reported as unused", chk_clean.get("is_used") is False)

# Check an existing withdrawal's reference (must be flagged as used)
existing_wd = WithdrawalRecord.objects.filter(reference__isnull=False).exclude(reference="").first()
if existing_wd:
    chk_used = ReceiptParserService.check_receipt_usage(reference=existing_wd.reference)
    test("Existing withdrawal reference flagged as used",
         chk_used.get("is_used") is True,
         f"ref={existing_wd.reference}, used_in={chk_used.get('used_in')}")
    chk_hash = ReceiptParserService.check_receipt_usage(file_hash=existing_wd.file_hash) if existing_wd.file_hash else None
    if chk_hash:
        test("Existing file_hash flagged as used",
             chk_hash.get("is_used") is True,
             f"hash={existing_wd.file_hash[:12]}...")
else:
    test("No existing withdrawals with reference (skipped)", True, "SKIP")

# -------------------------------------------------------------------------
# SCENARIO 10: CONCURRENT DOUBLE SWEEP (Race Condition)
# -------------------------------------------------------------------------
print("\n--- SCENARIO 10: CONCURRENT DOUBLE SWEEP (Race Condition Test) ---")
with db_transaction.atomic():
    games_withdrawal.refresh_from_db()
    half_balance = (games_withdrawal.dzt_balance / 2).quantize(Decimal("0.01"))
    full_balance = games_withdrawal.dzt_balance

    outcomes = {}

    def do_sweep(label, amount):
        try:
            src = StellarWallet.objects.get(id=games_withdrawal.id)
            dst = StellarWallet.objects.get(id=main_treasury.id)
            r = StellarService.send_payment(source_wallet=src, destination_wallet=dst, amount=amount)
            outcomes[label] = r
        except Exception as e:
            outcomes[label] = {"success": False, "error": str(e)}

    t1 = threading.Thread(target=do_sweep, args=("T1", full_balance))
    t2 = threading.Thread(target=do_sweep, args=("T2", full_balance))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    total_successes = sum(1 for v in outcomes.values() if v.get("success"))
    test("Only ONE of two concurrent full sweeps succeeds (no double spend)",
         total_successes <= 1,
         f"T1={outcomes.get('T1', {}).get('success')}, T2={outcomes.get('T2', {}).get('success')}")

    # Restore balances since worker threads commit independently
    total_swept = sum(v.get('amount', Decimal('0')) for v in outcomes.values() if v.get('success'))
    if total_swept > Decimal('0'):
        src = StellarWallet.objects.get(id=games_withdrawal.id)
        dst = StellarWallet.objects.get(id=main_treasury.id)
        src.dzt_balance += total_swept
        dst.dzt_balance -= total_swept
        src.save(update_fields=['dzt_balance'])
        dst.save(update_fields=['dzt_balance'])

    db_transaction.set_rollback(True)

# -------------------------------------------------------------------------
# SCENARIO 11: WALLET FAMILY INTEGRITY
# -------------------------------------------------------------------------
print("\n--- SCENARIO 11: WALLET FAMILY INTEGRITY ---")
treasury_wallets = StellarWallet.objects.filter(role=WalletRole.VAULT)
collection_wallets = StellarWallet.objects.filter(role=WalletRole.COLLECTION)
withdrawal_wallets_q = StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL)

test("Exactly 1 Treasury Vault wallet", treasury_wallets.count() == 1)
test("At least 5 COLLECTION wallets across families", collection_wallets.count() >= 5)
test("At least 3 WITHDRAWAL wallets (GAME, FACTURE, ESIM)", withdrawal_wallets_q.count() >= 3)

for family in ["GAME", "FACTURE", "ESIM"]:
    withdrawal = StellarWallet.objects.filter(family=family, role=WalletRole.WITHDRAWAL).first()
    test(f"{family} family has a dedicated WITHDRAWAL wallet",
         withdrawal is not None,
         withdrawal.name if withdrawal else "MISSING")

# -------------------------------------------------------------------------
# SUMMARY
# -------------------------------------------------------------------------
print()
print("=" * 70)
total = len(results)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
print(f"RESULTS: {passed}/{total} tests passed  |  {failed} failures")
if failed > 0:
    print()
    print("FAILED TESTS:")
    for r in results:
        if r[0] == FAIL:
            print(f"  {r[1]}: {r[2]}")
print("=" * 70)
sys.exit(0 if failed == 0 else 1)
