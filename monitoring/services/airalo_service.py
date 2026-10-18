"""
Airalo eSIM Wholesale API Integration Service for SofizAdmin
Queries Airalo Partner API v2 to fetch available wholesale credit balance, check eSIM packages,
and audit working capital allocated to mobile telecom inventory.
"""
import logging
from decimal import Decimal
import os
import httpx
from django.conf import settings
from django.utils import timezone
from ..models import AiraloAccount, MonitoringGlobalSettings

logger = logging.getLogger(__name__)


class AiraloServiceError(Exception):
    pass


class AiraloService:
    BASE_URL = "https://partners-api.airalo.com/v2"

    @classmethod
    def get_credentials(cls):
        """Retrieve Airalo API credentials from settings or environment variables"""
        global_settings = MonitoringGlobalSettings.get_settings()
        client_id = global_settings.airalo_client_id or os.getenv("AIRALO_CLIENT_ID", "")
        client_secret = global_settings.airalo_client_secret or os.getenv("AIRALO_CLIENT_SECRET", "")
        base_url = global_settings.airalo_base_url or os.getenv("AIRALO_BASE_URL", cls.BASE_URL)
        return client_id.strip(), client_secret.strip(), base_url.strip().rstrip('/')

    @classmethod
    def get_access_token(cls, client_id: str, client_secret: str, base_url: str) -> str:
        """Authenticate with Airalo OAuth2 and retrieve access token"""
        token_url = f"{base_url}/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials"
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        with httpx.Client(timeout=3.0) as client:
            resp = client.post(token_url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise AiraloServiceError(f"Airalo Auth Failed ({resp.status_code}): {resp.text}")
            
            data = resp.json()
            token = data.get("data", {}).get("access_token")
            if not token:
                token = data.get("access_token")
            if not token:
                raise AiraloServiceError(f"No access token returned by Airalo: {resp.text}")
            return token

    @classmethod
    def get_available_balance(cls, access_token: str, base_url: str) -> Decimal:
        """Fetch available wholesale balance in USD from Airalo"""
        balance_url = f"{base_url}/balance"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(balance_url, headers=headers)
            if resp.status_code != 200:
                raise AiraloServiceError(f"Airalo Balance Query Failed ({resp.status_code}): {resp.text}")
            
            data = resp.json()
            # Parse available balance
            balances = data.get("data", {}).get("balances", {})
            available = balances.get("availableBalance", {})
            amount = available.get("amount", 0)
            return Decimal(str(amount))

    @classmethod
    def sync_account(cls) -> AiraloAccount:
        """Synchronize live Airalo wholesale credit balance from official partner API"""
        client_id, client_secret, base_url = cls.get_credentials()
        account, _ = AiraloAccount.objects.get_or_create(
            id=1,
            defaults={"account_name": "Official Airalo Partner Account"}
        )

        if not client_id or not client_secret:
            account.last_error = "Airalo API credentials not configured in settings or environment."
            account.last_synced_at = timezone.now()
            account.save()
            return account

        try:
            token = cls.get_access_token(client_id, client_secret, base_url)
            balance_usd = cls.get_available_balance(token, base_url)

            account.available_balance_usd = balance_usd
            account.last_synced_at = timezone.now()
            account.last_error = None
            account.save()
            return account
        except Exception as e:
            account.last_error = f"Airalo live API sync failed: {e}"
            account.last_synced_at = timezone.now()
            account.save()
            return account

    @classmethod
    def get_wholesale_wallet_status(cls):
        """Fetch Airalo Partner Wholesale Balance directly from live API"""
        client_id, client_secret, base_url = cls.get_credentials()
        current_balance = Decimal("0.00")
        source = "live_api"
        last_err = None

        if client_id and client_secret:
            try:
                token = cls.get_access_token(client_id, client_secret, base_url)
                current_balance = cls.get_available_balance(token, base_url)
            except Exception as e:
                logger.warning(f"Airalo live balance fetch failed: {e}")
                last_err = str(e)
        else:
            last_err = "Airalo API credentials not configured"

        account, _ = AiraloAccount.objects.get_or_create(
            id=1,
            defaults={"account_name": "Official Airalo Partner Account"}
        )
        if current_balance > Decimal("0.00") or not account.available_balance_usd:
            account.available_balance_usd = current_balance
        account.last_synced_at = timezone.now()
        account.last_error = last_err
        account.save()

        return {
            "success": last_err is None,
            "source": source,
            "account_name": account.account_name,
            "available_balance_usd": float(account.available_balance_usd or 0.0),
            "currency": "USD",
            "error": last_err
        }

