"""
BaridiMob Live Balance & Settlement Service for SofizAdmin
Calls Epay BaridiMob Financial API to fetch real-time DZD balances, accounts, and transactions using Master Admin API Key.
"""
import logging
from decimal import Decimal
from datetime import datetime
import os
import httpx
from django.utils import timezone
from django.db import transaction, models
from ..models import (
    BaridiMobAccount,
    BaridiMobTransaction,
    MonitoringGlobalSettings,
    UtilityBillRecord,
    UtilityServiceType,
    SubSystemType,
)

logger = logging.getLogger(__name__)


class BaridiMobService:
    @classmethod
    def get_api_auth(cls):
        global_settings = MonitoringGlobalSettings.get_settings()
        base_url = (global_settings.epay_api_url or "https://epay.sofizpay.com/api/operations").rstrip('/')
        api_key = global_settings.epay_api_key
        headers = {
            "X-API-KEY": api_key,
            "Accept": "application/json"
        }
        return base_url, headers

    @classmethod
    @classmethod
    def sync_baridi_balance(cls, account_key: str = None) -> dict:
        """
        Calls Epay BaridiMob Financial API for 'game' (Salah Gaming Account) or 'facture' (Sihaam Bills).
        Updates BaridiMobAccount in local database with real-time liquid balance.
        """
        from ..models import SubSystemType
        base_url, headers = cls.get_api_auth()

        # Handle 'all' to sync both accounts in sequence
        if account_key == 'all':
            res_game = cls.sync_baridi_balance(account_key='game')
            res_facture = cls.sync_baridi_balance(account_key='facture')
            return {
                "success": res_game.get("success", False) or res_facture.get("success", False),
                "game": res_game,
                "facture": res_facture,
            }

        # Determine target endpoint and metadata
        if account_key == 'game':
            endpoints = [
                f"{base_url}/financial/baridimob/game/balance/",
                f"{base_url}/financial/game/balance/",
            ]
            default_label = "salahsofi"
            default_rip = "00799999001738866535"
            default_name = "Salah Gaming Account (salahsofi)"
            system_type = SubSystemType.GAMING
        else:
            endpoints = [
                f"{base_url}/financial/baridimob/facture/balance/",
                f"{base_url}/financial/baridimob/balance/",
            ]
            default_label = "Sihaam31"
            default_rip = "00799999004166560419"
            default_name = "BaridiMob Main Settlement Account (Sihaam31)"
            system_type = SubSystemType.UTILITY

        last_error = None
        for endpoint in endpoints:
            try:
                with httpx.Client(timeout=15.0) as client:
                    res = client.get(endpoint, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        accounts = data.get("accounts", [])
                        total_balance = Decimal(str(data.get("total_balance_dzd") or data.get("balance_dzd") or "0.00"))
                        if system_type == SubSystemType.GAMING:
                            account_label = "salahsofi"
                        else:
                            raw_label = data.get("account_label") or data.get("label")
                            account_label = "Sihaam31" if raw_label == 'facture' else (raw_label or default_label)

                        acc_number = default_rip
                        if accounts:
                            acc_number = str(accounts[0].get("number", default_rip))
                            if total_balance == 0 and "balance" in accounts[0]:
                                total_balance = Decimal(str(accounts[0].get("balance", "0.00")))

                        acc = BaridiMobAccount.objects.filter(rip_number=acc_number).first()
                        if not acc:
                            acc = BaridiMobAccount.objects.filter(system_type=system_type).first()

                        now = timezone.now()
                        if not acc:
                            acc = BaridiMobAccount.objects.create(
                                account_name=default_name,
                                rip_number=acc_number,
                                account_email=account_label,
                                system_type=system_type,
                                balance_dzd=max(Decimal("0.00"), total_balance),
                                last_stable_balance=max(Decimal("0.00"), total_balance),
                                is_glitch_quarantined=(total_balance < Decimal("0.00")),
                                quarantined_glitch_amount=total_balance if total_balance < Decimal("0.00") else Decimal("0.00"),
                                glitch_detected_at=now if total_balance < Decimal("0.00") else None,
                                is_active=True,
                                last_synced_at=now,
                                notes="Primary Gaming Working Capital Account whitelisted for game top-up operations and wholesale disbursement." if system_type == SubSystemType.GAMING else None
                            )
                        else:
                            # Institutional Anomaly Detection: Algérie Poste Negative Hold / Server Glitch
                            if total_balance < Decimal("0.00"):
                                if not acc.is_glitch_quarantined:
                                    acc.is_glitch_quarantined = True
                                    acc.quarantined_glitch_amount = total_balance
                                    acc.glitch_detected_at = now
                                    if acc.balance_dzd > Decimal("0.00"):
                                        acc.last_stable_balance = acc.balance_dzd
                                    glitch_msg = f"[Algérie Poste Glitch Quarantined @ {now.strftime('%Y-%m-%d %H:%M:%S')}]: Reported negative balance {total_balance:,.2f} DZD without commercial overdraft. Quarantined with stable balance {acc.last_stable_balance:,.2f} DZD to preserve accounting integrity."
                                    acc.notes = (acc.notes or '').strip() + f"\n• {glitch_msg}"
                                    logger.warning(glitch_msg)
                                else:
                                    acc.quarantined_glitch_amount = total_balance
                            else:
                                if acc.is_glitch_quarantined:
                                    # Postal server self-corrected and hold cleared!
                                    acc.is_glitch_quarantined = False
                                    acc.glitch_resolved_at = now
                                    resolve_msg = f"[Algérie Poste Glitch Resolved @ {now.strftime('%Y-%m-%d %H:%M:%S')}]: Postal balance self-corrected from {acc.quarantined_glitch_amount:,.2f} DZD to {total_balance:,.2f} DZD."
                                    acc.notes = (acc.notes or '').strip() + f"\n• {resolve_msg}"
                                    logger.info(resolve_msg)
                                acc.balance_dzd = total_balance
                                acc.last_stable_balance = total_balance

                            acc.rip_number = acc_number
                            acc.account_email = account_label
                            acc.system_type = system_type
                            acc.last_synced_at = now
                            acc.save(update_fields=[
                                'balance_dzd', 'last_stable_balance', 'is_glitch_quarantined',
                                'quarantined_glitch_amount', 'glitch_detected_at', 'glitch_resolved_at',
                                'rip_number', 'account_email', 'system_type', 'last_synced_at', 'notes'
                            ])

                        logger.info(f"Live BaridiMob balance synced for [{system_type}] ({acc.account_name}): {total_balance:,.2f} DZD")
                        return {
                            "success": True,
                            "account_key": account_key or 'facture',
                            "balance_dzd": total_balance,
                            "account_number": acc_number,
                            "account_label": account_label,
                            "account_name": acc.account_name,
                            "system_type": acc.system_type,
                            "account": acc
                        }
                    else:
                        last_error = f"HTTP {res.status_code}: {res.text}"
            except Exception as e:
                last_error = str(e)

        logger.error(f"Failed to sync BaridiMob balance for [{account_key}]: {last_error}")
        return {"success": False, "error": last_error}

    @classmethod
    def fetch_live_transactions(cls, account_key: str = 'facture', limit: int = 50, fetch_all: bool = True, max_pages: int = 35) -> dict:
        """
        Calls Epay BaridiMob Financial API to fetch real-time raw transaction ledger.
        Supports 'facture' (Sihaam31) or 'game' (salahsofi).
        When fetch_all=True, automatically paginates through all available pages.
        """
        base_url, headers = cls.get_api_auth()
        if account_key == 'game':
            endpoint = f"{base_url}/financial/baridimob/game/transactions/"
            default_label = "salahsofi"
        else:
            endpoint = f"{base_url}/financial/baridimob/facture/transactions/"
            default_label = "Sihaam31"

        all_transactions = []
        page = 1
        account_label = default_label

        try:
            with httpx.Client(timeout=30.0) as client:
                while True:
                    params = {"page": page, "limit": limit}
                    res = client.get(endpoint, headers=headers, params=params)
                    if res.status_code == 200:
                        data = res.json()
                        txs = data.get("transactions", [])
                        if not txs:
                            break
                        all_transactions.extend(txs)
                        account_label = data.get("account_label", account_label)
                        has_next = data.get("has_next_page", False)
                        if not has_next or not fetch_all or page >= max_pages:
                            break
                        page += 1
                    elif account_key != 'game' and page == 1:
                        # Fallback to general endpoint for backward compatibility
                        fallback_ep = f"{base_url}/financial/baridimob/transactions/"
                        res2 = client.get(fallback_ep, headers=headers, params=params)
                        if res2.status_code == 200:
                            data2 = res2.json()
                            txs2 = data2.get("transactions", [])
                            all_transactions.extend(txs2)
                            account_label = data2.get("account_label", default_label)
                            has_next2 = data2.get("has_next_page", False)
                            if not has_next2 or not fetch_all or page >= max_pages:
                                break
                            page += 1
                        else:
                            break
                    else:
                        break

            return {
                "success": True,
                "count": len(all_transactions),
                "transactions": all_transactions,
                "account_label": account_label
            }
        except Exception as e:
            logger.error(f"Exception fetching BaridiMob transactions: {e}")
            return {"success": False, "error": str(e), "transactions": all_transactions}

    @classmethod
    def sync_live_transactions_to_db(cls, account_key: str = None, limit: int = 50, fetch_all: bool = True) -> dict:
        """
        Fetches live transactions from BaridiMob across all pages and permanently archives ALL transactions into
        BaridiMobTransaction ledger, while also reconciling utility bill payments into UtilityBillRecord.
        Accurately identifies and separates Postal / Bank fee deductions from client paid utility bills.
        """
        # If 'all' or None, sync both accounts
        keys_to_sync = ['facture', 'game'] if (account_key in ('all', None) or not account_key) else [account_key]
        total_synced = 0
        all_errors = []

        for key in keys_to_sync:
            tx_data = cls.fetch_live_transactions(account_key=key, limit=limit, fetch_all=fetch_all)
            if not tx_data.get("success"):
                all_errors.append(f"[{key}]: {tx_data.get('error')}")
                continue

            transactions = tx_data.get("transactions", [])
            label = tx_data.get("account_label") or ("salahsofi" if key == 'game' else "Sihaam31")

            # Locate target account
            target_system = SubSystemType.GAMING if key == 'game' else SubSystemType.UTILITY
            acc = BaridiMobAccount.objects.filter(account_email__icontains=label).first() or \
                  BaridiMobAccount.objects.filter(system_type=target_system).first() or \
                  BaridiMobAccount.objects.filter(is_active=True).first()

            if not acc:
                logger.warning(f"No BaridiMobAccount found to link transactions for [{key}] ({label})")
                continue

            with transaction.atomic():
                for tx in transactions:
                    tid = str(tx.get("tid") or tx.get("uid") or tx.get("id") or "").strip()
                    if not tid:
                        continue

                    amount = Decimal(str(tx.get("amount") or 0.0))
                    desc = tx.get("description") or tx.get("type") or ""
                    tx_type = tx.get("type") or tx.get("businessType") or "GENERIC"

                    # Determine fee amount and operation classification
                    fee_amount = Decimal(str(tx.get("feeAmount") or 0.0))

                    # Operation code and Bank Fee classification
                    is_bank_fee = False
                    if "atm" in tx_type.lower() or "withdrawal" in tx_type.lower():
                        operation_code = "GAB_WITHDRAWAL"
                        if fee_amount == Decimal("0.00"):
                            fee_amount = Decimal("30.00")  # Algérie Poste GAB transaction fee
                    elif "transfer to" in tx_type.lower() or "virement émis" in tx_type.lower():
                        operation_code = "TRANSFER_OUT"
                    elif "transfer from" in tx_type.lower() or "virement reçu" in tx_type.lower():
                        operation_code = "TRANSFER_IN"
                    elif "reversal" in tx_type.lower() or "reversal" in desc.lower():
                        operation_code = "REVERSAL"
                    elif "bill" in tx_type.lower() or "topup" in tx_type.lower():
                        operation_code = "BILL_PAYMENT"
                    else:
                        operation_code = "GENERIC"

                    # Check if standalone postal / bank fee deduction
                    fee_keywords = ["fee", "frais", "agio", "timbre", "commission", "tenue de compte", "abonnement"]
                    if any(kw in tx_type.lower() or kw in desc.lower() for kw in fee_keywords):
                        is_bank_fee = True
                        operation_code = "POSTAL_FEE"

                    ref_num = None
                    avail_bal = None
                    for d in tx.get("details", []):
                        lbl = str(d.get("label", "")).lower()
                        d_id = str(d.get("id", ""))
                        if d_id == "refNum" or "reference" in lbl:
                            ref_num = str(d.get("value") or "").strip()
                        if d_id == "availableBalance" or "balance" in lbl:
                            val_str = str(d.get("value", "")).replace("DZD", "").replace(",", "").strip()
                            try:
                                avail_bal = Decimal(val_str)
                            except Exception:
                                pass

                    raw_ts = str(tx.get("timestamp") or "")
                    if raw_ts and len(raw_ts) == 14:
                        try:
                            tx_date = datetime.strptime(raw_ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                        except Exception:
                            tx_date = timezone.now()
                    else:
                        tx_date = timezone.now()

                    # 1. Permanently Archive ALL Transactions in BaridiMobTransaction
                    BaridiMobTransaction.objects.update_or_create(
                        account=acc,
                        tid=tid,
                        defaults={
                            "ref_num": ref_num,
                            "amount": amount,
                            "fee_amount": fee_amount,
                            "transaction_type": tx_type,
                            "operation_code": operation_code,
                            "is_bank_fee": is_bank_fee,
                            "description": desc,
                            "available_balance": avail_bal,
                            "transaction_date": tx_date,
                            "raw_data": tx,
                        }
                    )
                    total_synced += 1

                # Reconcile reversals: Identify bill payments that were reversed within seconds
                rev_refs = set(BaridiMobTransaction.objects.filter(
                    account=acc, operation_code="REVERSAL"
                ).exclude(ref_num__isnull=True).exclude(ref_num="").values_list("ref_num", flat=True))

                # Update reversed bill payment transactions to REVERSED_BILL
                if rev_refs:
                    BaridiMobTransaction.objects.filter(
                        account=acc, ref_num__in=rev_refs, operation_code="BILL_PAYMENT"
                    ).update(operation_code="REVERSED_BILL")
                    # Clean up false utility bills that were reversed and never settled
                    UtilityBillRecord.objects.filter(bill_reference__in=rev_refs).delete()

                # Reconcile genuine, unreversed bill payments into UtilityBillRecord
                for tx_obj in BaridiMobTransaction.objects.filter(account=acc, operation_code="BILL_PAYMENT"):
                    grp = (tx_obj.raw_data.get("operationGroup") or "").upper() if tx_obj.raw_data else ""
                    if "SONELGAZ" in grp:
                        service = UtilityServiceType.SONELGAZ
                    elif "ADE" in grp or "EAUX" in grp:
                        service = UtilityServiceType.ADE
                    else:
                        service = UtilityServiceType.ALGERIE_TELECOM

                    dyn = tx_obj.raw_data.get("dynamicParams") or {} if tx_obj.raw_data else {}
                    bill_ref = tx_obj.ref_num or dyn.get("bill_radio") or dyn.get("customerNumber") or f"BM-{tx_obj.tid}"
                    cust_acc = dyn.get("customerNumber") or ""

                    UtilityBillRecord.objects.update_or_create(
                        bill_reference=bill_ref,
                        defaults={
                            "service": service,
                            "customer_account": cust_acc,
                            "bill_amount_dzd": abs(tx_obj.amount),
                            "commission_earned_dzd": Decimal("50.00"),
                            "is_settled": True,
                            "baridimob_account": acc,
                            "payment_date": tx_obj.transaction_date,
                        }
                    )

        logger.info(f"Permanently archived {total_synced} BaridiMob transactions across accounts in DB")
        return {"success": True, "count": total_synced, "errors": all_errors}

    @classmethod
    def sync_account_balance(cls, account: BaridiMobAccount = None) -> dict:
        """
        Synchronizes live balance for a BaridiMob account and automatically archives all transactions.
        Compatible interface for API views and external callers.
        """
        account_key = 'game' if account and account.system_type == SubSystemType.GAMING else 'facture'
        res = cls.sync_baridi_balance(account_key=account_key)
        if not res.get("success"):
            raise Exception(res.get("error", "Failed to sync BaridiMob account balance"))
        return res
