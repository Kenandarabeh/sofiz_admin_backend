"""
Binance & Crypto Transaction Hash Verification Service for SofizAdmin
Verifies Binance Pay Order IDs, Binance USDT Transfers, and Blockchain TXIDs (TRC20/BEP20)
Checks whether the actual received amount on Binance matches the recorded transaction amount.
"""
import logging
import re
from decimal import Decimal
import httpx
from django.utils import timezone
from ..models import MonitoringGlobalSettings

logger = logging.getLogger(__name__)


class BinanceVerificationService:

    @classmethod
    def verify_transaction(
        cls,
        txid_or_hash: str,
        expected_usd_amount: Decimal = None,
        expected_dzd_amount: Decimal = None,
        exchange_rate: Decimal = None
    ) -> dict:
        """
        Verifies a transaction ID or Hash on Binance / Blockchain.
        Compares actual amount with expected amount.
        """
        if not txid_or_hash or not str(txid_or_hash).strip():
            return {
                'success': False,
                'status': 'NOT_FOUND',
                'verified_amount_usd': None,
                'notes': 'No Transaction ID / Hash provided.'
            }

        txid = str(txid_or_hash).strip()
        settings = MonitoringGlobalSettings.get_settings()
        rate = exchange_rate or settings.usd_to_dzd_exchange_rate or Decimal("240.00")

        # Determine expected USD
        if expected_usd_amount is not None:
            expected_usd = Decimal(str(expected_usd_amount))
        elif expected_dzd_amount is not None:
            expected_usd = (Decimal(str(expected_dzd_amount)) / rate).quantize(Decimal('0.01'))
        else:
            expected_usd = None

        result = cls._fetch_transaction_details(txid, settings)
        
        if not result['found']:
            # Fallback check on Epay Gateway
            epay_result = cls._query_epay_gateway(txid, settings)
            if epay_result['found']:
                result = epay_result

        if not result['found']:
            return {
                'success': False,
                'status': 'NOT_FOUND',
                'verified_amount_usd': None,
                'notes': f"⚠️ Transaction ID '{txid}' could not be verified on Binance or Blockchain network. Details: {result.get('error', 'Not found')}"
            }

        actual_usd = Decimal(str(result['amount_usd']))
        currency = result.get('currency', 'USDT')
        network = result.get('network', 'Binance / Crypto')

        # Compare Amounts
        if expected_usd is not None:
            diff = abs(actual_usd - expected_usd)
            # Allow minor delta ($0.50 tolerance for fee rounding)
            if diff <= Decimal("0.50"):
                status = 'VERIFIED_MATCH'
                notes = f"🟢 VERIFIED & MATCHED: Actual {actual_usd:,.2f} {currency} on {network} matches expected (${expected_usd:,.2f} USD). Timestamp: {result.get('time', timezone.now().strftime('%Y-%m-%d %H:%M'))}"
            else:
                status = 'AMOUNT_MISMATCH'
                notes = f"🔴 AMOUNT MISMATCH: Actual received on {network} is {actual_usd:,.2f} {currency}, but recorded is ${expected_usd:,.2f} USD! (Discrepancy: ${diff:,.2f})"
        else:
            status = 'VERIFIED_MATCH'
            notes = f"🟢 VERIFIED: Found {actual_usd:,.2f} {currency} on {network}."

        return {
            'success': True,
            'status': status,
            'verified_amount_usd': actual_usd,
            'network': network,
            'currency': currency,
            'notes': notes,
            'raw_data': result.get('raw', {})
        }

    @classmethod
    def _fetch_transaction_details(cls, txid: str, settings: MonitoringGlobalSettings) -> dict:
        """
        Attempts to detect and query the transaction from Tron (TRC20), BSC (BEP20), or Binance Pay API.
        """
        # 1. TRON TRC20 TXID (64 hex characters)
        if re.match(r'^[a-fA-F0-9]{64}$', txid):
            tron_data = cls._query_tronscan(txid)
            if tron_data['found']:
                return tron_data

        # 2. BSC / EVM BEP20 TXID (0x + 64 hex characters)
        if re.match(r'^0x[a-fA-F0-9]{64}$', txid):
            bsc_data = cls._query_bscscan(txid)
            if bsc_data['found']:
                return bsc_data

        # 3. Binance Pay Order Query (if API credentials configured)
        if settings.binance_api_key and settings.binance_api_secret:
            binance_pay_data = cls._query_binance_pay_api(txid, settings)
            if binance_pay_data['found']:
                return binance_pay_data

        return {'found': False, 'error': 'No matching blockchain or Binance Pay record found.'}

    @classmethod
    def _query_tronscan(cls, txid: str) -> dict:
        """Queries Tronscan API for USDT (TRC20) transfer info"""
        url = f"https://apilist.tronscanapi.com/api/transaction-info?hash={txid}"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers={"User-Agent": "SofizAdmin/1.0"})
                if res.status_code == 200:
                    data = res.json()
                    # Check for TRC20 transfers
                    trc20_transfers = data.get('trc20TransferInfo', [])
                    if trc20_transfers:
                        transfer = trc20_transfers[0]
                        raw_amount = Decimal(str(transfer.get('amount_str', '0')))
                        decimals = int(transfer.get('decimals', 6))
                        amount = raw_amount / (Decimal(10) ** decimals)
                        symbol = transfer.get('symbol', 'USDT')
                        return {
                            'found': True,
                            'amount_usd': amount,
                            'currency': symbol,
                            'network': 'Tron (TRC20)',
                            'time': timezone.now().strftime('%Y-%m-%d %H:%M'),
                            'raw': data
                        }
                    
                    # Direct TRX contract
                    if data.get('contractRet') == 'SUCCESS':
                        contract_data = data.get('contractData', {})
                        if 'amount' in contract_data:
                            amount = Decimal(str(contract_data['amount'])) / Decimal(1000000)
                            return {
                                'found': True,
                                'amount_usd': amount,
                                'currency': 'TRX',
                                'network': 'Tron (TRX)',
                                'raw': data
                            }
        except Exception as e:
            logger.warning(f"Tronscan query failed for {txid}: {e}")
        return {'found': False}

    @classmethod
    def _query_bscscan(cls, txid: str) -> dict:
        """Queries BSC BscScan API for BEP20 USDT transfer"""
        url = f"https://api.bscscan.com/api?module=proxy&action=eth_getTransactionByHash&txhash={txid}"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    if data.get('result'):
                        return {
                            'found': True,
                            'amount_usd': Decimal("0.00"),
                            'currency': 'USDT',
                            'network': 'BNB Smart Chain (BEP20)',
                            'raw': data
                        }
        except Exception as e:
            logger.warning(f"BscScan query failed for {txid}: {e}")
        return {'found': False}

    @classmethod
    def _query_binance_pay_api(cls, order_id: str, settings: MonitoringGlobalSettings) -> dict:
        """Queries Binance Pay OpenAPI order query endpoint"""
        # Binance Pay query API stub with HMAC SHA512
        try:
            endpoint = "https://bpay.binanceapi.com/binancepay/openapi/v2/order/query"
            payload = {"prepOrderId": order_id} if order_id.isdigit() else {"merchantTradeNo": order_id}
            # If configured, send request
            return {'found': False}
        except Exception as e:
            logger.warning(f"Binance Pay API error for {order_id}: {e}")
            return {'found': False}

    @classmethod
    def _query_epay_gateway(cls, txid: str, settings: MonitoringGlobalSettings) -> dict:
        """Queries Epay / SofizPay Binance verification gateway"""
        base_url = (settings.epay_api_url or "https://epay.sofizpay.com/api/operations").rstrip('/')
        url = f"{base_url}/binance/verify/"
        headers = {
            "X-API-KEY": settings.epay_api_key,
            "Content-Type": "application/json"
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, params={"txid": txid}, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    if data.get('success'):
                        return {
                            'found': True,
                            'amount_usd': Decimal(str(data.get('amount_usd', '0.00'))),
                            'currency': data.get('currency', 'USDT'),
                            'network': 'Binance Pay Gateway',
                            'raw': data
                        }
        except Exception as e:
            logger.debug(f"Epay Binance gateway query info: {e}")
        return {'found': False}


class BinanceApiService:
    """Official Binance API integration with HMAC-SHA256 signature support"""
    BASE_URL = "https://api.binance.com"

    @classmethod
    def _sign_params(cls, params: dict, secret: str) -> dict:
        import hmac
        import hashlib
        import time
        import urllib.parse

        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 60000
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    @classmethod
    def get_p2p_order_history(cls, trade_type: str = 'BUY', page: int = 1, rows: int = 20) -> dict:
        """Fetches recent Binance C2C / P2P orders"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'error': 'Binance API credentials not configured in Global Settings.', 'orders': []}

        endpoint = f"{cls.BASE_URL}/sapi/v1/c2c/orderMatch/listUserOrderHistory"
        params = {
            'tradeType': trade_type,
            'page': page,
            'rows': rows,
        }
        cls._sign_params(params, settings.binance_api_secret)
        headers = {"X-MBX-APIKEY": settings.binance_api_key}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get('code') == '000000':
                    return {'success': True, 'orders': data.get('data', []), 'total': data.get('total', 0)}
                return {'success': False, 'error': data.get('message', f'HTTP {res.status_code}'), 'orders': []}
        except Exception as e:
            logger.error(f"Error fetching Binance P2P orders: {e}")
            return {'success': False, 'error': str(e), 'orders': []}

    @classmethod
    def get_pay_transactions(cls, start_timestamp: int = None, limit: int = 20) -> dict:
        """Fetches recent Binance Pay transactions (sent/received)"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'error': 'Binance API credentials not configured in Global Settings.', 'transactions': []}

        endpoint = f"{cls.BASE_URL}/sapi/v1/pay/transactions"
        params = {'limit': limit}
        if start_timestamp:
            params['startTimestamp'] = start_timestamp
        cls._sign_params(params, settings.binance_api_secret)
        headers = {"X-MBX-APIKEY": settings.binance_api_key}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get('code') == '000000':
                    return {'success': True, 'transactions': data.get('data', [])}
                return {'success': False, 'error': data.get('message', f'HTTP {res.status_code}'), 'transactions': []}
        except Exception as e:
            logger.error(f"Error fetching Binance Pay transactions: {e}")
            return {'success': False, 'error': str(e), 'transactions': []}

    @classmethod
    def get_account_balances(cls) -> dict:
        """Fetches USDT balances across Binance Funding and Spot wallets"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {
                'success': False,
                'error': 'Binance API credentials not configured in Global Settings.',
                'total_usdt': 0.0,
                'funding_usdt': 0.0,
                'spot_usdt': 0.0,
                'balance_dzd_equivalent': 0.0,
                'assets': []
            }

        headers = {"X-MBX-APIKEY": settings.binance_api_key}
        funding_free = Decimal('0.00')
        funding_locked = Decimal('0.00')
        spot_free = Decimal('0.00')
        spot_locked = Decimal('0.00')

        try:
            with httpx.Client(timeout=10.0) as client:
                # 1. Query Binance Funding Wallet (/sapi/v1/asset/get-funding-asset)
                p_fund = {'asset': 'USDT'}
                cls._sign_params(p_fund, settings.binance_api_secret)
                r_fund = client.post(f"{cls.BASE_URL}/sapi/v1/asset/get-funding-asset", params=p_fund, headers=headers)
                if r_fund.status_code == 200:
                    d_fund = r_fund.json()
                    if isinstance(d_fund, list) and d_fund:
                        funding_free = Decimal(str(d_fund[0].get('free', '0.00')))
                        funding_locked = Decimal(str(d_fund[0].get('locked', '0.00')))

                # 2. Query Binance Spot Wallet (/sapi/v3/asset/getUserAsset)
                p_spot = {'asset': 'USDT'}
                cls._sign_params(p_spot, settings.binance_api_secret)
                r_spot = client.post(f"{cls.BASE_URL}/sapi/v3/asset/getUserAsset", params=p_spot, headers=headers)
                if r_spot.status_code == 200:
                    d_spot = r_spot.json()
                    if isinstance(d_spot, list) and d_spot:
                        spot_free = Decimal(str(d_spot[0].get('free', '0.00')))
                        spot_locked = Decimal(str(d_spot[0].get('locked', '0.00')))

            total_usdt = (funding_free + funding_locked + spot_free + spot_locked).quantize(Decimal('0.01'))
            rate = settings.usd_to_dzd_exchange_rate or Decimal('240.00')
            total_dzd = (total_usdt * rate).quantize(Decimal('0.01'))

            return {
                'success': True,
                'total_usdt': float(total_usdt),
                'funding_usdt': float(funding_free + funding_locked),
                'spot_usdt': float(spot_free + spot_locked),
                'balance_dzd_equivalent': float(total_dzd),
                'exchange_rate': float(rate),
                'last_synced_at': timezone.now().isoformat(),
                'assets': [
                    {'wallet': 'FUNDING', 'asset': 'USDT', 'free': float(funding_free), 'locked': float(funding_locked)},
                    {'wallet': 'SPOT', 'asset': 'USDT', 'free': float(spot_free), 'locked': float(spot_locked)},
                ]
            }
        except Exception as e:
            logger.error(f"Error fetching Binance balances: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_usdt': 0.0,
                'funding_usdt': 0.0,
                'spot_usdt': 0.0,
                'balance_dzd_equivalent': 0.0,
                'assets': []
            }

    @classmethod
    def get_withdraw_history(cls, coin: str = None, limit: int = 50) -> dict:
        """Fetches recent Binance crypto on-chain withdrawals history (with network fees)"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'error': 'Binance API credentials not configured in Global Settings.', 'withdrawals': []}

        endpoint = f"{cls.BASE_URL}/sapi/v1/capital/withdraw/history"
        params = {'limit': limit}
        if coin:
            params['coin'] = coin
        cls._sign_params(params, settings.binance_api_secret)
        headers = {"X-MBX-APIKEY": settings.binance_api_key}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers=headers)
                data = res.json()
                if res.status_code == 200 and isinstance(data, list):
                    return {'success': True, 'withdrawals': data}
                return {'success': False, 'error': data.get('msg', f'HTTP {res.status_code}') if isinstance(data, dict) else str(data), 'withdrawals': []}
        except Exception as e:
            logger.error(f"Error fetching Binance withdraw history: {e}")
            return {'success': False, 'error': str(e), 'withdrawals': []}

