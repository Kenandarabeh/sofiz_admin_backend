"""
Bybit API Integration Service for SofizAdmin eSIM Financial Monitoring
Interacts directly with Bybit V5 API to query live USDT balances across Funding & Unified accounts.
Used to audit USDT earmarked for Visa Card funding in eSIM wholesale operations.
"""
import time
import hmac
import hashlib
import logging
from decimal import Decimal
import os
import httpx
from django.conf import settings
from django.utils import timezone
from ..models import BybitAccount, MonitoringGlobalSettings

logger = logging.getLogger(__name__)


class BybitServiceError(Exception):
    pass


class BybitService:
    BASE_URL = "https://api.bybit.com"

    @classmethod
    def get_credentials(cls):
        """Retrieve Bybit API credentials from settings or environment variables"""
        global_settings = MonitoringGlobalSettings.get_settings()
        api_key = global_settings.bybit_api_key or os.getenv("BYBIT_API_KEY", "")
        api_secret = global_settings.bybit_api_secret or os.getenv("BYBIT_API_SECRET", "")
        user_id = global_settings.bybit_user_id or "477447830"
        return api_key.strip(), api_secret.strip(), user_id.strip()

    @classmethod
    def _generate_signature(cls, timestamp: str, api_key: str, api_secret: str, recv_window: str, params_str: str) -> str:
        """Generate HMAC-SHA256 signature for Bybit V5 API"""
        payload = f"{timestamp}{api_key}{recv_window}{params_str}"
        return hmac.new(
            api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @classmethod
    def get_funding_balance(cls, api_key: str, api_secret: str, coin: str = "USDT") -> Decimal:
        """Fetch balance from Bybit FUND account (used for Card & P2P)"""
        endpoint = "/v5/asset/transfer/query-account-coin-balance"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query_params = f"accountType=FUND&coin={coin}"
        
        signature = cls._generate_signature(timestamp, api_key, api_secret, recv_window, query_params)
        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
        }

        url = f"{cls.BASE_URL}{endpoint}?{query_params}"
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                raise BybitServiceError(f"HTTP {resp.status_code}: {resp.text}")
            
            data = resp.json()
            if data.get("retCode") != 0:
                raise BybitServiceError(f"Bybit API Error {data.get('retCode')}: {data.get('retMsg')}")
            
            balance_data = data.get("result", {}).get("balance", {})
            if isinstance(balance_data, dict):
                wallet_bal = balance_data.get("walletBalance", "0")
                return Decimal(str(wallet_bal))
            elif isinstance(balance_data, list):
                for item in balance_data:
                    if item.get("coin") == coin:
                        wallet_bal = item.get("walletBalance", "0")
                        return Decimal(str(wallet_bal))
            return Decimal("0.0000")

    @classmethod
    def get_unified_balance(cls, api_key: str, api_secret: str, coin: str = "USDT") -> Decimal:
        """Fetch balance from Bybit UNIFIED trading account"""
        endpoint = "/v5/account/wallet-balance"
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query_params = f"accountType=UNIFIED&coin={coin}"
        
        signature = cls._generate_signature(timestamp, api_key, api_secret, recv_window, query_params)
        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
        }

        url = f"{cls.BASE_URL}{endpoint}?{query_params}"
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return Decimal("0.0000")
            
            data = resp.json()
            if data.get("retCode") != 0:
                return Decimal("0.0000")
            
            account_list = data.get("result", {}).get("list", [])
            if account_list:
                coins = account_list[0].get("coin", [])
                for c in coins:
                    if c.get("coin") == coin:
                        wallet_bal = c.get("walletBalance", "0")
                        return Decimal(str(wallet_bal))
            return Decimal("0.0000")

    @classmethod
    def sync_account(cls) -> BybitAccount:
        """Synchronize live Bybit balances from official Bybit V5 API"""
        api_key, api_secret, user_id = cls.get_credentials()
        account, _ = BybitAccount.objects.get_or_create(
            user_id=user_id or "477447830",
            defaults={"account_name": "Official Bybit Corporate Account"}
        )

        if not api_key or not api_secret:
            account.last_error = "Bybit API credentials not configured in settings or environment."
            account.last_synced_at = timezone.now()
            account.update_dzd_equivalent()
            account.save()
            return account

        try:
            funding_bal = cls.get_funding_balance(api_key, api_secret, "USDT")
            unified_bal = cls.get_unified_balance(api_key, api_secret, "USDT")

            account.funding_balance_usdt = funding_bal
            account.unified_balance_usdt = unified_bal
            account.last_synced_at = timezone.now()
            account.last_error = None
            account.update_dzd_equivalent()
            account.save()
            return account
        except Exception as e:
            account.last_error = f"Bybit live API sync failed: {e}"
            account.last_synced_at = timezone.now()
            account.update_dzd_equivalent()
            account.save()
            return account

    @classmethod
    def get_card_transfers(cls, limit: int = 10):
        """Fetch Bybit Visa Card funding transfers directly from live Bybit V5 API"""
        api_key, api_secret, user_id = cls.get_credentials()
        if not api_key or not api_secret:
            return {
                "success": False,
                "source": "live_api",
                "error": "Bybit credentials not configured",
                "transfers": []
            }

        try:
            endpoint = "/v5/asset/transfer/query-sub-member-transfer-list"
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            query_params = f"coin=USDT&limit={limit}"
            signature = cls._generate_signature(timestamp, api_key, api_secret, recv_window, query_params)
            headers = {
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": signature,
            }
            url = f"{cls.BASE_URL}{endpoint}?{query_params}"
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                        return {"success": True, "transfers": data["result"]["list"], "source": "live_api"}
            return {"success": False, "source": "live_api", "transfers": [], "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning(f"Bybit live transfer query failed: {e}")
            return {"success": False, "source": "live_api", "transfers": [], "error": str(e)}

