"""
Institutional Binance P2P Acquisition Rate Resolution & Verification Service
Ensures all foreign currency assets (USD, USDT) are valued strictly at the
actual historical / verified purchase price paid in DZD on Binance P2P.
"""
import logging
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


class P2PRateService:
    """
    Resolves and verifies the authentic Binance P2P acquisition price for:
    - G2Bulk Wholesale Account (USD -> DZD)
    - Binance Corporate Reserves (USDT -> DZD)
    - Airalo eSIM Wholesale Partner (USD -> DZD)
    - Bybit Visa Wholesale Account (USDT -> DZD)
    """

    @classmethod
    def get_effective_p2p_rate(cls, system_type: str = None) -> dict:
        """
        Determines the exact purchase price paid for USD/USDT on Binance P2P.
        Hierarchy of Truth:
        1. Department replenishment record with verified P2P purchase rate (WithdrawalRecord / eSIMFundingRecord).
        2. Live / verified Binance P2P C2C Order History (most recent BUY execution price).
        3. Configured system fallback from MonitoringGlobalSettings.
        """
        from ..models import (
            WithdrawalRecord,
            eSIMFundingRecord,
            MonitoringGlobalSettings,
            SubSystemType
        )
        from .binance_service import BinanceApiService

        sys_upper = (system_type or '').upper()

        # 1. Department Replenishment P2P Execution Record
        if sys_upper in ['GAMING', 'GAME']:
            w = WithdrawalRecord.objects.filter(
                p2p_rate__gt=Decimal("0.00")
            ).order_by('-updated_at', '-id').first()
            if w and w.p2p_rate and w.p2p_rate > Decimal("0.00"):
                rate = Decimal(str(w.p2p_rate)).quantize(Decimal("0.01"))
                return {
                    'rate': rate,
                    'p2p_order_id': w.p2p_order_id or f"WD-{w.id}",
                    'source': 'BINANCE_P2P_WITHDRAWAL_RECORD',
                    'system_type': 'GAMING',
                    'audit_badge': f"Verified Binance P2P Purchase: {rate:,.2f} DZD/USDT",
                    'is_verified_p2p': True,
                    'timestamp': w.updated_at.strftime('%Y-%m-%d %H:%M') if w.updated_at else None,
                    'notes': f"Valued at actual Binance P2P acquisition price paid for Withdrawal #{w.id} (Order #{w.p2p_order_id or 'N/A'})."
                }
        elif sys_upper in ['ESIM']:
            e = eSIMFundingRecord.objects.filter(
                p2p_rate__gt=Decimal("0.00")
            ).order_by('-updated_at', '-id').first()
            if e and e.p2p_rate and e.p2p_rate > Decimal("0.00"):
                rate = Decimal(str(e.p2p_rate)).quantize(Decimal("0.01"))
                return {
                    'rate': rate,
                    'p2p_order_id': getattr(e, 'p2p_order_id', None) or f"ESIM-{e.id}",
                    'source': 'BINANCE_P2P_ESIM_RECORD',
                    'system_type': 'ESIM',
                    'audit_badge': f"Verified Binance P2P Purchase: {rate:,.2f} DZD/USDT",
                    'is_verified_p2p': True,
                    'timestamp': e.updated_at.strftime('%Y-%m-%d %H:%M') if e.updated_at else None,
                    'notes': f"Valued at actual Binance P2P acquisition price paid for eSIM Funding #{e.id}."
                }

        # 2. Query Live Binance API C2C / P2P Order History (Latest completed BUY trade)
        try:
            history = BinanceApiService.get_p2p_order_history(trade_type='BUY')
            orders = history.get('orders', [])
            for ord_item in orders:
                unit_price_raw = ord_item.get('unitPrice')
                if unit_price_raw:
                    rate = Decimal(str(unit_price_raw)).quantize(Decimal("0.01"))
                    if rate > Decimal("0.00"):
                        return {
                            'rate': rate,
                            'p2p_order_id': ord_item.get('orderNumber') or ord_item.get('advNo'),
                            'source': 'BINANCE_API_C2C_BUY_ORDER',
                            'system_type': sys_upper or 'ALL',
                            'audit_badge': f"Verified Binance P2P Purchase: {rate:,.2f} DZD/USDT",
                            'is_verified_p2p': True,
                            'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M'),
                            'notes': f"Valued at real-time Binance C2C order execution price #{ord_item.get('orderNumber')}."
                        }
        except Exception as api_err:
            logger.warning(f"Failed to query Binance P2P API for rate: {api_err}")

        # 3. Fallback to any recent completed P2P across all departments
        any_w = WithdrawalRecord.objects.filter(
            p2p_rate__gt=Decimal("0.00")
        ).order_by('-updated_at', '-id').first()
        if any_w and any_w.p2p_rate:
            rate = Decimal(str(any_w.p2p_rate)).quantize(Decimal("0.01"))
            return {
                'rate': rate,
                'p2p_order_id': any_w.p2p_order_id or f"WD-{any_w.id}",
                'source': 'LATEST_GLOBAL_P2P_RECORD',
                'system_type': sys_upper or 'ALL',
                'audit_badge': f"Verified Binance P2P Purchase: {rate:,.2f} DZD/USDT",
                'is_verified_p2p': True,
                'timestamp': any_w.updated_at.strftime('%Y-%m-%d %H:%M') if any_w.updated_at else None,
                'notes': f"Valued at latest verified P2P purchase price from Withdrawal #{any_w.id}."
            }

        # 4. Final institutional fallback from Settings
        settings = MonitoringGlobalSettings.get_settings()
        fallback_rate = Decimal(str(settings.usd_to_dzd_exchange_rate or "254.00")).quantize(Decimal("0.01"))
        return {
            'rate': fallback_rate,
            'p2p_order_id': 'GLOBAL_CONFIG',
            'source': 'SYSTEM_GLOBAL_FALLBACK',
            'system_type': sys_upper or 'ALL',
            'audit_badge': f"Configured Exchange Rate: {fallback_rate:,.2f} DZD/USD",
            'is_verified_p2p': False,
            'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M'),
            'notes': "Valued at configured global base rate (no recent P2P buy order found)."
        }

    @classmethod
    def sync_global_settings_from_latest_p2p(cls) -> Decimal:
        """
        Synchronizes MonitoringGlobalSettings.usd_to_dzd_exchange_rate
        with the latest verified Binance P2P execution price to ensure system-wide consistency.
        """
        from ..models import MonitoringGlobalSettings
        rate_info = cls.get_effective_p2p_rate()
        effective_rate = rate_info['rate']

        settings = MonitoringGlobalSettings.get_settings()
        if settings.usd_to_dzd_exchange_rate != effective_rate:
            settings.usd_to_dzd_exchange_rate = effective_rate
            settings.save(update_fields=['usd_to_dzd_exchange_rate'])
            logger.info(f"Synchronized global exchange rate to verified Binance P2P price: {effective_rate} DZD/USDT")
        return effective_rate
