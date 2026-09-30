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
from ..models import BaridiMobAccount, MonitoringGlobalSettings, UtilityBillRecord, UtilityServiceType

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
    def fetch_live_transactions(cls, limit: int = 15) -> dict:
        """
        Calls GET https://epay.sofizpay.com/api/operations/financial/baridimob/transactions/?limit=...
        Returns real-time raw transaction ledger from BaridiMob.
        """
        base_url, headers = cls.get_api_auth()
        endpoint = f"{base_url}/financial/baridimob/transactions/"
        params = {"limit": limit}

        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.get(endpoint, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "success": True,
                        "count": data.get("count", 0),
                        "transactions": data.get("transactions", []),
                        "account_label": data.get("account_label", "Sihaam31")
                    }
                else:
                    logger.error(f"HTTP {res.status_code} fetching BaridiMob transactions: {res.text}")
                    return {"success": False, "error": f"HTTP {res.status_code}: {res.text}", "transactions": []}
        except Exception as e:
            logger.error(f"Exception fetching BaridiMob transactions: {e}")
            return {"success": False, "error": str(e), "transactions": []}

    @classmethod
    def sync_live_transactions_to_db(cls, limit: int = 25) -> dict:
        """
        Fetches live transactions from BaridiMob and reconciles them into UtilityBillRecord.
        Provides audit verification between BaridiMob debit records and Utility bill payments.
        """
        tx_data = cls.fetch_live_transactions(limit=limit)
        if not tx_data.get("success"):
            return {"success": False, "error": tx_data.get("error")}

        transactions = tx_data.get("transactions", [])
        acc = BaridiMobAccount.objects.filter(is_active=True).first()
        synced_count = 0

        with transaction.atomic():
            for tx in transactions:
                grp = (tx.get("operationGroup") or "").upper()
                if "SONELGAZ" in grp:
                    service = UtilityServiceType.SONELGAZ
                elif "ADE" in grp or "EAUX" in grp:
                    service = UtilityServiceType.ADE
                else:
                    service = UtilityServiceType.ALGERIE_TELECOM

                dyn = tx.get("dynamicParams") or {}
                bill_ref = dyn.get("bill_radio") or dyn.get("customerNumber") or f"BM-{tx.get('uid')}"
                cust_acc = dyn.get("customerNumber") or ""
                amount = Decimal(str(tx.get("amount") or 0.0))

                raw_ts = str(tx.get("timestamp") or "")
                if raw_ts and len(raw_ts) == 14:
                    try:
                        payment_date = datetime.strptime(raw_ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                    except Exception:
                        payment_date = timezone.now()
                else:
                    payment_date = timezone.now()

                UtilityBillRecord.objects.update_or_create(
                    bill_reference=bill_ref,
                    defaults={
                        "service": service,
                        "customer_account": cust_acc,
                        "bill_amount_dzd": amount,
                        "commission_earned_dzd": Decimal("50.00"),
                        "is_settled": True,
                        "baridimob_account": acc,
                        "payment_date": payment_date,
                    }
                )
                synced_count += 1

        logger.info(f"Reconciled {synced_count} live BaridiMob utility bills into database")
        return {"success": True, "count": synced_count}

    @classmethod
    def sync_account_balance(cls, account: BaridiMobAccount = None) -> dict:
        """
        Synchronizes live balance for a BaridiMob account.
        Compatible interface for API views and external callers.
        """
        res = cls.sync_baridi_balance()
        if not res.get("success"):
            raise Exception(res.get("error", "Failed to sync BaridiMob account balance"))
        return res
