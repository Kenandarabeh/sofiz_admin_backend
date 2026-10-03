"""
Unified Epay Financial API Client for SofizAdmin
Fetches Dollar Rate AND Game Profits in ONE single unified API request with dynamic product/service filtering.
Also handles Utility Bills synchronization (Sonelgaz, ADE, AT) and Facture Fees management.
"""
import logging
from decimal import Decimal
import os
import httpx
from django.conf import settings
from django.utils import timezone
from ..models import MonitoringGlobalSettings, GameProfitRecord, UtilityBillRecord

logger = logging.getLogger(__name__)


class EpaySyncService:
    @staticmethod
    def get_api_credentials():
        global_settings = MonitoringGlobalSettings.get_settings()
        api_url = global_settings.epay_api_url or os.getenv("SOFIZPAY_EPAY_API_URL", "https://epay.sofizpay.com/api/operations").rstrip('/')
        api_key = (
            global_settings.epay_api_key or
            os.getenv("MASTER_ADMIN_API_KEY") or
            os.getenv("SOFIZPAY_ADMIN_API_KEY", "sk_sofizadmin_live_52041594509c51cd5cda405b244d9b703e684225473e63164ab614c681de7779")
        )
        return api_url.rstrip('/'), api_key.strip()

    @classmethod
    def get_auth_headers(cls) -> list:
        api_url, primary_key = cls.get_api_credentials()
        keys = [
            primary_key,
            os.getenv("MASTER_ADMIN_API_KEY"),
            "sk_sofizadmin_live_52041594509c51cd5cda405b244d9b703e684225473e63164ab614c681de7779",
            "23a87961eca6be3443d760b38224c1007110bc46440d7259"
        ]
        seen = set()
        unique_keys = []
        for k in keys:
            if k and str(k).strip() and str(k).strip() not in seen:
                seen.add(str(k).strip())
                unique_keys.append(str(k).strip())
        return api_url, unique_keys

    @classmethod
    def sync_financial_summary(cls, product: str = None, from_date: str = None, to_date: str = None) -> dict:
        """
        Calls the SINGLE UNIFIED API in Epay:
        GET /api/operations/financial/summary/?product=...&from_date=...&to_date=...
        """
        api_url, keys_to_try = cls.get_auth_headers()
        endpoints_to_try = [
            f"{api_url}/financial/summary/",
            f"{api_url}/financial/",
            f"{api_url}/pricing/"
        ]

        params = {}
        if product:
            params['product'] = str(product).strip()
        if from_date:
            params['from_date'] = str(from_date).strip()
        if to_date:
            params['to_date'] = str(to_date).strip()

        last_error = None
        for endpoint in endpoints_to_try:
            for key in keys_to_try:
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-KEY": key
                }
                try:
                    with httpx.Client(timeout=15.0) as client:
                        res = client.get(endpoint, headers=headers, params=params)
                        if res.status_code == 200:
                            data = res.json()
                            dollar_rate = Decimal(str(data.get("dollar_rate", "250.00")))
                            total_profit = Decimal(str(data.get("total_profit_dzd", "0.00")))
                            total_sales = Decimal(str(data.get("total_sales_dzd", "0.00")))
                            total_orders = int(data.get("total_orders", 0))

                            if not product or product == 'all':
                                global_settings = MonitoringGlobalSettings.get_settings()
                                global_settings.usd_to_dzd_exchange_rate = dollar_rate
                                global_settings.total_live_profits_dzd = total_profit
                                global_settings.total_live_sales_dzd = total_sales
                                global_settings.total_live_orders_count = total_orders
                                global_settings.save(update_fields=[
                                    'usd_to_dzd_exchange_rate',
                                    'total_live_profits_dzd',
                                    'total_live_sales_dzd',
                                    'total_live_orders_count'
                                ])

                            logger.info(f"Unified sync completed from {endpoint} | Rate: {dollar_rate} | Profit: {total_profit}")
                            return {
                                "success": True,
                                "endpoint": endpoint,
                                "dollar_rate": dollar_rate,
                                "total_profit_dzd": total_profit,
                                "total_sales_dzd": total_sales,
                                "total_cost_dzd": Decimal(str(data.get("total_cost_dzd", "0.00"))),
                                "total_orders": total_orders,
                                "filter_product": data.get("filter_product", product or "ALL"),
                                "from_date": data.get("from_date"),
                                "to_date": data.get("to_date"),
                                "breakdown": data.get("breakdown"),
                                "raw": data
                            }
                        elif res.status_code == 404:
                            break
                        else:
                            last_error = f"HTTP {res.status_code} on {endpoint}: {res.text}"
                except Exception as e:
                    last_error = str(e)

        logger.error(f"Failed unified financial sync from Epay: {last_error}")
        return {"success": False, "error": last_error}

    @classmethod
    def sync_utility_bills(cls, limit: int = 100, service: str = None) -> dict:
        """
        Fetches settled utility bills from Epay and synchronizes into UtilityBillRecord:
        GET /api/operations/financial/bills/?limit=...&service=...
        """
        api_url, keys_to_try = cls.get_auth_headers()
        endpoint = f"{api_url}/financial/bills/"
        params = {"limit": limit}
        if service:
            params["service"] = service

        last_error = None
        for key in keys_to_try:
            headers = {"X-API-KEY": key, "Accept": "application/json"}
            try:
                with httpx.Client(timeout=20.0) as client:
                    res = client.get(endpoint, headers=headers, params=params)
                    if res.status_code == 200:
                        data = res.json()
                        bills = data.get("bills", [])
                        synced_count = 0

                        for b in bills:
                            ref = b.get("bill_reference")
                            if not ref:
                                continue
                            srv = b.get("service", "SONELGAZ")
                            if srv not in [c[0] for c in UtilityBillRecord.BILL_SERVICES]:
                                srv = "SONELGAZ"

                            UtilityBillRecord.objects.update_or_create(
                                bill_reference=ref,
                                defaults={
                                    "service": srv,
                                    "customer_account": b.get("customer_account") or "",
                                    "bill_amount_dzd": Decimal(str(b.get("bill_amount_dzd", 0.0))),
                                    "commission_earned_dzd": Decimal(str(b.get("commission_earned_dzd", 0.0))),
                                    "is_settled": b.get("is_settled", True),
                                }
                            )
                            synced_count += 1

                        logger.info(f"Synced {synced_count} utility bills from Epay successfully")
                        return {"success": True, "count": synced_count, "total_available": len(bills)}
                    else:
                        last_error = f"HTTP {res.status_code}: {res.text}"
            except Exception as e:
                last_error = str(e)

        return {"success": False, "error": last_error}

    @classmethod
    def fetch_facture_fees(cls) -> dict:
        """
        GET /api/operations/facture-fees/
        Returns current configured fees for all utility services.
        """
        api_url, keys_to_try = cls.get_auth_headers()
        endpoint = f"{api_url}/facture-fees/"

        for key in keys_to_try:
            headers = {"X-API-KEY": key, "Accept": "application/json"}
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.get(endpoint, headers=headers)
                    if res.status_code == 200:
                        return {"success": True, "fees": res.json()}
            except Exception as e:
                logger.error(f"Error fetching facture fees: {e}")

        return {"success": False, "error": "Failed to fetch facture fees"}

    @classmethod
    def update_facture_fee(cls, facture_type: str, fee_amount: float) -> dict:
        """
        POST /api/operations/facture-fees/
        Updates fee amount for a specific utility facture type.
        """
        api_url, keys_to_try = cls.get_auth_headers()
        endpoint = f"{api_url}/facture-fees/"
        payload = {"facture_type": facture_type, "fee_amount": fee_amount}

        for key in keys_to_try:
            headers = {"X-API-KEY": key, "Content-Type": "application/json"}
            try:
                with httpx.Client(timeout=10.0) as client:
                    res = client.post(endpoint, headers=headers, json=payload)
                    if res.status_code == 200:
                        return {"success": True, "data": res.json()}
            except Exception as e:
                logger.error(f"Error updating facture fee: {e}")

        return {"success": False, "error": "Failed to update facture fee"}

    # Backward compatibility wrappers
    @classmethod
    def sync_dollar_rate(cls) -> dict:
        return cls.sync_financial_summary()

    @classmethod
    def fetch_game_profit(cls, from_date: str = None, to_date: str = None) -> dict:
        return cls.sync_financial_summary(from_date=from_date, to_date=to_date)

    @classmethod
    def sync_game_profits_from_epay(cls, limit: int = 100) -> dict:
        return cls.sync_financial_summary()
