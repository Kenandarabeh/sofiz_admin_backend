"""
G2Bulk API Integration Service for SofizAdmin Financial Monitoring
Interacts directly with G2Bulk API to query live supplier balance and account details.
"""
import logging
from decimal import Decimal
import os
from django.conf import settings
from django.utils import timezone
import httpx
from ..models import SupplierAccount, MonitoringGlobalSettings

logger = logging.getLogger(__name__)


class G2BulkError(Exception):
    pass


class G2BulkAuthError(G2BulkError):
    pass


class G2BulkService:
    @staticmethod
    def get_api_key(supplier: SupplierAccount = None) -> str:
        """Resolve API Key priority: supplier model -> global settings -> os.environ"""
        if supplier and supplier.api_key:
            return supplier.api_key.strip()
        
        global_settings = MonitoringGlobalSettings.get_settings()
        if global_settings.g2bulk_api_key:
            return global_settings.g2bulk_api_key.strip()
            
        env_key = os.getenv("G2BULK_API_KEY") or getattr(settings, "G2BULK_API_KEY", None)
        if env_key:
            return env_key.strip()
            
        raise G2BulkAuthError("G2Bulk API key is not configured. Please add it in Financial Settings or .env.")

    @classmethod
    def get_me(cls, api_key: str = None, base_url: str = None) -> dict:
        """
        Fetch authenticated user details and live balance from G2Bulk API.
        Endpoint: /getMe (or /me)
        Returns:
            {
                "success": true,
                "user_id": 123456,
                "username": "johndoe",
                "first_name": "John Doe",
                "balance": 8.74
            }
        """
        global_settings = MonitoringGlobalSettings.get_settings()
        key = api_key or cls.get_api_key()
        endpoint_base = base_url or global_settings.g2bulk_base_url.rstrip('/')

        headers = {
            "X-API-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Try /getMe first (official G2Bulk endpoint) and fallback to /me if needed
        urls_to_try = [f"{endpoint_base}/getMe", f"{endpoint_base}/me"]

        last_err = None
        for url in urls_to_try:
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, headers=headers)
                    if response.status_code == 401:
                        raise G2BulkAuthError(f"Authentication failed: {response.text}")
                    elif response.status_code == 200:
                        data = response.json()
                        user_info = data.get("data", data)
                        
                        balance_val = user_info.get("balance", 0)
                        try:
                            balance_decimal = Decimal(str(balance_val))
                        except Exception:
                            balance_decimal = Decimal("0.0000")

                        user_id = str(user_info.get("user_id") or user_info.get("id") or "")
                        username = str(user_info.get("username") or user_info.get("first_name") or "")

                        return {
                            "balance_usd": balance_decimal,
                            "user_id": user_id,
                            "username": username,
                            "first_name": str(user_info.get("first_name", "")),
                            "raw": data
                        }
                    else:
                        last_err = f"HTTP {response.status_code}: {response.text}"
            except (G2BulkAuthError, G2BulkError):
                raise
            except Exception as e:
                last_err = str(e)

        raise G2BulkError(f"G2Bulk API unreachable ({last_err})")

    @classmethod
    def sync_supplier(cls, supplier: SupplierAccount = None) -> dict:
        """Sync live balance for G2Bulk supplier account in DB from official G2Bulk API"""
        if supplier is None:
            supplier, _ = SupplierAccount.objects.get_or_create(
                provider='G2BULK',
                defaults={'name': 'G2Bulk Official Account'}
            )
        try:
            api_key = cls.get_api_key(supplier)
            res = cls.get_me(api_key=api_key)
            supplier.balance_usd = res["balance_usd"]
            if res.get("user_id"):
                supplier.account_uid = res["user_id"]
            if res.get("username"):
                supplier.account_username = res["username"]
                
            supplier.update_dzd_equivalent()
            supplier.last_synced_at = timezone.now()
            supplier.last_error = None
            supplier.save()

            # Record time-series audit tracking snapshot in database
            try:
                from .account_monitoring_service import AccountMonitoringService
                from ..models import AccountMonitoringChannel
                AccountMonitoringService.record_snapshot(
                    channel=AccountMonitoringChannel.G2BULK,
                    account_label="G2Bulk Wholesale Inventory",
                    activity="Gaming",
                    source_type="G2Bulk",
                    current_balance=supplier.balance_usd,
                    currency="USD",
                    current_balance_dzd=supplier.balance_dzd_equivalent,
                    trigger_type="LIVE_API_SYNC",
                    last_synced_at=supplier.last_synced_at,
                    notes=f"Live G2Bulk API sync snapshot: ${supplier.balance_usd:,.2f} USD ({supplier.balance_dzd_equivalent:,.2f} DZD)",
                )
            except Exception as snap_err:
                logger.debug(f"Snapshot tracking note: {snap_err}")

            return {
                "success": True,
                "is_simulation": False,
                "supplier": supplier,
                "balance_usd": supplier.balance_usd,
                "balance_dzd": supplier.balance_dzd_equivalent,
                "balance_dzd_equivalent": supplier.balance_dzd_equivalent,
                "username": supplier.account_username,
                "user_id": supplier.account_uid
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to sync G2Bulk supplier: {error_msg}")
            supplier.last_error = error_msg
            supplier.last_synced_at = timezone.now()
            supplier.save(update_fields=['last_error', 'last_synced_at'])
            return {
                "success": False,
                "supplier": supplier,
                "error": error_msg
            }

    @classmethod
    def sync_account_balance(cls, supplier: SupplierAccount = None) -> dict:
        """
        Synchronizes live balance for a G2Bulk supplier account.
        Compatible interface for API views and external callers.
        """
        res = cls.sync_supplier(supplier=supplier)
        if not res.get("success"):
            raise G2BulkError(res.get("error", "Failed to sync G2Bulk supplier balance"))
        return res

    @classmethod
    def get_transactions(cls, transaction_type: str = None, limit: int = 100) -> dict:
        """
        Fetches recent transactions from G2Bulk API (/transactions?limit=...)
        Optionally filters by transaction_type (e.g. 'add_balance' for deposits).
        If 'add_balance' is requested, searches multiple recent pages to ensure deposits
        aren't overshadowed by high-volume gaming customer charges.
        """
        try:
            global_settings = MonitoringGlobalSettings.get_settings()
            key = cls.get_api_key()
            endpoint_base = global_settings.g2bulk_base_url.rstrip('/')
            url = f"{endpoint_base}/transactions"

            headers = {
                "X-API-Key": key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            all_transactions = []
            max_pages = 5 if transaction_type == 'add_balance' else 1

            with httpx.Client(timeout=15.0) as client:
                for page in range(1, max_pages + 1):
                    params = {"limit": 100, "page": page}
                    res = client.get(url, params=params, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        txs = data.get("data", [])
                        if not txs:
                            break
                        all_transactions.extend(txs)
                    else:
                        break

            if transaction_type == 'add_balance':
                # Match both 'add_balance' and 'add balance'
                filtered = [
                    t for t in all_transactions
                    if 'add' in str(t.get("transaction_type", "")).lower()
                ]
            elif transaction_type:
                filtered = [t for t in all_transactions if t.get("transaction_type") == transaction_type]
            else:
                filtered = all_transactions[:limit]

            return {
                "success": True,
                "transactions": filtered,
                "total": len(filtered),
            }
        except Exception as e:
            logger.error(f"Failed to fetch G2Bulk transactions: {e}")
            return {
                "success": False,
                "error": str(e),
                "transactions": []
            }
